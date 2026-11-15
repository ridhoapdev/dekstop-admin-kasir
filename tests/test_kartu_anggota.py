"""
tests/test_kartu_anggota.py — Unit test untuk Pencarian Global, Kartu Anggota, dan Filter Cepat (Modul 6).
"""
import pytest
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import tambah_anggota
from app.db.repo_simpanan import tambah_transaksi_simpanan
from app.db.repo_pinjaman import buat_pinjaman_baru
from app.db.repo_angsuran import bayar_angsuran
from app.db.repo_kartu_anggota import (
    cari_global, ambil_data_kartu_anggota, ambil_transaksi_filter_cepat
)


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_modul6.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_cari_global_case_insensitive(db_conn):
    id_a = tambah_anggota(
        db_conn, "A-0001", "Siti Nurhaliza", "EMP-99", "Keuangan", "08123", "Bandung", "2026-11-01"
    )
    buat_pinjaman_baru(
        db_conn, "P-0001", id_a, 1, 5000000, 5, 1.5, 0, "2026-11-01"
    )

    # Cari nama huruf kecil
    hasil_nama = cari_global(db_conn, "nurhaliza")
    assert len(hasil_nama) >= 1
    assert hasil_nama[0]["tipe"] == "anggota"
    assert "Siti Nurhaliza" in hasil_nama[0]["judul"]

    # Cari no pinjaman
    hasil_pinj = cari_global(db_conn, "P-0001")
    assert len(hasil_pinj) >= 1
    assert any(h["tipe"] == "pinjaman" for h in hasil_pinj)

    # Cari NIK
    hasil_nik = cari_global(db_conn, "EMP-99")
    assert len(hasil_nik) >= 1
    assert hasil_nik[0]["tipe"] == "anggota"


def test_ambil_data_kartu_anggota_lengkap(db_conn):
    id_a = tambah_anggota(
        db_conn, "A-0001", "Budi Santoso", "EMP-01", "Gudang", "08111", "Jakarta", "2026-11-01"
    )
    # Tambah simpanan
    tambah_transaksi_simpanan(db_conn, id_a, "pokok", "setor", 100000, "2026-11-01")
    tambah_transaksi_simpanan(db_conn, id_a, "wajib", "setor", 50000, "2026-11-02")

    # Tambah pinjaman
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_a, 1, plafon=2000000, tenor=2,
        jasa_persen_per_bulan=1.0, biaya_admin=0, tanggal_cair="2026-10-01"
    )

    # Bayar cicilan 1
    bayar_angsuran(
        db_conn, pinj_id, angsuran_id=None, tanggal="2026-11-05",
        bayar_pokok=1000000, bayar_jasa=20000
    )

    kartu = ambil_data_kartu_anggota(db_conn, id_a)
    assert kartu is not None
    assert kartu["anggota"]["nama"] == "Budi Santoso"
    assert kartu["saldo_simpanan"]["pokok"] == 100000
    assert kartu["saldo_simpanan"]["wajib"] == 50000
    assert kartu["saldo_simpanan"]["total"] == 150000

    # Cek pinjaman aktif
    assert len(kartu["pinjaman_aktif"]) == 1
    assert kartu["pinjaman_aktif"][0]["sisa_pokok"] == 1000000

    # Cek riwayat gabungan
    assert len(kartu["riwayat_transaksi"]) == 3  # 2 simpanan + 1 angsuran


def test_filter_cepat_transaksi(db_conn):
    id_a = tambah_anggota(db_conn, "A-0001", "Andi", None, None, None, None, "2026-11-01")
    tambah_transaksi_simpanan(db_conn, id_a, "wajib", "setor", 50000, "2026-11-14")

    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_a, 1, 1000000, 1, 1.0, 0, "2026-10-01"
    )

    # Filter hari_ini
    hari_ini = ambil_transaksi_filter_cepat(db_conn, "hari_ini")
    assert len(hari_ini) >= 1
    assert hari_ini[0]["nominal"] == 50000

    # Filter pinjaman aktif
    p_aktif = ambil_transaksi_filter_cepat(db_conn, "pinjaman_aktif")
    assert len(p_aktif) == 1
    assert "P-0001" in p_aktif[0]["rincian"]

    # Filter menunggak (jatuh tempo 2026-11-01 sudah lewat per 14 Nov 2026)
    tunggakan = ambil_transaksi_filter_cepat(db_conn, "menunggak")
    assert len(tunggakan) == 1
    assert "P-0001" in tunggakan[0]["rincian"]

