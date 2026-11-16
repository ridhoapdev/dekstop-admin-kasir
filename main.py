"""
main.py — Titik masuk utama aplikasi Koperasi Simpan Pinjam.
Menjalankan inisialisasi database, backup saat startup, dan menampilkan GUI.
"""
import sys
import logging
from logging.handlers import RotatingFileHandler
from PySide6.QtWidgets import QApplication

from app.config import DB_PATH, LOG_DIR, NAMA_APLIKASI
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.layanan.backup import buat_backup
from app.ui.jendela_utama import JendelaUtama


def konfigurasi_logging() -> None:
    """Mengatur logging aplikasi dengan rotasi berkas maksimal 5 MB (RULES.md)."""
    log_file = LOG_DIR / "app.log"
    handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    logging.basicConfig(
        handlers=[handler],
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )


def main() -> None:
    konfigurasi_logging()
    logging.info("Memulai aplikasi %s", NAMA_APLIKASI)

    # 1. Buka database & inisialisasi skema
    conn = buka_koneksi(DB_PATH)
    inisialisasi_skema(conn)

    # 2. Backup otomatis saat aplikasi dibuka (RULES.md Bab 4.6)
    try:
        buat_backup(conn, catat_log=True)
        logging.info("Backup otomatis saat startup selesai.")
    except Exception as e:
        logging.error("Gagal melakukan backup startup: %s", e)

    # 3. Jalankan antarmuka PySide6
    app = QApplication(sys.argv)
    app.setApplicationName(NAMA_APLIKASI)

    from PySide6.QtGui import QFont
    app.setFont(QFont("Segoe UI", 11))

    from app.ui.tema import STYLE_GLOBAL
    app.setStyleSheet(STYLE_GLOBAL)

    jendela = JendelaUtama(conn)
    jendela.show()

    kode_keluar = app.exec()
    conn.close()
    sys.exit(kode_keluar)


if __name__ == "__main__":
    main()

