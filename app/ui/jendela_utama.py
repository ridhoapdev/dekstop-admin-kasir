"""
app/ui/jendela_utama.py — Kerangka jendela utama PySide6 dengan stacked widget dan integrasi Buku Kas Operasional.
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QMenuBar, QMenu, QStatusBar, QMessageBox, QStackedWidget,
    QLineEdit, QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QPushButton, QButtonGroup
)
from PySide6.QtGui import QAction, QFont, QCursor
from PySide6.QtCore import Qt
import sqlite3
from typing import Optional, Dict

from app.config import NAMA_APLIKASI, VERSI_APLIKASI
from app.layanan.backup import buat_backup, ambil_info_backup_terakhir
from app.db.repo_kartu_anggota import cari_global
from app.ui.komponen.sidebar import KomponenSidebar
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
from app.ui.layar_barang import LayarBarang
from app.ui.layar_pihak import LayarPihak
from app.ui.layar_pembelian import LayarPembelian
from app.ui.layar_daftar_stok import LayarDaftarStok
from app.ui.layar_ringkasan_toko import LayarRingkasanToko
from app.ui.layar_penjualan import LayarPenjualan
from app.ui.layar_piutang import LayarPiutang
from app.ui.layar_penitipan import LayarPenitipan
from app.ui.layar_kartu_barang import LayarKartuBarang
from app.ui.layar_retur_toko import LayarReturToko
from app.ui.layar_opname_toko import LayarOpnameToko
from app.ui.layar_laporan_toko import LayarLaporanToko
from app.ui.layar_closing_toko import LayarClosingToko


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
        self.resize(1200, 780)
        self.setMinimumSize(1024, 650)

        font_dasar = QFont("Segoe UI", 11)
        self.setFont(font_dasar)

        # Sembunyikan QMenuBar standar karena navigasi sudah dialihkan ke sidebar modern
        self.menuBar().hide()

        # Wadah Utama: Horizontal Split (Kiri: Sidebar Navigasi, Kanan: Konten Utama)
        wadah_induk = QWidget(self)
        layout_induk = QHBoxLayout(wadah_induk)
        layout_induk.setContentsMargins(0, 0, 0, 0)
        layout_induk.setSpacing(0)

        # 1. Sidebar Navigasi Kiri (Modern 3 Level)
        self.sidebar = KomponenSidebar(self.conn, self)
        self.sidebar.navigasi_diminta.connect(self._navigasi_dari_sidebar)
        self.sidebar.mode_lipat_berubah.connect(self._on_sidebar_mode_lipat_berubah)
        self.sidebar_frame = self.sidebar
        layout_induk.addWidget(self.sidebar)

        # 2. Area Konten Kanan
        wadah_konten = QWidget(self)
        wadah_konten.setStyleSheet("background-color: #F8FAFC;")
        layout_konten = QVBoxLayout(wadah_konten)
        layout_konten.setContentsMargins(16, 12, 16, 14)
        layout_konten.setSpacing(10)

        # Header Atas: Tombol Toggle Sidebar, Breadcrumb Indikator Halaman Aktif & Kotak Cari Global
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        # Tombol Buka/Tutup Sidebar (Hamburger Menu)
        self.btn_toggle_sidebar = QPushButton("☰ Menu", self)
        self.btn_toggle_sidebar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_toggle_sidebar.setToolTip("Buka atau tutup bilah samping (sidebar)")
        self.btn_toggle_sidebar.setStyleSheet(
            "background-color: #FFFFFF; border: 1.5px solid #CBD5E1; border-radius: 6px; "
            "padding: 0 14px; min-height: 38px; font-weight: bold; color: #1E293B; outline: none;"
        )
        self.btn_toggle_sidebar.clicked.connect(self._toggle_sidebar)
        top_bar.addWidget(self.btn_toggle_sidebar)

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
        self.input_cari_global.setPlaceholderText("Ketik nama anggota, barang, supplier, penitip, pembeli... (hasil muncul instan)")
        self.input_cari_global.setMinimumHeight(38)
        self.input_cari_global.setStyleSheet(
            "padding: 0 12px; border: 1.5px solid #CBD5E1; border-radius: 6px; background-color: #FFFFFF;"
        )
        self.input_cari_global.textChanged.connect(self._on_cari_global_changed)
        top_bar.addWidget(self.input_cari_global, 1)

        layout_konten.addLayout(top_bar)

        self.list_hasil_cari = QListWidget(self)
        self.list_hasil_cari.setMaximumHeight(160)
        self.list_hasil_cari.setFont(QFont("Segoe UI", 11))
        self.list_hasil_cari.setStyleSheet(
            "border: 1px solid #CBD5E1; border-radius: 4px; background-color: #FFFFFF; selection-background-color: #DBEAFE; selection-color: #1E3A8A;"
        )
        self.list_hasil_cari.hide()
        self.list_hasil_cari.itemClicked.connect(self._on_hasil_cari_diklik)
        layout_konten.addWidget(self.list_hasil_cari)

        # Stacked Widget untuk navigasi layar
        self.stack = QStackedWidget(self)

        self.layar_ringkasan = LayarRingkasan(self.conn, callback_navigasi=self._aksi_navigasi_ringkasan, parent=self)
        scroll_ringkasan = QScrollArea(self)
        scroll_ringkasan.setWidgetResizable(True)
        scroll_ringkasan.setFrameShape(QFrame.Shape.NoFrame)
        scroll_ringkasan.setWidget(self.layar_ringkasan)
        self.stack.addWidget(scroll_ringkasan)

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

        # Modul 13 & 14: Unit Toko
        self.layar_ringkasan_toko = LayarRingkasanToko(
            self.conn, navigasi_callback=self._aksi_navigasi_toko, parent=self
        )
        scroll_ringkasan_toko = QScrollArea(self)
        scroll_ringkasan_toko.setWidgetResizable(True)
        scroll_ringkasan_toko.setFrameShape(QFrame.Shape.NoFrame)
        scroll_ringkasan_toko.setWidget(self.layar_ringkasan_toko)
        self.stack.addWidget(scroll_ringkasan_toko)

        self.layar_penjualan = LayarPenjualan(self.conn, parent=self)
        self.stack.addWidget(self.layar_penjualan)

        self.layar_piutang = LayarPiutang(self.conn, parent=self)
        self.stack.addWidget(self.layar_piutang)

        self.layar_penitipan = LayarPenitipan(self.conn, parent=self)
        self.stack.addWidget(self.layar_penitipan)

        self.layar_barang = LayarBarang(self.conn, parent=self)
        self.stack.addWidget(self.layar_barang)

        self.layar_pihak = LayarPihak(self.conn, parent=self)
        self.stack.addWidget(self.layar_pihak)

        self.layar_pembelian = LayarPembelian(self.conn, parent=self)
        self.stack.addWidget(self.layar_pembelian)

        self.layar_daftar_stok = LayarDaftarStok(self.conn, parent=self)
        self.stack.addWidget(self.layar_daftar_stok)

        # Modul 15: Unit Toko Lanjutan
        self.layar_kartu_barang = LayarKartuBarang(
            self.conn, navigasi_callback=self._aksi_navigasi_toko, parent=self
        )
        self.stack.addWidget(self.layar_kartu_barang)

        self.layar_retur_toko = LayarReturToko(self.conn, parent=self)
        self.stack.addWidget(self.layar_retur_toko)

        self.layar_opname_toko = LayarOpnameToko(self.conn, parent=self)
        self.stack.addWidget(self.layar_opname_toko)

        self.layar_laporan_toko = LayarLaporanToko(self.conn, parent=self)
        self.stack.addWidget(self.layar_laporan_toko)

        self.layar_closing_toko = LayarClosingToko(self.conn, parent=self)
        self.stack.addWidget(self.layar_closing_toko)

        self.stack.setCurrentWidget(self.layar_ringkasan)

        layout_konten.addWidget(self.stack)
        layout_induk.addWidget(wadah_konten, 1)
        self.setCentralWidget(wadah_induk)

        status_bar = QStatusBar(self)
        status_bar.setFont(QFont("Segoe UI", 10))
        self.setStatusBar(status_bar)
        status_bar.showMessage("Aplikasi siap digunakan.")

        # Default sorot tombol ringkasan
        self._sorot_tombol_nav("ringkasan")

    def _navigasi_dari_sidebar(self, kunci: str) -> None:
        """Handler pemetaan dari klik sidebar ke halaman layar target."""
        pemetaan_aksi = {
            "ringkasan": self._buka_layar_ringkasan,
            "anggota": self._buka_layar_anggota,
            "simpanan": self._buka_layar_simpanan,
            "pinjaman": self._buka_layar_pinjaman,
            "angsuran": self._buka_layar_angsuran,
            "kartu_anggota": self._buka_layar_kartu_anggota,
            "kas": self._buka_layar_kas,
            "filter_cepat": self._buka_layar_filter_cepat,
            "penjualan": self._buka_layar_penjualan,
            "piutang": self._buka_layar_piutang,
            "penitipan": self._buka_layar_penitipan,
            "pembelian": self._buka_layar_pembelian,
            "barang": self._buka_layar_barang,
            "pihak": self._buka_layar_pihak,
            "stok": self._buka_layar_daftar_stok,
            "kartu_barang": self._buka_layar_kartu_barang,
            "retur": self._buka_layar_retur_toko,
            "opname": self._buka_layar_opname_toko,
            "laporan_mingguan": self._buka_layar_laporan,
            "laporan_bulanan": self._buka_layar_laporan_bulanan,
            "laporan_tahunan": self._buka_layar_laporan_tahunan,
            "closing_sp": self._buka_layar_closing,
            "laporan_toko": self._buka_layar_laporan_toko,
            "closing_toko": self._buka_layar_closing_toko,
            "impor": self._buka_layar_impor,
        }
        aksi = pemetaan_aksi.get(kunci)
        if aksi:
            aksi()

    def _toggle_sidebar(self) -> None:
        """Mendelegasikan buka/tutup ke komponen sidebar."""
        if hasattr(self, "sidebar") and self.sidebar:
            self.sidebar.toggle_mode_lipat()

    def _on_sidebar_mode_lipat_berubah(self, terlipat: bool) -> None:
        """Memperbarui teks tombol hamburger di top bar ketika mode lipat sidebar berubah."""
        if hasattr(self, "btn_toggle_sidebar") and self.btn_toggle_sidebar:
            self.btn_toggle_sidebar.setText("☰ Buka Menu" if terlipat else "☰ Menu")

    def _sorot_tombol_nav(self, kunci: str) -> None:
        """Memastikan tombol navigasi yang sesuai dengan layar aktif ditandai aktif di sidebar."""
        if hasattr(self, "sidebar") and self.sidebar:
            self.sidebar.set_aktif(kunci)

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

        # Menu Toko (Terpisah dari Simpan Pinjam)
        menu_toko = menu_bar.addMenu("&Toko")
        aksi_ringkasan_toko = QAction("&Ringkasan Dasbor Toko", self)
        aksi_ringkasan_toko.triggered.connect(self._buka_layar_ringkasan_toko)
        aksi_penjualan = QAction("&Kasir Penjualan", self)
        aksi_penjualan.triggered.connect(self._buka_layar_penjualan)
        aksi_piutang = QAction("&Piutang Pembeli", self)
        aksi_piutang.triggered.connect(self._buka_layar_piutang)
        aksi_penitipan = QAction("Penitipan &Barang Harian", self)
        aksi_penitipan.triggered.connect(self._buka_layar_penitipan)
        aksi_pembelian = QAction("&Pembelian (Barang Masuk)", self)
        aksi_pembelian.triggered.connect(self._buka_layar_pembelian)
        aksi_daftar_stok = QAction("Daftar &Stok FIFO Real-Time", self)
        aksi_daftar_stok.triggered.connect(self._buka_layar_daftar_stok)
        aksi_master_barang = QAction("Master &Barang dan Satuan", self)
        aksi_master_barang.triggered.connect(self._buka_layar_barang)
        aksi_pihak = QAction("Data &Pihak (Supplier, Penitip, Pembeli)", self)
        aksi_pihak.triggered.connect(self._buka_layar_pihak)

        menu_toko.addAction(aksi_ringkasan_toko)
        menu_toko.addSeparator()
        menu_toko.addAction(aksi_penjualan)
        menu_toko.addAction(aksi_piutang)
        menu_toko.addAction(aksi_penitipan)
        menu_toko.addSeparator()
        menu_toko.addAction(aksi_pembelian)
        menu_toko.addAction(aksi_daftar_stok)
        menu_toko.addSeparator()

        aksi_retur = QAction("&Retur Barang (Supplier dan Konsumen)", self)
        aksi_retur.triggered.connect(self._buka_layar_retur_toko)
        aksi_opname = QAction("&Stock Opname Toko", self)
        aksi_opname.triggered.connect(self._buka_layar_opname_toko)
        aksi_laporan_toko = QAction("&Laporan Toko", self)
        aksi_laporan_toko.triggered.connect(self._buka_layar_laporan_toko)
        aksi_closing_toko = QAction("&Closing Akhir Bulan Toko", self)
        aksi_closing_toko.triggered.connect(self._buka_layar_closing_toko)

        menu_toko.addAction(aksi_retur)
        menu_toko.addAction(aksi_opname)
        menu_toko.addAction(aksi_laporan_toko)
        menu_toko.addAction(aksi_closing_toko)
        menu_toko.addSeparator()

        menu_toko.addAction(aksi_master_barang)
        menu_toko.addAction(aksi_pihak)

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

    def _aksi_navigasi_toko(self, aksi: str) -> None:
        if aksi in ("ke_penjualan", "buka_kasir"):
            self._buka_layar_penjualan()
        elif aksi in ("ke_piutang", "buka_piutang", "kelola_piutang"):
            self._buka_layar_piutang()
        elif aksi in ("ke_penitipan", "buka_penitipan", "setoran_penitip"):
            self._buka_layar_penitipan()
        elif aksi in ("ke_pembelian", "buka_pembelian", "pembelian"):
            self._buka_layar_pembelian()
        elif aksi in ("ke_stok", "buka_stok"):
            self._buka_layar_daftar_stok()
        elif aksi in ("ke_barang", "buka_barang"):
            self._buka_layar_barang()
        elif aksi in ("ke_pihak", "buka_pihak"):
            self._buka_layar_pihak()
        elif aksi in ("ke_kartu_barang", "buka_kartu_barang"):
            self._buka_layar_kartu_barang()
        elif aksi in ("ke_retur", "buka_retur"):
            self._buka_layar_retur_toko()
        elif aksi in ("ke_opname", "buka_opname"):
            self._buka_layar_opname_toko()
        elif aksi in ("ke_laporan_toko", "buka_laporan_toko"):
            self._buka_layar_laporan_toko()
        elif aksi in ("ke_closing_toko", "buka_closing_toko"):
            self._buka_layar_closing_toko()

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
            return

        barang_id = data.get("barang_id")
        if barang_id:
            self.buka_kartu_barang(barang_id)
            return

        supplier_id = data.get("supplier_id")
        if supplier_id:
            self._buka_layar_pihak()
            return

        penitip_id = data.get("penitip_id")
        if penitip_id:
            self._buka_layar_penitipan()
            return

        pembeli_id = data.get("pembeli_id")
        if pembeli_id:
            self._buka_layar_piutang()
            return

    def buka_kartu_anggota(self, anggota_id: int) -> None:
        self.stack.setCurrentWidget(self.layar_kartu_anggota)
        self.lbl_breadcrumb.setText("Halaman: Kartu Anggota")
        self._sorot_tombol_nav("anggota")
        self.layar_kartu_anggota.muat_anggota(anggota_id)

    def buka_kartu_barang(self, barang_id: int) -> None:
        self.stack.setCurrentWidget(self.layar_kartu_barang)
        self.lbl_breadcrumb.setText("Halaman: Kartu Barang")
        self._sorot_tombol_nav("kartu_barang")
        self.layar_kartu_barang.set_barang_id(barang_id)

    def _buka_layar_kartu_barang(self) -> None:
        self.stack.setCurrentWidget(self.layar_kartu_barang)
        self.lbl_breadcrumb.setText("Halaman: Kartu Barang")
        self._sorot_tombol_nav("kartu_barang")
        self.layar_kartu_barang.muat_data()

    def _buka_layar_retur_toko(self) -> None:
        self.stack.setCurrentWidget(self.layar_retur_toko)
        self.lbl_breadcrumb.setText("Halaman: Retur Toko")
        self._sorot_tombol_nav("retur")
        self.layar_retur_toko.muat_data()

    def _buka_layar_opname_toko(self) -> None:
        self.stack.setCurrentWidget(self.layar_opname_toko)
        self.lbl_breadcrumb.setText("Halaman: Stock Opname Toko")
        self._sorot_tombol_nav("opname")
        self.layar_opname_toko.muat_daftar_sesi()

    def _buka_layar_laporan_toko(self) -> None:
        self.stack.setCurrentWidget(self.layar_laporan_toko)
        self.lbl_breadcrumb.setText("Halaman: Laporan Toko")
        self._sorot_tombol_nav("laporan_toko")
        self.layar_laporan_toko.muat_data()

    def _buka_layar_closing_toko(self) -> None:
        self.stack.setCurrentWidget(self.layar_closing_toko)
        self.lbl_breadcrumb.setText("Halaman: Closing Akhir Bulan Toko")
        self._sorot_tombol_nav("closing_toko")
        self.layar_closing_toko._periksa_periode()

    def _buka_layar_ringkasan(self) -> None:
        self.stack.setCurrentIndex(0)
        self.lbl_breadcrumb.setText("Halaman: Ringkasan (Beranda)")
        self._sorot_tombol_nav("ringkasan")
        self.layar_ringkasan.muat_data()

    def _buka_layar_closing(self) -> None:
        self.stack.setCurrentWidget(self.layar_closing)
        self.lbl_breadcrumb.setText("Halaman: Closing Akhir Bulan")
        self._sorot_tombol_nav("closing_sp")
        self.layar_closing.muat_riwayat()

    def _buka_layar_kas(self) -> None:
        self.stack.setCurrentWidget(self.layar_kas)
        self.lbl_breadcrumb.setText("Halaman: Buku Kas Operasional")
        self._sorot_tombol_nav("kas")
        self.layar_kas.muat_data()

    def _buka_layar_impor(self) -> None:
        self.stack.setCurrentWidget(self.layar_impor)
        self.lbl_breadcrumb.setText("Halaman: Impor Data Excel")
        self._sorot_tombol_nav("impor")

    def _buka_layar_kartu_anggota(self) -> None:
        self.stack.setCurrentWidget(self.layar_kartu_anggota)
        self.lbl_breadcrumb.setText("Halaman: Kartu Anggota")
        self._sorot_tombol_nav("kartu_anggota")
        if self.layar_kartu_anggota.anggota_id_aktif:
            self.layar_kartu_anggota.muat_anggota(self.layar_kartu_anggota.anggota_id_aktif)
        else:
            cur = self.conn.cursor()
            cur.execute("SELECT id FROM anggota ORDER BY id ASC LIMIT 1")
            baris = cur.fetchone()
            if baris:
                self.layar_kartu_anggota.muat_anggota(baris[0])

    def _buka_layar_laporan(self) -> None:
        self.stack.setCurrentWidget(self.layar_laporan)
        self.lbl_breadcrumb.setText("Halaman: Laporan Mingguan Simpan Pinjam")
        self._sorot_tombol_nav("laporan_mingguan")
        self.layar_laporan.muat_data()

    def _buka_layar_laporan_bulanan(self) -> None:
        self.stack.setCurrentWidget(self.layar_laporan_bulanan)
        self.lbl_breadcrumb.setText("Halaman: Laporan Bulanan Simpan Pinjam")
        self._sorot_tombol_nav("laporan_bulanan")
        self.layar_laporan_bulanan.muat_data()

    def _buka_layar_laporan_tahunan(self) -> None:
        self.stack.setCurrentWidget(self.layar_laporan_tahunan)
        self.lbl_breadcrumb.setText("Halaman: Laporan Tahunan Simpan Pinjam")
        self._sorot_tombol_nav("laporan_tahunan")
        self.layar_laporan_tahunan.muat_data()

    def _buka_layar_filter_cepat(self) -> None:
        self.stack.setCurrentWidget(self.layar_filter_cepat)
        self.lbl_breadcrumb.setText("Halaman: Filter Cepat Transaksi")
        self._sorot_tombol_nav("filter_cepat")
        self.layar_filter_cepat.muat_data()

    def _buka_layar_anggota(self) -> None:
        self.stack.setCurrentWidget(self.layar_anggota)
        self.lbl_breadcrumb.setText("Halaman: Data Anggota")
        self._sorot_tombol_nav("anggota")
        self.layar_anggota.muat_data()

    def _buka_layar_simpanan(self) -> None:
        self.stack.setCurrentWidget(self.layar_simpanan)
        self.lbl_breadcrumb.setText("Halaman: Transaksi Simpanan")
        self._sorot_tombol_nav("simpanan")
        self.layar_simpanan.muat_data()

    def _buka_layar_pinjaman(self) -> None:
        self.stack.setCurrentWidget(self.layar_pinjaman)
        self.lbl_breadcrumb.setText("Halaman: Data Pinjaman")
        self._sorot_tombol_nav("pinjaman")
        self.layar_pinjaman.muat_data()

    def _buka_layar_angsuran(self) -> None:
        self.stack.setCurrentWidget(self.layar_angsuran)
        self.lbl_breadcrumb.setText("Halaman: Pembayaran Angsuran")
        self._sorot_tombol_nav("angsuran")
        self.layar_angsuran.muat_data()

    def _buka_layar_ringkasan_toko(self) -> None:
        self.stack.setCurrentIndex(13)
        self.lbl_breadcrumb.setText("Halaman: Dasbor Ringkasan Toko")
        self._sorot_tombol_nav("ringkasan_toko")
        self.layar_ringkasan_toko.muat_data()

    def _buka_layar_penjualan(self) -> None:
        self.stack.setCurrentWidget(self.layar_penjualan)
        self.lbl_breadcrumb.setText("Halaman: Kasir Penjualan Toko")
        self._sorot_tombol_nav("penjualan")
        self.layar_penjualan.muat_data()

    def _buka_layar_piutang(self) -> None:
        self.stack.setCurrentWidget(self.layar_piutang)
        self.lbl_breadcrumb.setText("Halaman: Piutang Pembeli Toko")
        self._sorot_tombol_nav("piutang")
        self.layar_piutang.muat_data()

    def _buka_layar_penitipan(self) -> None:
        self.stack.setCurrentWidget(self.layar_penitipan)
        self.lbl_breadcrumb.setText("Halaman: Penitipan Barang Harian")
        self._sorot_tombol_nav("penitipan")
        self.layar_penitipan.muat_data()

    def _buka_layar_pembelian(self) -> None:
        self.stack.setCurrentWidget(self.layar_pembelian)
        self.lbl_breadcrumb.setText("Halaman: Pembelian Toko")
        self._sorot_tombol_nav("pembelian")
        self.layar_pembelian.muat_data()

    def _buka_layar_daftar_stok(self) -> None:
        self.stack.setCurrentWidget(self.layar_daftar_stok)
        self.lbl_breadcrumb.setText("Halaman: Daftar Stok FIFO Toko")
        self._sorot_tombol_nav("stok")
        self.layar_daftar_stok.muat_data()

    def _buka_layar_barang(self) -> None:
        self.stack.setCurrentWidget(self.layar_barang)
        self.lbl_breadcrumb.setText("Halaman: Master Barang Toko")
        self._sorot_tombol_nav("barang")
        self.layar_barang.muat_data()

    def _buka_layar_pihak(self) -> None:
        self.stack.setCurrentWidget(self.layar_pihak)
        self.lbl_breadcrumb.setText("Halaman: Pihak Terkait Toko")
        self._sorot_tombol_nav("pihak")
        self.layar_pihak.muat_data()

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
