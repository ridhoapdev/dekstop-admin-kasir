"""
tests/test_laporan.py — Unit test untuk modul Laporan Mingguan dan Ekspor (Modul 8).
"""
import pytest
from datetime import date
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import tambah_anggota
from app.db.repo_simpanan import tambah_transaksi_simpanan
from app.db.repo_pinjaman import buat_pinjaman_baru
from app.db.repo_angsuran import bayar_angsuran
from app.db.repo_laporan import (
    tentukan_rentang_minggu, ambil_data_laporan_mingguan, catat_log_laporan_mingguan
)
from app.layanan.ekspor_excel import ekspor_tabel_ke_excel
from app.layanan.ekspor_pdf import ekspor_laporan_ke_pdf


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_laporan.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_rentang_minggu_senin_sampai_minggu():
    # Misal Sabtu 14 Nov 2026 -> Senin 9 Nov s/d Minggu 15 Nov
    ref = date(2026, 11, 14)
    awal, akhir = tentukan_rentang_minggu(ref)
    assert awal == date(2026, 11, 9)
    assert akhir == date(2026, 11, 15)
    assert (akhir - awal).days == 6


def test_ambil_data_laporan_mingguan_dan_saldo_kas(db_conn):
    id_a = tambah_anggota(db_conn, "A-0001", "Dani", None, None, None, None, "2026-10-01")

    # Transaksi sebelum minggu laporan (Saldo Kas Awal)
    tambah_transaksi_simpanan(db_conn, id_a, "pokok", "setor", 500000, tanggal="2026-11-01")

    # Transaksi dalam minggu laporan (9 Nov s/d 15 Nov)
    # Setor wajib 100.000
    tambah_transaksi_simpanan(db_conn, id_a, "wajib", "setor", 100000, tanggal="2026-11-10")
    # Tarik sukarela 50.000 (harus setor dulu)
    tambah_transaksi_simpanan(db_conn, id_a, "sukarela", "setor", 100000, tanggal="2026-11-11")
    tambah_transaksi_simpanan(db_conn, id_a, "sukarela", "tarik", 50000, tanggal="2026-11-12")

    # Pinjaman cair 1.000.000 admin 10.000
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_a, 1, plafon=1000000, tenor=1,
        jasa_persen_per_bulan=1.0, biaya_admin=10000, tanggal_cair="2026-11-13"
    )

    # Bayar angsuran 200.000 pokok + 10.000 jasa
    bayar_angsuran(
        db_conn, pinj_id, angsuran_id=None, tanggal="2026-11-14",
        bayar_pokok=200000, bayar_jasa=10000
    )

    lap = ambil_data_laporan_mingguan(
        db_conn, tanggal_awal_iso="2026-11-09", tanggal_akhir_iso="2026-11-15", catat_log=True
    )

    assert lap["saldo_kas_awal"] == 500000
    assert lap["total_simpanan_setor"] == 200000  # 100rb wajib + 100rb sukarela
    assert lap["total_simpanan_tarik"] == 50000
    assert lap["total_pinjaman_cair"] == 1000000
    assert lap["total_biaya_admin"] == 10000
    assert lap["total_angsuran_pokok"] == 200000
    assert lap["total_angsuran_jasa"] == 10000
    assert lap["total_angsuran_masuk"] == 210000

    # Total kas masuk = simpanan setor 200rb + admin 10rb + angsuran 210rb = 420.000
    assert lap["total_kas_masuk"] == 420000
    # Total kas keluar = simpanan tarik 50rb + pencairan 1.000.000 = 1.050.000
    assert lap["total_kas_keluar"] == 1050000
    # Saldo kas akhir = 500.000 + 420.000 - 1.050.000 = -130.000
    assert lap["saldo_kas_akhir"] == -130000

    # Cek log laporan mingguan tercatat
    cur = db_conn.cursor()
    cur.execute("SELECT COUNT(*) FROM laporan_mingguan_log;")
    assert cur.fetchone()[0] == 1


def test_ekspor_pdf_dan_excel_laporan(tmp_path):
    excel_path = tmp_path / "laporan.xlsx"
    pdf_path = tmp_path / "laporan.pdf"

    kolom = ["No", "Tanggal", "Keterangan", "Masuk (Rp)", "Keluar (Rp)", "Sumber"]
    baris = [
        ["1", "2026-11-10", "Simpanan Wajib Dani", "100.000", "0", "simpanan"],
        ["2", "2026-11-13", "Pencairan Pinjaman P-0001", "0", "1.000.000", "pencairan"]
    ]

    # Ekspor Excel
    out_excel = ekspor_tabel_ke_excel(
        "Laporan Mingguan", kolom, baris, excel_path, baris_total=["TOTAL", "", "", "100.000", "1.000.000", ""]
    )
    assert out_excel.exists()

    # Ekspor PDF
    metrik = [
        ("Saldo Kas Awal", "Rp 500.000"),
        ("Total Kas Masuk", "Rp 100.000"),
        ("Total Kas Keluar", "Rp 1.000.000"),
        ("Saldo Kas Akhir", "-Rp 400.000")
    ]
    out_pdf = ekspor_laporan_ke_pdf(
        "LAPORAN MINGGUAN KOPERASI", "09 Nov 2026 s/d 15 Nov 2026", metrik, kolom, baris, pdf_path
    )
    assert out_pdf.exists()

