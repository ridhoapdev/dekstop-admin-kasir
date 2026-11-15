"""
tests/test_db.py — Pengujian unit untuk koneksi SQLite dan inisialisasi skema (Modul 1).
"""
import sqlite3
import pytest
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema, SKEMA_VERSI_TERKINI


def test_pragma_koneksi(tmp_path):
    db_file = tmp_path / "test_koperasi.db"
    conn = buka_koneksi(db_file)
    try:
        cur = conn.cursor()
        
        # Cek foreign keys
        cur.execute("PRAGMA foreign_keys;")
        assert cur.fetchone()[0] == 1

        # Cek synchronous
        cur.execute("PRAGMA synchronous;")
        # 2 mewakili FULL
        assert cur.fetchone()[0] == 2

        # Cek journal mode (WAL)
        cur.execute("PRAGMA journal_mode;")
        assert cur.fetchone()[0].upper() == "WAL"
    finally:
        conn.close()


def test_inisialisasi_skema_dan_versi(tmp_path):
    db_file = tmp_path / "test_koperasi.db"
    conn = buka_koneksi(db_file)
    try:
        inisialisasi_skema(conn)

        cur = conn.cursor()
        cur.execute("PRAGMA user_version;")
        assert cur.fetchone()[0] == SKEMA_VERSI_TERKINI

        # Verifikasi tabel penting tercipta
        tabel_wajib = [
            "pengaturan", "anggota", "simpanan_transaksi", "produk_pinjaman",
            "pinjaman", "angsuran", "pembayaran_angsuran", "kas_transaksi",
            "closing", "closing_saldo_anggota", "laporan_mingguan_log",
            "draft", "log_aktivitas"
        ]

        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        ditemukan = {baris[0] for baris in cur.fetchall()}

        for t in tabel_wajib:
            assert t in ditemukan, f"Tabel {t} harus ada di database"

        # Verifikasi konfigurasi awal
        cur.execute("SELECT nilai FROM pengaturan WHERE kunci = 'nama_koperasi';")
        assert cur.fetchone()[0] == "Koperasi Simpan Pinjam"

        # Verifikasi produk pinjaman awal
        cur.execute("SELECT COUNT(*) FROM produk_pinjaman;")
        assert cur.fetchone()[0] >= 1
    finally:
        conn.close()


def test_foreign_key_enforcement(tmp_path):
    db_file = tmp_path / "test_fk.db"
    conn = buka_koneksi(db_file)
    try:
        inisialisasi_skema(conn)
        cur = conn.cursor()

        # Memasukkan simpanan untuk anggota_id yang tidak ada harus gagal IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute("""
                INSERT INTO simpanan_transaksi (anggota_id, jenis, arah, jumlah, tanggal, periode)
                VALUES (999, 'pokok', 'setor', 50000, '2026-11-14', '2026-11');
            """)
    finally:
        conn.close()

