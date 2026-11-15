"""
tests/test_backup.py — Pengujian unit untuk layanan backup otomatis dan rotasi file.
"""
import time
import sqlite3
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.layanan.backup import buat_backup, rotasi_backup, ambil_info_backup_terakhir


def test_buat_backup_dan_isi_identik(tmp_path):
    db_file = tmp_path / "koperasi.db"
    backup_folder = tmp_path / "backup"
    
    conn = buka_koneksi(db_file)
    try:
        inisialisasi_skema(conn)
        
        # Tambah satu baris data
        cur = conn.cursor()
        cur.execute("INSERT INTO pengaturan (kunci, nilai) VALUES ('kunci_uji', 'nilai_uji');")
        conn.commit()

        # Buat backup
        backup_file = buat_backup(conn, folder_tujuan=backup_folder, catat_log=True)
        assert backup_file.exists()
        assert backup_file.name.startswith("koperasi_")
        assert backup_file.name.endswith(".db")

        # Cek isi backup identik
        b_conn = sqlite3.connect(str(backup_file))
        try:
            b_cur = b_conn.cursor()
            b_cur.execute("SELECT nilai FROM pengaturan WHERE kunci = 'kunci_uji';")
            row = b_cur.fetchone()
            assert row is not None
            assert row[0] == "nilai_uji"
        finally:
            b_conn.close()

        # Cek log aktivitas mencatat backup
        cur.execute("SELECT COUNT(*) FROM log_aktivitas WHERE aksi = 'backup';")
        assert cur.fetchone()[0] >= 1

        # Cek info backup terakhir
        info = ambil_info_backup_terakhir(backup_folder)
        assert info is not None
        assert "hari ini" in info
    finally:
        conn.close()


def test_rotasi_backup_maksimal_file(tmp_path):
    backup_folder = tmp_path / "backup_rotasi"
    backup_folder.mkdir()

    # Buat 35 file dummy backup dengan mtime bertahap
    file_list = []
    base_time = time.time()
    for i in range(35):
        f = backup_folder / f"koperasi_2026-11-14_{i:04d}00.db"
        f.write_text("dummy")
        # Set mtime
        mod_time = base_time + i * 10
        import os
        os.utime(f, (mod_time, mod_time))
        file_list.append(f)

    assert len(list(backup_folder.glob("koperasi_*.db"))) == 35

    # Rotasi simpan 30
    dihapus = rotasi_backup(backup_folder, maks_simpan=30)
    assert len(dihapus) == 5

    sisa = list(backup_folder.glob("koperasi_*.db"))
    assert len(sisa) == 30


def test_backup_folder_kedua(tmp_path):
    db_file = tmp_path / "koperasi.db"
    backup_folder1 = tmp_path / "backup1"
    backup_folder2 = tmp_path / "backup2"
    backup_folder2.mkdir()

    conn = buka_koneksi(db_file)
    try:
        inisialisasi_skema(conn)
        buat_backup(conn, folder_tujuan=backup_folder1, folder_kedua=str(backup_folder2))

        b1 = list(backup_folder1.glob("koperasi_*.db"))
        b2 = list(backup_folder2.glob("koperasi_*.db"))

        assert len(b1) == 1
        assert len(b2) == 1
        assert b1[0].name == b2[0].name
    finally:
        conn.close()

