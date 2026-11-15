import os
import pytest
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import tambah_anggota
from app.db.repo_kas import (
    tambah_kas_manual,
    ambil_daftar_buku_kas,
    balik_kas_manual
)
from app.db.repo_pinjaman import (
    ajukan_pinjaman,
    setujui_dan_cairkan_pinjaman,
    tolak_pengajuan_pinjaman,
    ambil_pinjaman_by_id,
    ambil_daftar_pinjaman
)
from app.db.repo_simpanan import tambah_transaksi_simpanan, ambil_riwayat_simpanan
from app.db.repo_angsuran import bayar_angsuran
from app.layanan.cetak_kuitansi import (
    buat_kuitansi_simpanan_pdf,
    buat_kuitansi_angsuran_pdf
)


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_fitur_tambahan.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_kas_operasional_manual_dan_rekap(db_conn):
    # 1. Catat kas masuk operasional
    id_masuk = tambah_kas_manual(
        db_conn,
        tanggal="2026-11-14",
        keterangan="Donasi sosial non-anggota",
        jenis_arus="masuk",
        nominal=500000
    )
    assert id_masuk > 0

    # 2. Catat kas keluar operasional
    id_keluar = tambah_kas_manual(
        db_conn,
        tanggal="2026-11-14",
        keterangan="Beli ATK kertas & pulpen",
        jenis_arus="keluar",
        nominal=150000
    )
    assert id_keluar > 0

    # 3. Cek daftar kas
    daftar = ambil_daftar_buku_kas(db_conn, sumber_filter="manual")
    assert len(daftar) == 2

    # 4. Koreksi transaksi pembalik kas keluar
    id_balik = balik_kas_manual(db_conn, id_keluar, "Salah catat nota", "2026-11-14")
    assert id_balik > 0

    daftar_update = ambil_daftar_buku_kas(db_conn, sumber_filter="manual")
    assert len(daftar_update) == 3


def test_workflow_pengajuan_dan_persetujuan_pinjaman(db_conn):
    # Tambah anggota aktif
    id_ang = tambah_anggota(
        db_conn, "A-0010", "Siti Aminah", "Unit Keuangan", "0812345678", "Jl. Melati", "3201010101", "2026-11-01"
    )

    # 1. Ajukan pinjaman
    pinj_id = ajukan_pinjaman(
        conn=db_conn,
        no_pinjaman="P-0010",
        anggota_id=id_ang,
        produk_id=None,
        plafon=5000000,
        tenor=5,
        jasa_persen_per_bulan=1.0,
        biaya_admin=25000,
        tanggal_pengajuan="2026-11-14",
        keperluan="Modal usaha rumahan"
    )

    data = ambil_pinjaman_by_id(db_conn, pinj_id)
    assert data["status"] == "diajukan"
    assert data["tanggal_cair"] == "2026-11-14"

    # Pengajuan muncul di daftar pinjaman dengan status diajukan
    antrean = ambil_daftar_pinjaman(db_conn, status_filter="diajukan")
    assert len(antrean) == 1
    assert antrean[0]["no_pinjaman"] == "P-0010"

    # Kas belum berkurang saat diajukan
    cur = db_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM kas_transaksi WHERE ref_id = ?;", (pinj_id,))
    assert cur.fetchone()[0] == 0

    # 2. Setujui & Cairkan pinjaman
    setujui_dan_cairkan_pinjaman(db_conn, pinj_id, tanggal_cair="2026-11-15")

    data_cair = ambil_pinjaman_by_id(db_conn, pinj_id)
    assert data_cair["status"] == "aktif"
    assert data_cair["tanggal_cair"] == "2026-11-15"

    # Cek kas keluar pencairan & kas masuk admin tercatat
    cur.execute("SELECT keluar FROM kas_transaksi WHERE ref_id = ? AND sumber = 'pencairan';", (pinj_id,))
    assert cur.fetchone()[0] == 5000000
    cur.execute("SELECT masuk FROM kas_transaksi WHERE ref_id = ? AND sumber = 'biaya_admin';", (pinj_id,))
    assert cur.fetchone()[0] == 25000

    # Cek jadwal angsuran terbentuk
    cur.execute("SELECT COUNT(*) FROM angsuran WHERE pinjaman_id = ?;", (pinj_id,))
    assert cur.fetchone()[0] == 5


def test_workflow_penolakan_pengajuan_pinjaman(db_conn):
    id_ang = tambah_anggota(
        db_conn, "A-0011", "Budi Santoso", "Unit Lapangan", None, None, None, "2026-11-01"
    )

    pinj_id = ajukan_pinjaman(
        conn=db_conn,
        no_pinjaman="P-0011",
        anggota_id=id_ang,
        produk_id=None,
        plafon=10000000,
        tenor=12,
        jasa_persen_per_bulan=1.0,
        biaya_admin=50000,
        tanggal_pengajuan="2026-11-14",
        keperluan="Renovasi"
    )

    # Tolak pengajuan
    tolak_pengajuan_pinjaman(db_conn, pinj_id, "Kapasitas gaji tidak mencukupi")

    data = ambil_pinjaman_by_id(db_conn, pinj_id)
    assert data["status"] == "ditolak"
    assert "Ditolak: Kapasitas gaji tidak mencukupi" in data["keperluan"]


def test_cetak_kuitansi_pdf(tmp_path, db_conn):
    id_ang = tambah_anggota(
        db_conn, "A-0012", "Dewi Sartika", "Unit Administrasi", "08129999", None, None, "2026-11-01"
    )

    # 1. Kuitansi Simpanan
    tambah_transaksi_simpanan(db_conn, id_ang, "wajib", "setor", 100000, "2026-11-14", "Simpanan wajib November")
    daftar_s = ambil_riwayat_simpanan(db_conn, id_ang)
    assert len(daftar_s) == 1
    tx_s = dict(daftar_s[0])
    tx_s["no_anggota"] = "A-0012"
    tx_s["nama_anggota"] = "Dewi Sartika"
    tx_s["unit"] = "Unit Administrasi"

    out_simpanan = tmp_path / "kuitansi_simpanan.pdf"
    hasil_simpanan = buat_kuitansi_simpanan_pdf(tx_s, "Koperasi Simpan Pinjam Sejahtera", out_simpanan)
    assert os.path.exists(hasil_simpanan)
    assert os.path.getsize(hasil_simpanan) > 1000

    # 2. Kuitansi Angsuran
    pinj_id = ajukan_pinjaman(
        db_conn, "P-0012", id_ang, None, 2000000, 2, 1.0, 10000, "2026-11-01"
    )
    setujui_dan_cairkan_pinjaman(db_conn, pinj_id, "2026-11-01")

    bayar_angsuran(
        conn=db_conn,
        pinjaman_id=pinj_id,
        angsuran_id=1,
        tanggal="2026-11-14",
        bayar_pokok=1000000,
        bayar_jasa=20000,
        denda=0,
        keterangan="Cicilan ke-1"
    )
    cur = db_conn.cursor()
    cur.execute("SELECT * FROM pembayaran_angsuran WHERE pinjaman_id = ? ORDER BY id DESC LIMIT 1;", (pinj_id,))
    row = cur.fetchone()
    tx_a = dict(row)
    tx_a["no_anggota"] = "A-0012"
    tx_a["nama_anggota"] = "Dewi Sartika"
    tx_a["unit"] = "Unit Administrasi"
    tx_a["no_pinjaman"] = "P-0012"

    out_angsuran = tmp_path / "kuitansi_angsuran.pdf"
    hasil_angsuran = buat_kuitansi_angsuran_pdf(tx_a, "Koperasi Simpan Pinjam Sejahtera", out_angsuran)
    assert os.path.exists(hasil_angsuran)
    assert os.path.getsize(hasil_angsuran) > 1000
