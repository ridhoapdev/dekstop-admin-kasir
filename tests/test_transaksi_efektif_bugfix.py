"""
tests/test_transaksi_efektif_bugfix.py — Pengujian komprehensif untuk transaksi efektif & pembalik.
Menguji:
1. Skenario spesifik dari laporan user:
   - Setoran wajib Rp 500.000 (salah) -> dibatalkan Rp 500.000 -> setoran benar Rp 400.000
   - Pinjaman cair Rp 200.000, biaya admin Rp 5.000, angsuran Rp 24.000 (pokok 20.000, jasa 4.000)
   - Verifikasi Ringkasan, Laporan, Closing, dan Ekspor:
     * Simpanan setor = Rp 400.000 (bukan 900.000)
     * Simpanan tarik = Rp 0 (bukan 500.000)
     * Total kas masuk = Rp 429.000 (bukan 929.000)
     * Total kas keluar = Rp 200.000 (bukan 700.000)
     * Saldo kas akhir = Rp 229.000
2. Pembalik lintas rentang / minggu.
3. Pembalik lintas closing (periode terkunci).
4. Pembalik angsuran (sisa pokok, status angsuran telat/belum).
5. Pemindai ampersand UI agar tidak ada teks tombol bertanda underscore.
"""
import glob
import re
import pytest
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import tambah_anggota
from app.db.repo_simpanan import tambah_transaksi_simpanan, balik_transaksi_simpanan, hitung_saldo_simpanan_anggota
from app.db.repo_pinjaman import buat_pinjaman_baru
from app.db.repo_angsuran import (
    bayar_angsuran, balik_pembayaran_angsuran,
    hitung_sisa_pokok_pinjaman, ambil_daftar_angsuran_dengan_status
)
from app.db.repo_laporan import ambil_data_laporan_mingguan
from app.db.repo_ringkasan import ambil_ringkasan_dashboard
from app.db.repo_closing import jalankan_pemeriksaan_pra_closing, eksekusi_closing_bulanan
from app.db.migrasi_closing import audit_dan_migrasi_closing_lama
from app.logika.transaksi_efektif import hitung_rekap_kas_bersih_rentang


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_efektif.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_skenario_nyata_laporan_dan_closing_bersih(db_conn):
    # Buat anggota
    id_ang = tambah_anggota(
        db_conn, "A-0001", "Ridho Ageng", "Unit IT", "0812345678", None, None, "2026-11-01"
    )

    # 1. Setoran wajib Rp 500.000 (salah)
    id_s1 = tambah_transaksi_simpanan(
        db_conn, id_ang, "wajib", "setor", 500000, "2026-11-14", "Setor salah input"
    )
    # 2. Dibatalkan dengan pembalik Rp 500.000 pada hari/minggu/bulan yang sama
    balik_transaksi_simpanan(
        db_conn, id_s1, "Salah nominal", "2026-11-14"
    )
    # 3. Setoran benar Rp 400.000
    tambah_transaksi_simpanan(
        db_conn, id_ang, "wajib", "setor", 400000, "2026-11-14", "Setor yang benar"
    )

    # 4. Pencairan pinjaman Rp 200.000, admin Rp 5.000
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_ang, None, 200000, 10, 2.0, 5000, "2026-11-14", "Keperluan uji"
    )

    # 5. Angsuran Rp 24.000 (pokok 20.000, jasa 4.000)
    bayar_angsuran(
        db_conn, pinj_id, 1, "2026-11-14", bayar_pokok=20000, bayar_jasa=4000
    )

    # UJI 1: Saldo Simpanan Anggota
    saldo = hitung_saldo_simpanan_anggota(db_conn, id_ang)
    assert saldo["wajib"] == 400000
    assert saldo["total"] == 400000

    # UJI 2: Sisa Pokok Pinjaman
    sisa = hitung_sisa_pokok_pinjaman(db_conn, pinj_id)
    assert sisa == 180000

    # UJI 3: Layar Ringkasan Dashboard (Metrik Hari Ini Bersih)
    dash = ambil_ringkasan_dashboard(db_conn, tanggal_patokan_iso="2026-11-14")
    assert dash["simpanan_masuk_hari_ini"] == 400000
    assert dash["angsuran_masuk_hari_ini"] == 24000
    assert dash["pinjaman_cair_hari_ini"] == 200000
    assert dash["biaya_admin_hari_ini"] == 5000
    assert dash["posisi_kas"] == 229000

    # UJI 4: Laporan Mingguan
    lap = ambil_data_laporan_mingguan(db_conn, "2026-11-09", "2026-11-15")
    assert lap["total_simpanan_setor"] == 400000
    assert lap["total_simpanan_tarik"] == 0
    assert lap["total_angsuran_pokok"] == 20000
    assert lap["total_angsuran_jasa"] == 4000
    assert lap["total_pinjaman_cair"] == 200000
    assert lap["total_biaya_admin"] == 5000
    assert lap["total_kas_masuk"] == 429000
    assert lap["total_kas_keluar"] == 200000
    assert lap["saldo_kas_akhir"] == 229000

    # UJI 5: Pra-Closing
    pra = jalankan_pemeriksaan_pra_closing(db_conn, "2026-11")
    assert pra["kas_masuk"] == 429000
    assert pra["kas_keluar"] == 200000
    assert pra["kas_akhir"] == 229000
    assert pra["rekonsiliasi_cocok"] is True

    # UJI 6: Eksekusi Closing Bulanan
    closing_id = eksekusi_closing_bulanan(db_conn, "2026-11", "Closing November", backup_dulu=False)
    cur = db_conn.cursor()
    cur.execute("SELECT * FROM closing WHERE id = ?;", (closing_id,))
    row_c = cur.fetchone()
    assert row_c["total_kas_masuk"] == 429000
    assert row_c["total_kas_keluar"] == 200000
    assert row_c["saldo_kas_akhir"] == 229000
    assert row_c["total_simpanan"] == 400000
    assert row_c["total_sisa_pokok_pinjaman"] == 180000
    assert row_c["total_jasa_diterima"] == 4000


def test_pembalik_lintas_minggu_dan_lintas_periode(db_conn):
    id_ang = tambah_anggota(
        db_conn, "A-0002", "Budi Santoso", None, None, None, None, "2026-10-01"
    )

    # Transaksi di periode Oktober (2026-10-20)
    id_s = tambah_transaksi_simpanan(
        db_conn, id_ang, "sukarela", "setor", 300000, "2026-10-20", "Setoran Oktober"
    )

    # Closing periode Oktober
    eksekusi_closing_bulanan(db_conn, "2026-10", "Closing Oktober", backup_dulu=False)

    # Pembalik dilakukan di periode November (2026-11-05) karena salah input baru disadari di November
    id_pembalik = balik_transaksi_simpanan(
        db_conn, id_s, "Salah catat baru ketahuan di November", "2026-11-05"
    )
    assert id_pembalik > 0

    # Cek Laporan Minggu 1 November (2026-11-02 s/d 2026-11-08)
    lap_nov = ambil_data_laporan_mingguan(db_conn, "2026-11-02", "2026-11-08")
    # Karena aslinya di Oktober, di minggu ini pembalik tampil sebagai koreksi keluar 300.000
    assert lap_nov["saldo_kas_awal"] == 300000
    assert lap_nov["koreksi_keluar_lintas"] == 300000
    assert lap_nov["jumlah_koreksi_lintas"] == 1
    assert lap_nov["total_kas_keluar"] == 300000
    assert lap_nov["saldo_kas_akhir"] == 0

    # Cek Periode Oktober di tabel closing tetap utuh (tidak berubah)
    cur = db_conn.cursor()
    cur.execute("SELECT total_kas_masuk, saldo_kas_akhir FROM closing WHERE periode = '2026-10';")
    c_okt = cur.fetchone()
    assert c_okt[0] == 300000
    assert c_okt[1] == 300000


def test_pembalik_pembayaran_angsuran_kembali_menunggak(db_conn):
    id_ang = tambah_anggota(
        db_conn, "A-0003", "Citra Dewi", None, "08129999", None, None, "2026-10-01"
    )
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0003", id_ang, None, 1000000, 5, 1.0, 0, "2026-10-01"
    )

    # Bayar cicilan ke-1
    bayar_id = bayar_angsuran(
        db_conn, pinj_id, 1, "2026-10-15", bayar_pokok=200000, bayar_jasa=10000
    )
    assert hitung_sisa_pokok_pinjaman(db_conn, pinj_id) == 800000

    # Cicilan ke-1 sekarang lunas
    daftar1 = ambil_daftar_angsuran_dengan_status(db_conn, pinj_id, "2026-11-14")
    c1 = next(c for c in daftar1 if c["angsuran_ke"] == 1)
    assert c1["status"] == "lunas"

    # Dibatalkan karena salah input
    balik_pembayaran_angsuran(
        db_conn, bayar_id, "Salah transfer / dibatalkan", "2026-10-16"
    )

    # Sisa pokok harus kembali ke 1.000.000
    assert hitung_sisa_pokok_pinjaman(db_conn, pinj_id) == 1000000

    # Status cicilan ke-1 harus kembali belum/telat jika sudah lewat tanggal jatuh tempo
    daftar2 = ambil_daftar_angsuran_dengan_status(db_conn, pinj_id, "2026-11-14")
    c2 = next(c for c in daftar2 if c["angsuran_ke"] == 1)
    assert c2["status"] in ("belum", "telat")


def test_audit_migrasi_closing_lama(db_conn):
    # Buat baris closing buatan dengan status dibuka_kembali dan angka kotor
    with db_conn:
        db_conn.execute(
            """
            INSERT INTO closing 
            (periode, tanggal_closing, saldo_kas_awal, total_kas_masuk, total_kas_keluar,
             saldo_kas_akhir, total_simpanan, total_sisa_pokok_pinjaman, total_jasa_diterima,
             status, catatan)
            VALUES ('2026-09', '2026-09-30', 0, 999000, 500000, 499000, 0, 0, 0, 'dibuka_kembali', 'Test');
            """
        )

    laporan = audit_dan_migrasi_closing_lama(db_conn)
    assert len(laporan) == 1
    assert laporan[0]["diperbarui"] is True
    # Angka telah disesuaikan dengan rekap bersih (karena tidak ada transaksi di 2026-09, bersihnya 0)
    assert laporan[0]["angka_bersih"]["masuk"] == 0


def test_pemindai_ampersand_ui():
    """Memastikan tidak ada teks UI tombol/menu dengan ' & ' yang menyebabkan mnemonic underscore."""
    pola = re.compile(r'(\"[^\"]*\s&\s[^\"]*\"|\'[^\']*\s&\s[^\']*\')')
    pelanggaran = []
    for path in glob.glob("app/ui/**/*.py", recursive=True):
        with open(path, encoding="utf-8") as f:
            for num, line in enumerate(f, 1):
                m = pola.search(line)
                if m:
                    pelanggaran.append(f"{path}:{num} -> {m.group(0)}")
    assert len(pelanggaran) == 0, f"Ditemukan teks UI dengan ' & ': {pelanggaran}"

