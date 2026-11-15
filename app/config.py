"""
app/config.py — Pengaturan path dan konstanta aplikasi Koperasi.
"""
from pathlib import Path

# Direktori utama proyek
BASE_DIR = Path(__file__).resolve().parent.parent

# Folder data, backup, dan log
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backup"
LOG_DIR = BASE_DIR / "log"

# Path database utama
DB_PATH = DATA_DIR / "koperasi.db"

# Pastikan folder esensial tersedia
DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Konstanta Aplikasi
NAMA_APLIKASI = "Administrasi Koperasi Simpan Pinjam"
VERSI_APLIKASI = "1.0.0"

# Batas rotasi backup otomatis (RULES.md: 30 file terbaru)
MAX_BACKUP_FILES = 30

