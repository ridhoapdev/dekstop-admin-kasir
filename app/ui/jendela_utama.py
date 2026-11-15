"""
app/ui/jendela_utama.py — Kerangka jendela utama PySide6 dengan stacked widget dan integrasi Buku Kas Operasional.
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QMenuBar, QMenu, QStatusBar, QMessageBox, QStackedWidget,
    QLineEdit, QListWidget, QListWidgetItem
)
from PySide6.QtGui import QAction, QFont
from PySide6.QtCore import Qt
import sqlite3
from typing import Optional

from app.config import NAMA_APLIKASI, VERSI_APLIKASI
from app.layanan.backup import buat_backup, ambil_info_backup_terakhir
from app.db.repo_kartu_anggota import cari_global
from app.ui.layar_ringkasan import LayarRingkasan
from app.ui.layar_anggota import LayarAnggota
from app.ui.layar_simpanan import LayarSimpanan, DialogInputSimpanan
from app.ui.layar_pinjaman import LayarPinjaman, DialogPinjamanBaru
from app.ui.layar_angsuran import LayarAngsuran, DialogInputAngsuran
from app.ui.layar_kartu_anggota import LayarKartuAnggota
from app.ui.layar_filter_cepat import LayarFilterCepat
from app.ui.layar_laporan import LayarLaporan
from app.ui.layar_laporan_bulanan import LayarLaporanBulanan
from app.ui.layar_laporan_tahunan import LayarLaporanTahunan
from app.ui.layar_closing import LayarClosing
from app.ui.layar_impor import LayarImpor
from app.ui.layar_kas import LayarKas


class JendelaUtama(QMainWindow):
    """
    Jendela Utama Koperasi Simpan Pinjam.
    Menampilkan Layar Ringkasan sebagai halaman awal (default).
    """

    def __init__(self, conn: sqlite3.Connection):
        super().__init__()
        self.conn = conn
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle(f"{NAMA_APLIKASI} v{VERSI_APLIKASI}")
        self.resize(1024, 700)
        self.setMinimumSize(900, 600)

        font_dasar = QFont("Segoe UI", 12)
        self.setFont(font_dasar)

        self._buat_menu()

        wadah_utama = QWidget(self)
        layout_utama = QVBoxLayout(wadah_utama)
        layout_utama.setContentsMargins(15, 10, 15, 15)
        layout_utama.setSpacing(10)

        # Header Atas: Breadcrumb Indikator Halaman Aktif & Kotak Cari Global
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        # Indikator Halaman Aktif (Breadcrumb)
        self.lbl_breadcrumb = QLabel("Halaman: Ringkasan (Beranda)", self)
        self.lbl_breadcrumb.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_breadcrumb.setStyleSheet(
            "background-color: #EFF6FF; color: #1D4ED8; padding: 6px 14px; "
            "border: 1px solid #BFDBFE; border-radius: 6px;"
        )
        top_bar.addWidget(self.lbl_breadcrumb)

        top_bar.addSpacing(6)

        lbl_cari = QLabel("Pencarian Cepat:", self)
        lbl_cari.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_cari.setStyleSheet("color: #1E3A8A;")
        top_bar.addWidget(lbl_cari)

        self.input_cari_global = QLineEdit(self)
        self.input_cari_global.setPlaceholderText("Ketik nama, no. anggota, no. pinjaman, atau NIK karyawan... (hasil muncul instan)")
        self.input_cari_global.setMinimumHeight(38)
        self.input_cari_global.setStyleSheet(
            "padding: 0 12px; border: 1.5px solid #93C5FD; border-radius: 6px; background-color: #FFFFFF;"
        )
        self.input_cari_global.textChanged.connect(self._on_cari_global_changed)
        top_bar.addWidget(self.input_cari_global, 1)

        layout_utama.addLayout(top_bar)

        self.list_hasil_cari = QListWidget(self)
        self.list_hasil_cari.setMaximumHeight(160)
        self.list_hasil_cari.setFont(QFont("Segoe UI", 11))
        self.list_hasil_cari.setStyleSheet(
            "border: 1px solid #CBD5E1; border-radius: 4px; background-color: #F8FAFC;"
        )
        self.list_hasil_cari.hide()
        self.list_hasil_cari.itemClicked.connect(self._on_hasil_cari_diklik)
        layout_utama.addWidget(self.list_hasil_cari)

        # Stacked Widget untuk navigasi layar
        self.stack = QStackedWidget(self)

        self.layar_ringkasan = LayarRingkasan(self.conn, callback_navigasi=self._aksi_navigasi_ringkasan, parent=self)
        self.stack.addWidget(self.layar_ringkasan)

        self.layar_anggota = LayarAnggota(self.conn, parent=self)
        self.stack.addWidget(self.layar_anggota)

        self.layar_simpanan = LayarSimpanan(self.conn, parent=self)
        self.stack.addWidget(self.layar_simpanan)

        self.layar_pinjaman = LayarPinjaman(self.conn, parent=self)
        self.stack.addWidget(self.layar_pinjaman)

        self.layar_angsuran = LayarAngsuran(self.conn, parent=self)
        self.stack.addWidget(self.layar_angsuran)

        self.layar_kartu_anggota = LayarKartuAnggota(self.conn, parent=self)
        self.stack.addWidget(self.layar_kartu_anggota)

        self.layar_filter_cepat = LayarFilterCepat(
            self.conn, navigasi_kartu_callback=self.buka_kartu_anggota, parent=self
        )
        self.stack.addWidget(self.layar_filter_cepat)

        self.layar_laporan = LayarLaporan(self.conn, parent=self)
        self.stack.addWidget(self.layar_laporan)

        self.layar_laporan_bulanan = LayarLaporanBulanan(self.conn, parent=self)
        self.stack.addWidget(self.layar_laporan_bulanan)

        self.layar_laporan_tahunan = LayarLaporanTahunan(self.conn, parent=self)
        self.stack.addWidget(self.layar_laporan_tahunan)

        self.layar_closing = LayarClosing(self.conn, parent=self)
        self.stack.addWidget(self.layar_closing)

        self.layar_impor = LayarImpor(self.conn, parent=self)
        self.stack.addWidget(self.layar_impor)

        self.layar_kas = LayarKas(self.conn, parent=self)
        self.stack.addWidget(self.layar_kas)

        self.stack.setCurrentWidget(self.layar_ringkasan)

        layout_utama.addWidget(self.stack)
        self.setCentralWidget(wadah_utama)

        status_bar = QStatusBar(self)
        status_bar.setFont(QFont("Segoe UI", 10))
        self.setStatusBar(status_bar)
        status_bar.showMessage("Aplikasi siap digunakan.")

    def _buat_menu(self) -> None:
        menu_bar = self.menuBar()

        # Menu Beranda / Navigasi
        menu_navigasi = menu_bar.addMenu("&Navigasi")
        aksi_ringkasan = QAction("&Ringkasan (Beranda)", self)
        aksi_ringkasan.triggered.connect(self._buka_layar_ringkasan)
        aksi_keluar = QAction("&Keluar", self)
        aksi_keluar.triggered.connect(self.close)
        menu_navigasi.addAction(aksi_ringkasan)
        menu_navigasi.addSeparator()
        menu_navigasi.addAction(aksi_keluar)

        # Menu Pencarian & Filter Cepat
        menu_pencarian = menu_bar.addMenu("&Pencarian")
        aksi_filter_cepat = QAction("&Filter Cepat Transaksi", self)
        aksi_filter_cepat.triggered.connect(self._buka_layar_filter_cepat)
        menu_pencarian.addAction(aksi_filter_cepat)

        # Menu Data
        menu_data = menu_bar.addMenu("&Data")
        aksi_anggota = QAction("Data &Anggota", self)
        aksi_anggota.triggered.connect(self._buka_layar_anggota)
        aksi_kas = QAction("Buku &Kas Operasional", self)
        aksi_kas.triggered.connect(self._buka_layar_kas)
        aksi_impor = QAction("&Impor Data Excel", self)
        aksi_impor.triggered.connect(self._buka_layar_impor)
        menu_data.addAction(aksi_anggota)
        menu_data.addAction(aksi_kas)
        menu_data.addAction(aksi_impor)

        # Menu Transaksi
        menu_transaksi = menu_bar.addMenu("&Transaksi")
        aksi_simpanan = QAction("Transaksi &Simpanan", self)
        aksi_simpanan.triggered.connect(self._buka_layar_simpanan)
        aksi_pinjaman = QAction("Data &Pinjaman", self)
        aksi_pinjaman.triggered.connect(self._buka_layar_pinjaman)
        aksi_angsuran = QAction("Pembayaran &Angsuran", self)
        aksi_angsuran.triggered.connect(self._buka_layar_angsuran)
        menu_transaksi.addAction(aksi_simpanan)
        menu_transaksi.addAction(aksi_pinjaman)
        menu_transaksi.addAction(aksi_angsuran)

        # Menu Laporan & Periode
        menu_laporan = menu_bar.addMenu("&Laporan")
        aksi_mingguan = QAction("Laporan &Mingguan", self)
        aksi_mingguan.triggered.connect(self._buka_layar_laporan)
        aksi_bulanan = QAction("Laporan &Bulanan", self)
        aksi_bulanan.triggered.connect(self._buka_layar_laporan_bulanan)
        aksi_tahunan = QAction("Laporan &Tahunan", self)
        aksi_tahunan.triggered.connect(self._buka_layar_laporan_tahunan)
        aksi_closing = QAction("&Closing Akhir Bulan", self)
        aksi_closing.triggered.connect(self._buka_layar_closing)
        menu_laporan.addAction(aksi_mingguan)
        menu_laporan.addAction(aksi_bulanan)
        menu_laporan.addAction(aksi_tahunan)
        menu_laporan.addSeparator()
        menu_laporan.addAction(aksi_closing)

        # Menu Alat / Pemeliharaan
        menu_alat = menu_bar.addMenu("&Alat")
        aksi_backup_manual = QAction("&Backup Sekarang", self)
        aksi_backup_manual.triggered.connect(self._jalankan_backup_manual)
        aksi_pengaturan = QAction("&Pengaturan", self)
        aksi_pengaturan.triggered.connect(lambda: self._pesan_fitur("Pengaturan"))
        menu_alat.addAction(aksi_backup_manual)
        menu_alat.addAction(aksi_pengaturan)

    def _aksi_navigasi_ringkasan(self, aksi: str) -> None:
        if aksi in ("ke_simpanan", "input_simpanan"):
            self._buka_layar_simpanan()
        elif aksi in ("ke_angsuran", "input_angsuran"):
            self._buka_layar_angsuran()
        elif aksi in ("ke_pinjaman", "pinjaman_baru"):
            self._buka_layar_pinjaman()
        elif aksi in ("ke_filter_cepat", "cari_anggota"):
            self._buka_layar_filter_cepat()
        elif aksi in ("ke_laporan", "laporan"):
            self._buka_layar_laporan()
        elif aksi == "ke_laporan_bulanan":
            self._buka_layar_laporan_bulanan()
        elif aksi == "ke_laporan_tahunan":
            self._buka_layar_laporan_tahunan()
        elif aksi in ("ke_closing", "closing"):
            self._buka_layar_closing()

    def _on_cari_global_changed(self, teks: str) -> None:
        t = teks.strip()
        if not t:
            self.list_hasil_cari.clear()
            self.list_hasil_cari.hide()
            return

        hasil = cari_global(self.conn, t, limit=10)
        self.list_hasil_cari.clear()

        if not hasil:
            item = QListWidgetItem("Tidak ditemukan data yang sesuai.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_hasil_cari.addItem(item)
        else:
            for h in hasil:
                teks_item = f"[{h['tipe'].upper()}] {h['judul']} — {h['subjudul']}"
                item = QListWidgetItem(teks_item)
                item.setData(Qt.ItemDataRole.UserRole, h)
                self.list_hasil_cari.addItem(item)

        self.list_hasil_cari.show()

    def _on_hasil_cari_diklik(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return

        self.list_hasil_cari.hide()
        self.input_cari_global.clear()

        anggota_id = data.get("anggota_id")
        if anggota_id:
            self.buka_kartu_anggota(anggota_id)

    def buka_kartu_anggota(self, anggota_id: int) -> None:
        self.stack.setCurrentWidget(self.layar_kartu_anggota)
        self.lbl_breadcrumb.setText("Halaman: Kartu Anggota")
        self.layar_kartu_anggota.muat_anggota(anggota_id)

    def _buka_layar_ringkasan(self) -> None:
        self.stack.setCurrentWidget(self.layar_ringkasan)
        self.lbl_breadcrumb.setText("Halaman: Ringkasan (Beranda)")
        self.layar_ringkasan.muat_data()

    def _buka_layar_closing(self) -> None:
        self.stack.setCurrentWidget(self.layar_closing)
        self.lbl_breadcrumb.setText("Halaman: Closing Akhir Bulan")
        self.layar_closing.muat_riwayat()

    def _buka_layar_kas(self) -> None:
        self.stack.setCurrentWidget(self.layar_kas)
        self.lbl_breadcrumb.setText("Halaman: Buku Kas Operasional")
        self.layar_kas.muat_data()

    def _buka_layar_impor(self) -> None:
        self.stack.setCurrentWidget(self.layar_impor)
        self.lbl_breadcrumb.setText("Halaman: Impor Data Excel")

    def _buka_layar_laporan(self) -> None:
        self.stack.setCurrentWidget(self.layar_laporan)
        self.lbl_breadcrumb.setText("Halaman: Laporan Mingguan")
        self.layar_laporan.muat_data()

    def _buka_layar_laporan_bulanan(self) -> None:
        self.stack.setCurrentWidget(self.layar_laporan_bulanan)
        self.lbl_breadcrumb.setText("Halaman: Laporan Bulanan")
        self.layar_laporan_bulanan.muat_data()

    def _buka_layar_laporan_tahunan(self) -> None:
        self.stack.setCurrentWidget(self.layar_laporan_tahunan)
        self.lbl_breadcrumb.setText("Halaman: Laporan Tahunan")
        self.layar_laporan_tahunan.muat_data()

    def _buka_layar_filter_cepat(self) -> None:
        self.stack.setCurrentWidget(self.layar_filter_cepat)
        self.lbl_breadcrumb.setText("Halaman: Filter Cepat Transaksi")
        self.layar_filter_cepat.muat_data()

    def _buka_layar_anggota(self) -> None:
        self.stack.setCurrentWidget(self.layar_anggota)
        self.lbl_breadcrumb.setText("Halaman: Data Anggota")
        self.layar_anggota.muat_data()

    def _buka_layar_simpanan(self) -> None:
        self.stack.setCurrentWidget(self.layar_simpanan)
        self.lbl_breadcrumb.setText("Halaman: Transaksi Simpanan")
        self.layar_simpanan.muat_data()

    def _buka_layar_pinjaman(self) -> None:
        self.stack.setCurrentWidget(self.layar_pinjaman)
        self.lbl_breadcrumb.setText("Halaman: Data Pinjaman")
        self.layar_pinjaman.muat_data()

    def _buka_layar_angsuran(self) -> None:
        self.stack.setCurrentWidget(self.layar_angsuran)
        self.lbl_breadcrumb.setText("Halaman: Pembayaran Angsuran")
        self.layar_angsuran.muat_data()

    def _pesan_fitur(self, nama_fitur: str) -> None:
        QMessageBox.information(
            self,
            "Informasi",
            f"Fitur '{nama_fitur}' dijadwalkan pada modul berikutnya sesuai urutan pengerjaan di SPEC.md."
        )

    def _jalankan_backup_manual(self) -> None:
        try:
            file_hasil = buat_backup(self.conn)
            if file_hasil:
                self.layar_ringkasan.muat_data()
                QMessageBox.information(
                    self,
                    "Backup Berhasil",
                    f"Salinan database tersimpan dengan aman di folder backup:\n{file_hasil.name}"
                )
        except Exception as err:
            QMessageBox.warning(
                self,
                "Pemberitahuan",
                f"Gagal melakukan backup: {err}"
            )

    def closeEvent(self, event) -> None:
        try:
            buat_backup(self.conn, catat_log=True)
        except Exception:
            pass
        finally:
            event.accept()
