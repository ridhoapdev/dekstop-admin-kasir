"""
app/db/koneksi.py — Pengelolaan koneksi SQLite dengan konfigurasi PRAGMA sesuai RULES.md.
"""
import sqlite3
from pathlib import Path
from typing import Union
from app.config import DB_PATH


def buka_koneksi(path_db: Union[str, Path] = DB_PATH) -> sqlite3.Connection:
    """
    Membuka koneksi ke SQLite dengan PRAGMA:
    - journal_mode = WAL (Write-Ahead Logging untuk konkurensi & keandalan)
    - foreign_keys = ON (menjaga integritas relasi antar tabel)
    - synchronous = FULL (menjamin ketahanan data saat listrik mati / crash)
    - busy_timeout = 5000 (menghindari error locked secara mendadak)
    """
    path = Path(path_db)
    path.parent.mkdir(parents=True, exist_ok=True)

    # timeout 10 detik untuk retry otomatis saat database locked
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA synchronous = FULL;")
    cursor.execute("PRAGMA busy_timeout = 5000;")
    cursor.close()

    return conn

