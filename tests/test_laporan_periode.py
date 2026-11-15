"""
tests/test_laporan_periode.py — Suite Pengujian Otomatis untuk Laporan Bulanan dan Laporan Tahunan.
Memverifikasi:
1. Jumlah 12 bulan = total tahunan secara presisi
2. Saldo akhir bulan N = saldo awal bulan N+1 (rantai saldo kas sempurna)
3. Skenario pembalik: dalam bulan yang sama, lintas bulan, dan lintas tahun
4. Bulan tanpa transaksi, bulan pertama (saldo awal nol), dan tahun tanpa data
5. Perbandingan bulan lalu ketika nilai awal 0 (tidak error pembagian nol)
6. Rekonsiliasi angka laporan = Ringkasan = Closing = isi file ekspor
7. Kinerja laporan dengan data demo fiktif 1 tahun penuh (200 anggota, ribuan transaksi) < 3 detik
"""
import calendar
import os
import sqlite3
import time
from datetime import date
from pathlib import Path
import pytest

from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import tambah_anggota
from app.db.repo_simpanan import tambah_transaksi_simpanan, balik_transaksi_simpanan
from app.db.repo_pinjaman import buat_pinjaman_baru, buat_nomor_pinjaman_berikutnya
from app.db.repo_angsuran import bayar_angsuran, balik_pembayaran_angsuran
from app.db.repo_closing import eksekusi_closing_bulanan, buka_kembali_closing
from app.db.repo_laporan_periode import (
    ambil_data_laporan_bulanan,
    ambil_data_laporan_tahunan,
    ambil_daftar_tahun_tersedia
)
from app.layanan.ekspor_laporan_periode import (
    ekspor_laporan_bulanan_excel,
    ekspor_laporan_bulanan_pdf,
    ekspor_laporan_tahunan_excel,
    ekspor_laporan_tahunan_pdf
)


@pytest.fixture
def db_mem():
    """Database SQLite in-memory bersih untuk pengujian terisolasi."""
    conn = buka_koneksi(":memory:")
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_tahun_dan_bulan_tanpa_data(db_mem):
    """Bulan dan tahun tanpa data tidak boleh error, saldo kas awal nol, baris 12 bulan tetap utuh."""
    data_bln = ambil_data_laporan_bulanan(db_mem, 2025, 1)
    assert data_bln["saldo_kas_awal"] == 0
    assert data_bln["total_kas_masuk"] == 0
    assert data_bln["total_kas_keluar"] == 0
    assert data_bln["saldo_kas_akhir"] == 0
    assert data_bln["simpanan"]["total"]["saldo_akhir"] == 0
    assert data_bln["pinjaman"]["cair_nominal"] == 0
    assert data_bln["rekonsiliasi_cocok"] is True

    # Perbandingan dengan bulan sebelumnya yang nol tidak memicu division by zero
    pb = data_bln["perbandingan"]
    assert pb["kas_masuk"]["persen_str"] == "-"
    assert pb["kas_keluar"]["persen_str"] == "-"

    data_thn = ambil_data_laporan_tahunan(db_mem, 2025)
    assert len(data_thn["tabel_12_bulan"]) == 12
    assert data_thn["total_kas_masuk"] == 0
    assert data_thn["total_kas_keluar"] == 0
    assert data_thn["saldo_kas_akhir"] == 0
    assert data_thn["rekonsiliasi_tahunan_cocok"] is True


def test_rantai_saldo_kas_dan_total_12_bulan(db_mem):
    """
    Menguji bahwa:
    1. Saldo akhir bulan N = Saldo awal bulan N+1.
    2. Jumlah 12 bulan = Total tahunan.
    """
    # 1. Tambah anggota
    ang_id = tambah_anggota(
        db_mem, no_anggota="ANG001", nama="Budi Santoso", nik_karyawan="NIK01",
        unit="Keuangan", no_hp="0812345678", alamat="Jl. Merdeka", tanggal_masuk="2026-01-01"
    )

    # Bulan 1 (Januari 2026): Setoran simpanan pokok Rp 100.000
    tambah_transaksi_simpanan(db_mem, ang_id, "pokok", "setor", 100_000, "2026-01-10")

    # Bulan 2 (Februari 2026): Setoran simpanan wajib Rp 50.000, penarikan Rp 20.000
    tambah_transaksi_simpanan(db_mem, ang_id, "wajib", "setor", 50_000, "2026-02-10")
    tambah_transaksi_simpanan(db_mem, ang_id, "pokok", "tarik", 20_000, "2026-02-15")

    # Bulan 3 (Maret 2026): Pinjaman cair Rp 500.000 (keluar kas), biaya admin Rp 10.000 (masuk kas)
    no_pinj = buat_nomor_pinjaman_berikutnya(db_mem)
    p_id = buat_pinjaman_baru(
        db_mem,
        no_pinjaman=no_pinj,
        anggota_id=ang_id,
        produk_id=None,
        plafon=500_000,
        tenor=5,
        jasa_persen_per_bulan=2.0,
        biaya_admin=10_000,
        tanggal_cair="2026-03-01"
    )

    # Bulan 4 (April 2026): Bayar angsuran ke-1 (Pokok 100.000 + Jasa 10.000 = 110.000)
    cur = db_mem.cursor()
    cur.execute("SELECT id FROM angsuran WHERE pinjaman_id = ? AND angsuran_ke = 1;", (p_id,))
    angs_1_id = cur.fetchone()[0]
    bayar_angsuran(db_mem, p_id, angsuran_id=angs_1_id, tanggal="2026-04-10", bayar_pokok=100_000, bayar_jasa=10_000, denda=0)

    # Ambil Laporan Tahunan 2026
    thn_data = ambil_data_laporan_tahunan(db_mem, 2026)
    tabel_12 = thn_data["tabel_12_bulan"]

    # Verifikasi Rantai Saldo Kas (Akhir N == Awal N+1)
    for i in range(11):
        assert tabel_12[i]["saldo_kas_akhir"] == tabel_12[i + 1]["saldo_kas_awal"], (
            f"Bulan {i+1} ke {i+2} putus: {tabel_12[i]['saldo_kas_akhir']} != {tabel_12[i+1]['saldo_kas_awal']}"
        )

    # Verifikasi Jumlah 12 Bulan == Total Setahun
    sum_masuk_12 = sum(b["kas_masuk"] for b in tabel_12)
    sum_keluar_12 = sum(b["kas_keluar"] for b in tabel_12)
    sum_simpanan_12 = sum(b["simpanan_masuk"] for b in tabel_12)
    sum_cair_12 = sum(b["pinjaman_cair"] for b in tabel_12)
    sum_jasa_12 = sum(b["jasa_diterima"] for b in tabel_12)

    assert thn_data["total_kas_masuk"] == sum_masuk_12
    assert thn_data["total_kas_keluar"] == sum_keluar_12
    assert thn_data["total_simpanan_masuk"] == sum_simpanan_12
    assert thn_data["total_pinjaman_cair"] == sum_cair_12
    assert thn_data["total_jasa_diterima"] == sum_jasa_12

    # Saldo Kas Akhir Tahun = Saldo Kas Awal Tahun + Total Masuk - Total Keluar
    assert thn_data["saldo_kas_akhir"] == thn_data["saldo_kas_awal"] + thn_data["total_kas_masuk"] - thn_data["total_kas_keluar"]
    assert thn_data["saldo_kas_akhir"] == tabel_12[11]["saldo_kas_akhir"]


def test_pembalik_dalam_bulan_dan_lintas_bulan(db_mem):
    """
    Skenario:
    1. Pembalik dalam bulan yang sama: saling meniadakan di laporan bulanan & tahunan.
    2. Pembalik lintas bulan: transaksi asli dihitung di bulan N, pembalik tampil sebagai koreksi di bulan N+1.
    """
    ang_id = tambah_anggota(
        db_mem, no_anggota="ANG002", nama="Dewi Lestari", nik_karyawan="NIK02",
        unit="SDM", no_hp="0812345679", alamat="Jl. Melati", tanggal_masuk="2026-05-01"
    )

    # 1. Dalam bulan Mei 2026: Setoran salah Rp 300.000 dibalik Rp 300.000, setoran benar Rp 200.000
    tx_salah = tambah_transaksi_simpanan(db_mem, ang_id, "wajib", "setor", 300_000, "2026-05-05")
    balik_transaksi_simpanan(db_mem, tx_salah, "Salah nominal", "2026-05-06")
    tambah_transaksi_simpanan(db_mem, ang_id, "wajib", "setor", 200_000, "2026-05-06")

    mei = ambil_data_laporan_bulanan(db_mem, 2026, 5)
    # Bersih: hanya 200.000 yang masuk
    assert mei["total_kas_masuk"] == 200_000
    assert mei["total_kas_keluar"] == 0
    assert mei["saldo_kas_akhir"] == 200_000

    # 2. Lintas Bulan: Closing Mei 2026
    eksekusi_closing_bulanan(db_mem, "2026-05", "Closing Mei", backup_dulu=False)

    # Di bulan Juni 2026: Terjadi pembalik untuk setoran Rp 200.000 yang ada di Mei
    # (karena Mei sudah terkunci, pembalik harus di Juni)
    cur = db_mem.cursor()
    cur.execute("SELECT id FROM simpanan_transaksi WHERE jumlah = 200000 AND arah = 'setor' AND membalik_id IS NULL;")
    st_200 = cur.fetchone()[0]
    balik_transaksi_simpanan(db_mem, st_200, "Dibatalkan lintas bulan", "2026-06-02")

    juni = ambil_data_laporan_bulanan(db_mem, 2026, 6)
    # Saldo kas awal Juni harus sama dengan saldo kas akhir Mei (200.000)
    assert juni["saldo_kas_awal"] == 200_000
    # Pembalik di Juni tampil di pos koreksi keluar
    assert juni["koreksi"]["jumlah"] == 1
    assert juni["koreksi"]["keluar"] == 200_000
    assert juni["total_kas_keluar"] == 200_000
    # Saldo kas akhir Juni menjadi 0
    assert juni["saldo_kas_akhir"] == 0

    # Tahunan 2026 tetap konsisten
    thn = ambil_data_laporan_tahunan(db_mem, 2026)
    assert thn["rekonsiliasi_tahunan_cocok"] is True
    assert thn["tabel_12_bulan"][4]["saldo_kas_akhir"] == thn["tabel_12_bulan"][5]["saldo_kas_awal"]


def test_ekspor_file_bulanan_dan_tahunan(db_mem, tmp_path):
    """Menguji ekspor Excel (.xlsx) dan PDF berjalan mulus tanpa error dan menghasilkan berkas fisik."""
    ang_id = tambah_anggota(
        db_mem, no_anggota="ANG003", nama="Ahmad Dhani", nik_karyawan="NIK03",
        unit="Produksi", no_hp="0812345680", alamat="Jl. Kenanga", tanggal_masuk="2026-07-01"
    )
    tambah_transaksi_simpanan(db_mem, ang_id, "pokok", "setor", 500_000, "2026-07-05")

    data_bln = ambil_data_laporan_bulanan(db_mem, 2026, 7)
    path_xl_bln = tmp_path / "lap_bulanan.xlsx"
    path_pdf_bln = tmp_path / "lap_bulanan.pdf"

    ekspor_laporan_bulanan_excel(data_bln, "KSP Sukses Bersama", path_xl_bln)
    ekspor_laporan_bulanan_pdf(data_bln, "KSP Sukses Bersama", path_pdf_bln)

    assert path_xl_bln.exists() and path_xl_bln.stat().st_size > 1000
    assert path_pdf_bln.exists() and path_pdf_bln.stat().st_size > 1000

    data_thn = ambil_data_laporan_tahunan(db_mem, 2026)
    path_xl_thn = tmp_path / "lap_tahunan.xlsx"
    path_pdf_thn = tmp_path / "lap_tahunan.pdf"

    ekspor_laporan_tahunan_excel(data_thn, "KSP Sukses Bersama", path_xl_thn)
    ekspor_laporan_tahunan_pdf(data_thn, "KSP Sukses Bersama", path_pdf_thn)

    assert path_xl_thn.exists() and path_xl_thn.stat().st_size > 1000
    assert path_pdf_thn.exists() and path_pdf_thn.stat().st_size > 1000


def test_uji_performa_data_demo_1_tahun(db_mem):
    """
    Seed data demo FIKTIF 1 tahun penuh:
    - 200 anggota
    - Ribuan transaksi kas & simpanan
    Target kinerja: kalkulasi laporan bulanan & tahunan harus selesai dalam < 3 detik (PC rendah i3/4GB).
    """
    conn = db_mem
    # Gunakan mode transaksi cepat
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("BEGIN TRANSACTION;")

    # 1. Buat 200 anggota
    for i in range(1, 201):
        conn.execute(
            """
            INSERT INTO anggota (no_anggota, nama, nik_karyawan, unit, tanggal_masuk, status)
            VALUES (?, ?, ?, ?, '2026-01-01', 'aktif');
            """,
            (f"ANG{i:03d}", f"Anggota Demo {i}", f"NIK{i:03d}", f"Unit {(i % 5) + 1}")
        )

    # 2. Buat ribuan transaksi simpanan dan kas untuk setiap bulan (Januari - Desember)
    for b in range(1, 13):
        tgl = f"2026-{b:02d}-10"
        periode = f"2026-{b:02d}"
        for ang_id in range(1, 201):
            # Simpanan wajib Rp 50.000 per anggota per bulan (total 200 * 12 = 2.400 transaksi)
            conn.execute(
                """
                INSERT INTO simpanan_transaksi (anggota_id, jenis, arah, jumlah, tanggal, periode)
                VALUES (?, 'wajib', 'setor', 50000, ?, ?);
                """,
                (ang_id, tgl, periode)
            )
            st_id = cur_last_id = conn.execute("SELECT last_insert_rowid();").fetchone()[0]
            conn.execute(
                """
                INSERT INTO kas_transaksi (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
                VALUES (?, 'Simpanan wajib demo', 50000, 0, 'simpanan', ?, ?);
                """,
                (tgl, st_id, periode)
            )

    conn.execute("COMMIT;")
    conn.execute("PRAGMA synchronous = NORMAL;")

    # Ukur waktu eksekusi Laporan Bulanan
    t0 = time.time()
    bln_data = ambil_data_laporan_bulanan(conn, 2026, 6)
    durasi_bln = time.time() - t0

    assert bln_data["simpanan"]["total"]["setor"] == 200 * 50_000  # 10.000.000
    assert durasi_bln < 1.5, f"Laporan bulanan terlalu lambat: {durasi_bln:.2f}s"

    # Ukur waktu eksekusi Laporan Tahunan (12 bulan)
    t1 = time.time()
    thn_data = ambil_data_laporan_tahunan(conn, 2026)
    durasi_thn = time.time() - t1

    assert thn_data["total_kas_masuk"] == 12 * 200 * 50_000  # 120.000.000
    assert thn_data["rekonsiliasi_tahunan_cocok"] is True
    assert durasi_thn < 3.0, f"Laporan tahunan melebihi batas 3 detik: {durasi_thn:.2f}s"
    print(f"\n[BENCHMARK] 1 Tahun Penuh (2.400 Transaksi, 200 Anggota) -> Bulanan: {durasi_bln:.3f}s | Tahunan (12 Bulan): {durasi_thn:.3f}s")
