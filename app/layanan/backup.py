"""
app/layanan/backup.py — Layanan backup otomatis SQLite sesuai RULES.md.
Menggunakan sqlite3.Connection.backup() (BUKAN copy mentah).
Mendukung:
- Penamaan koperasi_YYYY-MM-DD_HHMM.db
- Rotasi 30 file terbaru (file lama dihapus)
- Salinan ke folder cadangan kedua jika diatur (mis. flashdisk / cloud)
- Pencatatan ke log_aktivitas
"""
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from app.config import BACKUP_DIR, DB_PATH, MAX_BACKUP_FILES


def buat_backup(
    conn: sqlite3.Connection,
    folder_tujuan: Optional[Path] = None,
    folder_kedua: Optional[str] = None,
    catat_log: bool = True
) -> Optional[Path]:
    """
    Melakukan backup online yang aman menggunakan API backup SQLite.
    """
    target_dir = folder_tujuan or BACKUP_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    nama_file = f"koperasi_{timestamp}.db"
    file_tujuan = target_dir / nama_file

    # Gunakan sqlite3.Connection.backup() ke database tujuan
    backup_conn = sqlite3.connect(str(file_tujuan))
    try:
        with backup_conn:
            conn.backup(backup_conn)
    finally:
        backup_conn.close()

    # Salin ke folder kedua jika ditentukan
    if folder_kedua and folder_kedua.strip():
        try:
            path_kedua = Path(folder_kedua.strip())
            if path_kedua.exists() and path_kedua.is_dir():
                shutil.copy2(file_tujuan, path_kedua / nama_file)
        except Exception:
            # Sesuai RULES.md: lanjut diam-diam jika folder kedua tidak tersedia
            pass

    # Rotasi file backup lama
    rotasi_backup(target_dir, maks_simpan=MAX_BACKUP_FILES)

    # Catat ke log aktivitas jika diminta
    if catat_log:
        try:
            with conn:
                conn.execute(
                    "INSERT INTO log_aktivitas (aksi, tabel, detail) VALUES (?, ?, ?);",
                    ("backup", "backup", f"Backup otomatis berhasil disimpan ke {nama_file}")
                )
        except Exception:
            pass

    return file_tujuan


def rotasi_backup(folder: Path, maks_simpan: int = MAX_BACKUP_FILES) -> List[Path]:
    """
    Menyimpan maks_simpan file backup terbaru di folder, menghapus file yang lebih lama.
    Mengembalikan daftar file yang dihapus.
    """
    if not folder.exists():
        return []

    daftar_file = sorted(
        folder.glob("koperasi_*.db"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    dihapus: List[Path] = []
    if len(daftar_file) > maks_simpan:
        for f in daftar_file[maks_simpan:]:
            try:
                f.unlink()
                dihapus.append(f)
            except OSError:
                pass

    return dihapus


def ambil_info_backup_terakhir(folder: Optional[Path] = None) -> Optional[str]:
    """
    Mengambil string waktu backup terakhir untuk ditampilkan di UI.
    Contoh: 'hari ini 08.12' atau '14 Nov 2026 15.30'
    """
    target_dir = folder or BACKUP_DIR
    if not target_dir.exists():
        return None

    daftar_file = sorted(
        target_dir.glob("koperasi_*.db"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    if not daftar_file:
        return None

    terakhir = daftar_file[0]
    waktu_mtime = datetime.fromtimestamp(terakhir.stat().st_mtime)
    sekarang = datetime.now()

    if waktu_mtime.date() == sekarang.date():
        return f"hari ini {waktu_mtime.strftime('%H.%M')}"
    return waktu_mtime.strftime("%d %b %Y %H.%M")

