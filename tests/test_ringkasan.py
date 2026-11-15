"""
tests/test_ringkasan.py — Unit test untuk modul Layar Ringkasan dan Pengingat (Modul 7).
"""
import pytest
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import tambah_anggota
from app.db.repo_simpanan import tambah_transaksi_simpanan
from app.db.repo_pinjaman import buat_pinjaman_baru
from app.db.repo_angsuran import bayar_angsuran
from app.db.repo_ringkasan import ambil_ringkasan_dashboard, hitung_saldo_kas_saat_ini


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_modul7.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_ringkasan_transaksi_hari_ini_dan_kas(db_conn):
    tgl_uji = "2026-11-14"
    id_a = tambah_anggota(db_conn, "A-0001", "Pak Haris", None, None, None, None, "2026-11-01")

    # 1. Simpanan masuk hari ini Rp 100.000
    tambah_transaksi_simpanan(db_conn, id_a, "wajib", "setor", 100000, tanggal=tgl_uji)

    # 2. Pinjaman cair hari ini Rp 5.000.000 (biaya admin Rp 50.000)
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_a, 1, plafon=5000000, tenor=5,
        jasa_persen_per_bulan=1.0, biaya_admin=50000, tanggal_cair=tgl_uji
    )

    # 3. Angsuran masuk hari ini Rp 500.000
    bayar_angsuran(
        db_conn, pinjaman_id=pinj_id, angsuran_id=None, tanggal=tgl_uji,
        bayar_pokok=450000, bayar_jasa=50000
    )

    dash = ambil_ringkasan_dashboard(db_conn, tanggal_patokan_iso=tgl_uji)

    assert dash["simpanan_masuk_hari_ini"] == 100000
    assert dash["pinjaman_cair_hari_ini"] == 5000000
    assert dash["angsuran_masuk_hari_ini"] == 500000

    # Posisi kas:
    # Masuk: Simpanan 100.000 + Biaya admin 50.000 + Angsuran 500.000 = 650.000
    # Keluar: Pencairan pinjaman 5.000.000
    # Saldo kas = 650.000 - 5.000.000 = -4.350.000
    assert dash["posisi_kas"] == -4350000


def test_ringkasan_jatuh_tempo_dan_menunggak(db_conn):
    tgl_uji = "2026-11-14"
    id_a = tambah_anggota(db_conn, "A-0001", "Bambang", None, None, "0812345", None, "2026-09-01")

    # Pinjaman cair 1 Oktober -> Angs 1 tempo 1 Nov (sudah lewat per 14 Nov = MENUNGGAK)
    # Angs 2 tempo 1 Des
    buat_pinjaman_baru(
        db_conn, "P-0001", id_a, 1, plafon=2000000, tenor=2,
        jasa_persen_per_bulan=1.0, biaya_admin=0, tanggal_cair="2026-10-01"
    )

    # Pinjaman kedua cair 10 Nov -> Angs 1 tempo 10 Des (jatuh tempo > 7 hari)
    # Pinjaman ketiga cair 14 Okt -> Angs 1 tempo 14 Nov (JATUH TEMPO HARI INI / MINGGU INI)
    id_b = tambah_anggota(db_conn, "A-0002", "Cecep", None, None, None, None, "2026-10-01")
    buat_pinjaman_baru(
        db_conn, "P-0002", id_b, 1, plafon=1000000, tenor=1,
        jasa_persen_per_bulan=1.0, biaya_admin=0, tanggal_cair="2026-10-14"
    )

    dash = ambil_ringkasan_dashboard(db_conn, tanggal_patokan_iso=tgl_uji)

    # Ada 1 cicilan jatuh tempo minggu ini (P-0002 tempo 14 Nov)
    assert dash["jumlah_jatuh_tempo_minggu_ini"] >= 1

    # Ada 1 anggota menunggak (Bambang, angsuran ke-1 tempo 1 Nov belum bayar)
    assert dash["jumlah_anggota_menunggak"] == 1
    assert dash["daftar_anggota_menunggak"][0]["nama_anggota"] == "Bambang"


def test_pengingat_laporan_dan_closing(db_conn):
    tgl_uji = "2026-11-14"
    dash = ambil_ringkasan_dashboard(db_conn, tanggal_patokan_iso=tgl_uji)

    # Default: pengingat laporan mingguan dan closing harus aktif (karena belum ada log/closing)
    assert dash["pengingat_laporan_mingguan"] is True
    assert dash["pengingat_closing"] is True

    # Jika laporan mingguan dicatat
    with db_conn:
        db_conn.execute("""
            INSERT INTO laporan_mingguan_log (tanggal_awal, tanggal_akhir, dibuat_pada)
            VALUES ('2026-11-01', '2026-11-07', '2026-11-10 10:00:00');
        """)

    # Jika closing bulan lalu (2026-10) sudah dilakukan
    with db_conn:
        db_conn.execute("""
            INSERT INTO closing (
                periode, tanggal_closing, saldo_kas_awal, total_kas_masuk,
                total_kas_keluar, saldo_kas_akhir, total_simpanan,
                total_sisa_pokok_pinjaman, total_jasa_diterima, status
            ) VALUES (
                '2026-10', '2026-10-31', 0, 0, 0, 0, 0, 0, 0, 'tertutup'
            );
        """)

    dash2 = ambil_ringkasan_dashboard(db_conn, tanggal_patokan_iso=tgl_uji)
    assert dash2["pengingat_laporan_mingguan"] is False
    assert dash2["pengingat_closing"] is False

