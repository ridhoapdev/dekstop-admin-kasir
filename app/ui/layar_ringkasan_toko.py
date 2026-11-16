"""
app/ui/layar_ringkasan_toko.py — Layar Dasbor Utama Unit Toko (Ringkasan Toko).
Menampilkan 6 kartu metrik bersih:
- Penjualan Hari Ini
- Laba Kotor Hari Ini
- Posisi Kas Toko Saat Ini
- Total Piutang Pembeli
- Hutang ke Penitip Hari Ini
- Nota Lewat Jatuh Tempo & Stok di Bawah Minimum
Aksi Cepat: Buka Kasir Penjualan, Penerimaan Piutang, Setoran Penitip Sore, Pembelian.
Realtime update via bus_sinyal.
"""
import sqlite3
from typing import Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QMessageBox
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt

from app.db.repo_ringkasan_toko import ambil_ringkasan_dasbor_toko
from app.util.format import format_rupiah, format_tanggal_indo
from app.layanan.bus_sinyal import langganan, lepas_langganan


class KartuMetrikToko(QFrame):
    """Komponen kartu metrik toko dengan font besar dan kontras jelas."""

    def __init__(self, judul: str, nilai_awal: str, warna_aksen: str = "#2563EB", parent=None):
        super().__init__(parent)
        self.setObjectName("KartuMetrikToko")
        self.setStyleSheet(
            f"QFrame#KartuMetrikToko {{ "
            f"    background-color: #FFFFFF; "
            f"    border: none; "
            f"    border-left: 6px solid {warna_aksen}; "
            f"    border-radius: 8px; "
            f"}} "
            f"QLabel {{ "
            f"    border: none; "
            f"    background: transparent; "
            f"}}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(6)

        self.lbl_judul = QLabel(judul, self)
        self.lbl_judul.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_judul.setStyleSheet("color: #6B7280; font-size: 11pt; font-weight: bold;")
        lay.addWidget(self.lbl_judul)

        self.lbl_nilai = QLabel(nilai_awal, self)
        self.lbl_nilai.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.lbl_nilai.setStyleSheet(f"color: {warna_aksen}; font-size: 18pt; font-weight: bold;")
        lay.addWidget(self.lbl_nilai)

    def set_nilai(self, nilai: str) -> None:
        self.lbl_nilai.setText(nilai)


class LayarRingkasanToko(QWidget):
    """Layar Ringkasan Toko (Dasbor Halaman Awal Toko)."""

    def __init__(self, conn: sqlite3.Connection, navigasi_callback: Optional[Callable[[str], None]] = None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.navigasi_cb = navigasi_callback
        self._inisialisasi_ui()

        # Langganan event bus real-time
        langganan("penjualan_berubah", self.muat_data)
        langganan("piutang_berubah", self.muat_data)
        langganan("penitipan_berubah", self.muat_data)
        langganan("stok_berubah", self.muat_data)
        langganan("kas_toko_berubah", self.muat_data)

    def closeEvent(self, event):
        lepas_langganan("penjualan_berubah", self.muat_data)
        lepas_langganan("piutang_berubah", self.muat_data)
        lepas_langganan("penitipan_berubah", self.muat_data)
        lepas_langganan("stok_berubah", self.muat_data)
        lepas_langganan("kas_toko_berubah", self.muat_data)
        super().closeEvent(event)

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(14)

        # Header Selamat Datang Toko
        header_lay = QHBoxLayout()
        lbl_judul = QLabel("Dasbor Utama Unit Toko Retail", self)
        lbl_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        lbl_judul.setStyleSheet("color: #1E3A8A;")
        header_lay.addWidget(lbl_judul)

        header_lay.addStretch()

        btn_refresh = QPushButton("Segarkan Data", self)
        btn_refresh.setMinimumHeight(38)
        btn_refresh.setStyleSheet(
            "background-color: #EFF6FF; color: #1D4ED8; border: 1.5px solid #93C5FD; "
            "font-weight: bold; border-radius: 6px; padding: 0 16px; outline: none;"
        )
        btn_refresh.clicked.connect(self.muat_data)
        header_lay.addWidget(btn_refresh)
        layout.addLayout(header_lay)

        # Grid Kartu Metrik
        grid = QGridLayout()
        grid.setSpacing(14)

        self.k_penjualan = KartuMetrikToko("Penjualan Hari Ini", "Rp 0", "#10B981", self)
        self.k_laba = KartuMetrikToko("Laba Kotor Hari Ini", "Rp 0", "#059669", self)
        self.k_kas = KartuMetrikToko("Posisi Kas Toko Saat Ini", "Rp 0", "#2563EB", self)
        self.k_piutang = KartuMetrikToko("Total Piutang Pembeli", "Rp 0", "#D97706", self)
        self.k_penitip = KartuMetrikToko("Hutang ke Penitip Hari Ini", "Rp 0", "#DC2626", self)
        self.k_peringatan = KartuMetrikToko("Perhatian dan Peringatan", "0 Nota Telat | 0 Stok Min", "#7C3AED", self)

        grid.addWidget(self.k_penjualan, 0, 0)
        grid.addWidget(self.k_laba, 0, 1)
        grid.addWidget(self.k_kas, 0, 2)
        grid.addWidget(self.k_piutang, 1, 0)
        grid.addWidget(self.k_penitip, 1, 1)
        grid.addWidget(self.k_peringatan, 1, 2)

        layout.addLayout(grid)

        # Tombol Aksi Cepat Besar
        lbl_aksi = QLabel("Aksi Cepat Operasional Toko:", self)
        lbl_aksi.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_aksi.setStyleSheet("margin-top: 10px; color: #1F2937;")
        layout.addWidget(lbl_aksi)

        aksi_grid = QHBoxLayout()
        aksi_grid.setSpacing(12)

        btn_kasir = QPushButton("Buka Kasir Penjualan", self)
        btn_kasir.setMinimumHeight(55)
        btn_kasir.setStyleSheet("background-color: #10B981; color: white; font-size: 13pt; font-weight: bold; border-radius: 6px; border: none; outline: none;")
        btn_kasir.clicked.connect(lambda: self._aksi("buka_kasir"))

        btn_piutang = QPushButton("Kelola Piutang Pembeli", self)
        btn_piutang.setMinimumHeight(55)
        btn_piutang.setStyleSheet("background-color: #F59E0B; color: white; font-size: 13pt; font-weight: bold; border-radius: 6px; border: none; outline: none;")
        btn_piutang.clicked.connect(lambda: self._aksi("kelola_piutang"))

        btn_setoran = QPushButton("Setoran Penitip (Sore)", self)
        btn_setoran.setMinimumHeight(55)
        btn_setoran.setStyleSheet("background-color: #6366F1; color: white; font-size: 13pt; font-weight: bold; border-radius: 6px; border: none; outline: none;")
        btn_setoran.clicked.connect(lambda: self._aksi("setoran_penitip"))

        btn_beli = QPushButton("Pembelian (Barang Masuk)", self)
        btn_beli.setMinimumHeight(55)
        btn_beli.setStyleSheet("background-color: #2563EB; color: white; font-size: 13pt; font-weight: bold; border-radius: 6px; border: none; outline: none;")
        btn_beli.clicked.connect(lambda: self._aksi("pembelian"))

        aksi_grid.addWidget(btn_kasir)
        aksi_grid.addWidget(btn_piutang)
        aksi_grid.addWidget(btn_setoran)
        aksi_grid.addWidget(btn_beli)
        layout.addLayout(aksi_grid)

        layout.addStretch()
        self.muat_data()

    def muat_data(self) -> None:
        data = ambil_ringkasan_dasbor_toko(self.conn)
        self.k_penjualan.set_nilai(format_rupiah(data["penjualan_hari_ini"]))
        self.k_laba.set_nilai(format_rupiah(data["laba_kotor_hari_ini"]))
        self.k_kas.set_nilai(format_rupiah(data["kas_toko"]))
        self.k_piutang.set_nilai(format_rupiah(data["total_piutang"]))
        self.k_penitip.set_nilai(format_rupiah(data["hutang_penitip"]))

        str_perhatian = f"{data['jumlah_nota_telat']} Nota Telat | {data['jumlah_stok_menipis']} Stok Min"
        self.k_peringatan.set_nilai(str_perhatian)

    def _aksi(self, nama: str) -> None:
        if self.navigasi_cb:
            self.navigasi_cb(nama)
