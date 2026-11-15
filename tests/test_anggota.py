"""
tests/test_anggota.py — Unit test untuk modul Data Anggota.
"""
import sqlite3
import pytest
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import (
    tambah_anggota, ubah_anggota, set_status_anggota,
    hapus_anggota_jika_tanpa_transaksi, ambil_anggota_by_id,
    ambil_daftar_anggota, buat_nomor_anggota_berikutnya
)


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_anggota.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_tambah_dan_ambil_anggota(db_conn):
    no_ang = buat_nomor_anggota_berikutnya(db_conn)
    assert no_ang == "A-0001"

    id_budi = tambah_anggota(
        db_conn,
        no_anggota=no_ang,
        nama="Budi Santoso",
        nik_karyawan="EMP-101",
        unit="Produksi",
        no_hp="08123456789",
        alamat="Jl. Merdeka No. 1",
        tanggal_masuk="2026-11-14",
        catatan="Anggota baru"
    )

    anggota = ambil_anggota_by_id(db_conn, id_budi)
    assert anggota is not None
    assert anggota["nama"] == "Budi Santoso"
    assert anggota["no_anggota"] == "A-0001"
    assert anggota["status"] == "aktif"

    # No anggota berikutnya harus A-0002
    no_berikutnya = buat_nomor_anggota_berikutnya(db_conn)
    assert no_berikutnya == "A-0002"


def test_ubah_data_anggota(db_conn):
    id_ang = tambah_anggota(
        db_conn,
        no_anggota="A-0001",
        nama="Siti Aminah",
        nik_karyawan=None,
        unit="Keuangan",
        no_hp="08555",
        alamat=None,
        tanggal_masuk="2026-11-14"
    )

    ubah_anggota(
        db_conn,
        anggota_id=id_ang,
        nama="Siti Aminah, S.E.",
        nik_karyawan="EMP-202",
        unit="Akuntansi",
        no_hp="08555123",
        alamat="Bandung",
        catatan="Promosi"
    )

    updated = ambil_anggota_by_id(db_conn, id_ang)
    assert updated["nama"] == "Siti Aminah, S.E."
    assert updated["unit"] == "Akuntansi"
    assert updated["nik_karyawan"] == "EMP-202"


def test_nonaktifkan_anggota(db_conn):
    id_ang = tambah_anggota(
        db_conn,
        no_anggota="A-0001",
        nama="Joko",
        nik_karyawan="123",
        unit="Logistik",
        no_hp=None,
        alamat=None,
        tanggal_masuk="2026-11-14"
    )

    set_status_anggota(db_conn, id_ang, status="keluar", tanggal_keluar="2026-11-20")
    anggota = ambil_anggota_by_id(db_conn, id_ang)
    assert anggota["status"] == "keluar"
    assert anggota["tanggal_keluar"] == "2026-11-20"


def test_aturan_hapus_anggota_jika_ada_transaksi(db_conn):
    id_ang = tambah_anggota(
        db_conn,
        no_anggota="A-0001",
        nama="Dewi",
        nik_karyawan="321",
        unit="HRD",
        no_hp=None,
        alamat=None,
        tanggal_masuk="2026-11-14"
    )

    # Tambah transaksi simpanan untuk Dewi
    with db_conn:
        db_conn.execute("""
            INSERT INTO simpanan_transaksi (anggota_id, jenis, arah, jumlah, tanggal, periode)
            VALUES (?, 'pokok', 'setor', 100000, '2026-11-14', '2026-11');
        """, (id_ang,))

    # Percobaan hapus harus ditolak ValueError sesuai SPEC.md / RULES.md
    with pytest.raises(ValueError, match="tidak boleh dihapus"):
        hapus_anggota_jika_tanpa_transaksi(db_conn, id_ang)

    # Pastikan data anggota tetap utuh
    assert ambil_anggota_by_id(db_conn, id_ang) is not None


def test_hapus_anggota_tanpa_transaksi_sukses(db_conn):
    id_ang = tambah_anggota(
        db_conn,
        no_anggota="A-0099",
        nama="Salah Input",
        nik_karyawan=None,
        unit=None,
        no_hp=None,
        alamat=None,
        tanggal_masuk="2026-11-14"
    )
    # Hapus anggota yang belum ada transaksi boleh sukses
    assert hapus_anggota_jika_tanpa_transaksi(db_conn, id_ang) is True
    assert ambil_anggota_by_id(db_conn, id_ang) is None


def test_pencarian_dan_filter_anggota(db_conn):
    tambah_anggota(db_conn, "A-0001", "Ahmad Dani", "EMP-01", "Gudang", None, None, "2026-11-14")
    id_b = tambah_anggota(db_conn, "A-0002", "Bambang Pamungkas", "EMP-02", "Lapangan", None, None, "2026-11-14")
    set_status_anggota(db_conn, id_b, "keluar")

    # Filter aktif
    aktif_list = ambil_daftar_anggota(db_conn, status_filter="aktif")
    assert len(aktif_list) == 1
    assert aktif_list[0]["nama"] == "Ahmad Dani"

    # Filter keluar
    keluar_list = ambil_daftar_anggota(db_conn, status_filter="keluar")
    assert len(keluar_list) == 1
    assert keluar_list[0]["nama"] == "Bambang Pamungkas"

    # Cari kata kunci
    hasil_cari = ambil_daftar_anggota(db_conn, kata_kunci="gudang")
    assert len(hasil_cari) == 1
    assert hasil_cari[0]["nama"] == "Ahmad Dani"

