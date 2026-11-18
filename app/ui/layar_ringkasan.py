"""
app/ui/layar_ringkasan.py — Layar Ringkasan / Dashboard Terpadu Halaman Awal.
Mengintegrasikan Unit Simpan Pinjam dan Unit Toko Retail dalam satu Dashboard Utuh,
informatif, akurat, dan bersih tanpa kesalahan logika pemisahan data.
"""
import sqlite3
import calendar
from datetime import date
from typing import Dict, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QGroupBox, QDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox
)
from PySide6.QtGui import (
    QFont, QCursor, QIcon, QPixmap, QPainter, QColor, QPen
)
from PySide6.QtCore import Qt, QRectF, QSize

from app.db.repo_ringkasan import ambil_ringkasan_dashboard
from app.db.repo_ringkasan_toko import ambil_ringkasan_dasbor_toko
from app.layanan.backup import ambil_info_backup_terakhir
from app.layanan.bus_sinyal import langganan, lepas_langganan
from app.util.format import format_rupiah, format_tanggal_indo


def _buat_ikon_vektor(nama: str, warna_hex: str = "#FFFFFF") -> QIcon:
    """Membuat ikon vektor 20x20 profesional untuk tombol aksi cepat."""
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(warna_hex))
    pen.setWidthF(1.8)
    p.setPen(pen)

    if nama == "simpanan":
        p.drawRoundedRect(QRectF(2, 4, 16, 12), 2, 2)
        p.drawEllipse(QRectF(8, 8, 4, 4))
    elif nama == "pinjaman":
        p.drawRoundedRect(QRectF(3, 2, 14, 16), 2, 2)
        p.drawLine(10, 6, 10, 14)
        p.drawLine(6, 10, 14, 10)
    elif nama == "angsuran":
        p.drawRoundedRect(QRectF(3, 2, 14, 16), 2, 2)
        p.drawLine(6, 6, 14, 6)
        p.drawLine(6, 10, 14, 10)
        p.drawLine(6, 14, 11, 14)
    elif nama == "kasir":
        p.drawRoundedRect(QRectF(2, 4, 16, 12), 2, 2)
        p.drawLine(2, 9, 18, 9)
        p.drawLine(5, 12, 7, 12)
        p.drawLine(9, 12, 11, 12)
        p.drawLine(13, 12, 15, 12)
    elif nama == "piutang":
        p.drawRoundedRect(QRectF(2, 3, 16, 14), 2, 2)
        p.drawLine(5, 10, 15, 10)
        p.drawLine(11, 6, 15, 10)
        p.drawLine(11, 14, 15, 10)
    elif nama == "penitipan":
        p.drawRoundedRect(QRectF(2, 6, 16, 11), 2, 2)
        p.drawArc(QRectF(6, 2, 8, 8), 0, 180 * 16)
    elif nama == "pembelian":
        p.drawRoundedRect(QRectF(3, 4, 14, 13), 2, 2)
        p.drawLine(10, 7, 10, 13)
        p.drawLine(7, 10, 13, 10)
    elif nama == "laporan":
        p.drawRoundedRect(QRectF(3, 2, 14, 16), 2, 2)
        p.drawLine(6, 14, 6, 10)
        p.drawLine(10, 14, 10, 7)
        p.drawLine(14, 14, 14, 5)
    elif nama == "closing":
        p.drawEllipse(QRectF(2, 2, 16, 16))
        p.drawLine(10, 5, 10, 10)
        p.drawLine(10, 10, 14, 12)
    p.end()
    return QIcon(pix)


class LayarRingkasan(QWidget):
    """
    Layar Ringkasan Terpadu (Single Unified Dashboard).
    Menggabungkan metrik Simpan Pinjam dan Unit Toko dengan batasan domain yang jelas.
    """

    def __init__(self, conn: sqlite3.Connection, callback_navigasi, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.navigasi = callback_navigasi
        self.data_sp = {}
        self.data_toko = {}
        self._inisialisasi_ui()

        # Langganan perubahan toko secara realtime
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
        self.setFont(QFont("Segoe UI", 11))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 24)
        layout.setSpacing(16)

        # 1. Header Ringkasan & Backup Terakhir
        header_layout = QHBoxLayout()
        header_teks = QVBoxLayout()
        header_teks.setSpacing(2)

        label_judul = QLabel("Dashboard Terpadu Koperasi dan Toko", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        label_judul.setStyleSheet("color: #0F172A;")
        header_teks.addWidget(label_judul)

        label_sub = QLabel("Ringkasan eksekutif arus kas, transaksi harian, dan kesehatan operasional", self)
        label_sub.setFont(QFont("Segoe UI", 9.5))
        label_sub.setStyleSheet("color: #64748B;")
        header_teks.addWidget(label_sub)

        header_layout.addLayout(header_teks, 1)

        self.lbl_backup_info = QLabel("Backup terakhir: -", self)
        self.lbl_backup_info.setStyleSheet("color: #64748B; font-size: 10pt; font-weight: 500;")
        header_layout.addWidget(self.lbl_backup_info)

        btn_segarkan = QPushButton("🔄 Segarkan Data", self)
        btn_segarkan.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_segarkan.setMinimumHeight(38)
        btn_segarkan.setStyleSheet("""
            QPushButton {
                background-color: #EFF6FF;
                color: #1D4ED8;
                border: 1.5px solid #93C5FD;
                font-weight: bold;
                border-radius: 6px;
                padding: 0 16px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #DBEAFE;
            }
        """)
        btn_segarkan.clicked.connect(self.muat_data)
        header_layout.addWidget(btn_segarkan)

        layout.addLayout(header_layout)

        # 2. Kotak Pengingat Penting (Banner Alert)
        self.box_pengingat = QWidget(self)
        self.layout_pengingat = QVBoxLayout(self.box_pengingat)
        self.layout_pengingat.setContentsMargins(0, 0, 0, 0)
        self.layout_pengingat.setSpacing(6)
        layout.addWidget(self.box_pengingat)

        # 3. Baris Ringkasan Arus Kas Utama (Koperasi SP + Toko Retail + Konsolidasi)
        lbl_kas_sec = QLabel("POSISI KAS DAN LIKUIDITAS", self)
        lbl_kas_sec.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_kas_sec.setStyleSheet("color: #475569; letter-spacing: 0.5px;")
        layout.addWidget(lbl_kas_sec)

        grid_kas = QGridLayout()
        grid_kas.setSpacing(12)

        self.card_kas_sp = self._buat_kartu_metrik(
            "KAS OPERASIONAL SIMPAN PINJAM", "Rp 0", "#2563EB", "#EFF6FF"
        )
        self.card_kas_toko = self._buat_kartu_metrik(
            "KAS OPERASIONAL UNIT TOKO", "Rp 0", "#0D9488", "#F0FDFA"
        )
        self.card_kas_total = self._buat_kartu_metrik(
            "TOTAL KAS KONSOLIDASI", "Rp 0", "#1E293B", "#F8FAFC"
        )

        grid_kas.addWidget(self.card_kas_sp["widget"], 0, 0)
        grid_kas.addWidget(self.card_kas_toko["widget"], 0, 1)
        grid_kas.addWidget(self.card_kas_total["widget"], 0, 2)
        layout.addLayout(grid_kas)

        # 4. Dua Kolom Utama: Kiri (Simpan Pinjam), Kanan (Unit Toko)
        split_unit_lay = QHBoxLayout()
        split_unit_lay.setSpacing(16)

        # === KOLOM KIRI: SIMPAN PINJAM ===
        panel_sp = QFrame(self)
        panel_sp.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
        """)
        lay_sp = QVBoxLayout(panel_sp)
        lay_sp.setContentsMargins(16, 14, 16, 16)
        lay_sp.setSpacing(12)

        # Header Kolom SP
        hdr_sp = QHBoxLayout()
        lbl_hdr_sp = QLabel("Unit Simpan Pinjam", panel_sp)
        lbl_hdr_sp.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_hdr_sp.setStyleSheet("color: #1E3A8A; border: none;")
        hdr_sp.addWidget(lbl_hdr_sp)
        hdr_sp.addStretch()
        tag_sp = QLabel("Aktivitas Hari Ini", panel_sp)
        tag_sp.setFont(QFont("Segoe UI", 8.5, QFont.Weight.Bold))
        tag_sp.setStyleSheet("background-color: #EFF6FF; color: #1D4ED8; padding: 2px 8px; border-radius: 4px; border: 1px solid #BFDBFE;")
        hdr_sp.addWidget(tag_sp)
        lay_sp.addLayout(hdr_sp)

        # Kartu-kartu Metrik SP
        grid_sp_metrik = QGridLayout()
        grid_sp_metrik.setSpacing(10)

        self.card_simpanan = self._buat_kartu_metrik(
            "Simpanan Masuk Hari Ini", "Rp 0", "#059669", "#ECFDF5"
        )
        self.card_angsuran = self._buat_kartu_metrik(
            "Angsuran Masuk Hari Ini", "Rp 0", "#2563EB", "#EFF6FF"
        )
        self.card_pinjaman = self._buat_kartu_metrik(
            "Pinjaman Cair Hari Ini", "Rp 0", "#D97706", "#FFFBEB"
        )
        self.card_admin = self._buat_kartu_metrik(
            "Biaya Admin Diterima", "Rp 0", "#0D9488", "#F0FDFA"
        )

        grid_sp_metrik.addWidget(self.card_simpanan["widget"], 0, 0)
        grid_sp_metrik.addWidget(self.card_angsuran["widget"], 0, 1)
        grid_sp_metrik.addWidget(self.card_pinjaman["widget"], 1, 0)
        grid_sp_metrik.addWidget(self.card_admin["widget"], 1, 1)
        lay_sp.addLayout(grid_sp_metrik)

        # Perhatian & Jatuh Tempo SP
        box_tempo_sp = QFrame(panel_sp)
        box_tempo_sp.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px;")
        lay_tempo_sp = QHBoxLayout(box_tempo_sp)
        lay_tempo_sp.setContentsMargins(12, 10, 12, 10)

        info_tempo_v = QVBoxLayout()
        info_tempo_v.setSpacing(2)
        lbl_tempo_title = QLabel("Jatuh Tempo 7 Hari ke Depan", box_tempo_sp)
        lbl_tempo_title.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        lbl_tempo_title.setStyleSheet("color: #64748B; border: none;")
        info_tempo_v.addWidget(lbl_tempo_title)
        self.lbl_tempo_info = QLabel("0 Angsuran", box_tempo_sp)
        self.lbl_tempo_info.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_tempo_info.setStyleSheet("color: #1E293B; border: none;")
        info_tempo_v.addWidget(self.lbl_tempo_info)
        lay_tempo_sp.addLayout(info_tempo_v, 1)

        btn_lihat_tempo = QPushButton("Lihat", box_tempo_sp)
        btn_lihat_tempo.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_lihat_tempo.setStyleSheet("""
            QPushButton {
                background-color: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE;
                font-weight: bold; border-radius: 5px; padding: 4px 12px; font-size: 9.5pt;
            }
            QPushButton:hover { background-color: #DBEAFE; }
        """)
        btn_lihat_tempo.clicked.connect(self._lihat_daftar_tempo)
        lay_tempo_sp.addWidget(btn_lihat_tempo)
        lay_sp.addWidget(box_tempo_sp)

        # Anggota Menunggak SP
        box_tunggak_sp = QFrame(panel_sp)
        box_tunggak_sp.setStyleSheet("background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px;")
        lay_tunggak_sp = QHBoxLayout(box_tunggak_sp)
        lay_tunggak_sp.setContentsMargins(12, 10, 12, 10)

        info_tunggak_v = QVBoxLayout()
        info_tunggak_v.setSpacing(2)
        lbl_tunggak_title = QLabel("Anggota Menunggak", box_tunggak_sp)
        lbl_tunggak_title.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        lbl_tunggak_title.setStyleSheet("color: #991B1B; border: none;")
        info_tunggak_v.addWidget(lbl_tunggak_title)
        self.lbl_menunggak_info = QLabel("0 Anggota", box_tunggak_sp)
        self.lbl_menunggak_info.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_menunggak_info.setStyleSheet("color: #DC2626; border: none;")
        info_tunggak_v.addWidget(self.lbl_menunggak_info)
        lay_tunggak_sp.addLayout(info_tunggak_v, 1)

        btn_lihat_tunggak = QPushButton("Lihat", box_tunggak_sp)
        btn_lihat_tunggak.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_lihat_tunggak.setStyleSheet("""
            QPushButton {
                background-color: #FEE2E2; color: #991B1B; border: 1px solid #F87171;
                font-weight: bold; border-radius: 5px; padding: 4px 12px; font-size: 9.5pt;
            }
            QPushButton:hover { background-color: #FCA5A5; }
        """)
        btn_lihat_tunggak.clicked.connect(self._lihat_daftar_menunggak)
        lay_tunggak_sp.addWidget(btn_lihat_tunggak)
        lay_sp.addWidget(box_tunggak_sp)

        # Tombol Aksi Cepat SP
        lbl_aksi_sp = QLabel("Aksi Cepat Simpan Pinjam:", panel_sp)
        lbl_aksi_sp.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_aksi_sp.setStyleSheet("color: #334155; border: none; margin-top: 4px;")
        lay_sp.addWidget(lbl_aksi_sp)

        grid_btn_sp = QGridLayout()
        grid_btn_sp.setSpacing(8)

        btn_aksi_simpanan = self._buat_tombol_aksi("Setor Simpanan", "#2563EB", "simpanan")
        btn_aksi_simpanan.clicked.connect(lambda: self.navigasi("ke_simpanan"))
        grid_btn_sp.addWidget(btn_aksi_simpanan, 0, 0)

        btn_aksi_angsuran = self._buat_tombol_aksi("Bayar Angsuran", "#059669", "angsuran")
        btn_aksi_angsuran.clicked.connect(lambda: self.navigasi("ke_angsuran"))
        grid_btn_sp.addWidget(btn_aksi_angsuran, 0, 1)

        btn_aksi_pinjaman = self._buat_tombol_aksi("Pinjaman Baru", "#D97706", "pinjaman")
        btn_aksi_pinjaman.clicked.connect(lambda: self.navigasi("ke_pinjaman"))
        grid_btn_sp.addWidget(btn_aksi_pinjaman, 1, 0)

        btn_aksi_filter = self._buat_tombol_aksi("Filter Transaksi", "#4F46E5", "filter")
        btn_aksi_filter.clicked.connect(lambda: self.navigasi("ke_filter_cepat"))
        grid_btn_sp.addWidget(btn_aksi_filter, 1, 1)

        lay_sp.addLayout(grid_btn_sp)
        split_unit_lay.addWidget(panel_sp, 1)

        # === KOLOM KANAN: UNIT TOKO RETAIL ===
        panel_toko = QFrame(self)
        panel_toko.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
        """)
        lay_toko = QVBoxLayout(panel_toko)
        lay_toko.setContentsMargins(16, 14, 16, 16)
        lay_toko.setSpacing(12)

        # Header Kolom Toko
        hdr_toko = QHBoxLayout()
        lbl_hdr_toko = QLabel("Unit Toko Retail", panel_toko)
        lbl_hdr_toko.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_hdr_toko.setStyleSheet("color: #065F46; border: none;")
        hdr_toko.addWidget(lbl_hdr_toko)
        hdr_toko.addStretch()
        tag_toko = QLabel("Operasional Toko", panel_toko)
        tag_toko.setFont(QFont("Segoe UI", 8.5, QFont.Weight.Bold))
        tag_toko.setStyleSheet("background-color: #ECFDF5; color: #059669; padding: 2px 8px; border-radius: 4px; border: 1px solid #A7F3D0;")
        hdr_toko.addWidget(tag_toko)
        lay_toko.addLayout(hdr_toko)

        # Kartu-kartu Metrik Toko
        grid_toko_metrik = QGridLayout()
        grid_toko_metrik.setSpacing(10)

        self.card_penjualan = self._buat_kartu_metrik(
            "Penjualan Hari Ini", "Rp 0", "#059669", "#ECFDF5"
        )
        self.card_laba = self._buat_kartu_metrik(
            "Laba Kotor Hari Ini", "Rp 0", "#047857", "#ECFDF5"
        )
        self.card_piutang = self._buat_kartu_metrik(
            "Total Piutang Pembeli", "Rp 0", "#D97706", "#FFFBEB"
        )
        self.card_penitip = self._buat_kartu_metrik(
            "Hutang Penitip Terkini", "Rp 0", "#DC2626", "#FEF2F2"
        )

        grid_toko_metrik.addWidget(self.card_penjualan["widget"], 0, 0)
        grid_toko_metrik.addWidget(self.card_laba["widget"], 0, 1)
        grid_toko_metrik.addWidget(self.card_piutang["widget"], 1, 0)
        grid_toko_metrik.addWidget(self.card_penitip["widget"], 1, 1)
        lay_toko.addLayout(grid_toko_metrik)

        # Peringatan Piutang Jatuh Tempo & Stok Minimum Toko
        box_peringatan_toko = QFrame(panel_toko)
        box_peringatan_toko.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px;")
        lay_per_toko = QHBoxLayout(box_peringatan_toko)
        lay_per_toko.setContentsMargins(12, 10, 12, 10)

        info_per_v = QVBoxLayout()
        info_per_v.setSpacing(2)
        lbl_per_title = QLabel("Status Nota Telat dan Stok Kritis", box_peringatan_toko)
        lbl_per_title.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        lbl_per_title.setStyleSheet("color: #64748B; border: none;")
        info_per_v.addWidget(lbl_per_title)
        self.lbl_perhatian_toko = QLabel("0 Nota Telat | 0 Stok Min", box_peringatan_toko)
        self.lbl_perhatian_toko.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_perhatian_toko.setStyleSheet("color: #7C3AED; border: none;")
        info_per_v.addWidget(self.lbl_perhatian_toko)
        lay_per_toko.addLayout(info_per_v, 1)

        btn_cek_stok = QPushButton("Cek Stok", box_peringatan_toko)
        btn_cek_stok.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn_cek_stok.setStyleSheet("""
            QPushButton {
                background-color: #F3E8FF; color: #7E22CE; border: 1px solid #D8B4FE;
                font-weight: bold; border-radius: 5px; padding: 4px 12px; font-size: 9.5pt;
            }
            QPushButton:hover { background-color: #E9D5FF; }
        """)
        btn_cek_stok.clicked.connect(lambda: self.navigasi("ke_stok"))
        lay_per_toko.addWidget(btn_cek_stok)
        lay_toko.addWidget(box_peringatan_toko)

        # Spacer sejajar dengan kolom kiri
        box_dummy = QFrame(panel_toko)
        box_dummy.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px;")
        lay_dummy = QHBoxLayout(box_dummy)
        lay_dummy.setContentsMargins(12, 10, 12, 10)
        lbl_info_toko_ringkas = QLabel("Kelola penjualan kasir, stok FIFO, dan titipan barang harian.", box_dummy)
        lbl_info_toko_ringkas.setStyleSheet("color: #64748B; font-size: 9pt; border: none;")
        lay_dummy.addWidget(lbl_info_toko_ringkas)
        lay_toko.addWidget(box_dummy)

        # Tombol Aksi Cepat Toko
        lbl_aksi_toko = QLabel("Aksi Cepat Operasional Toko:", panel_toko)
        lbl_aksi_toko.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_aksi_toko.setStyleSheet("color: #334155; border: none; margin-top: 4px;")
        lay_toko.addWidget(lbl_aksi_toko)

        grid_btn_toko = QGridLayout()
        grid_btn_toko.setSpacing(8)

        btn_kasir = self._buat_tombol_aksi("Buka Kasir", "#059669", "kasir")
        btn_kasir.clicked.connect(lambda: self.navigasi("ke_penjualan"))
        grid_btn_toko.addWidget(btn_kasir, 0, 0)

        btn_piutang = self._buat_tombol_aksi("Piutang Pembeli", "#D97706", "piutang")
        btn_piutang.clicked.connect(lambda: self.navigasi("ke_piutang"))
        grid_btn_toko.addWidget(btn_piutang, 0, 1)

        btn_setoran = self._buat_tombol_aksi("Setoran Penitip", "#4F46E5", "penitipan")
        btn_setoran.clicked.connect(lambda: self.navigasi("ke_penitipan"))
        grid_btn_toko.addWidget(btn_setoran, 1, 0)

        btn_beli = self._buat_tombol_aksi("Pembelian Stok", "#2563EB", "pembelian")
        btn_beli.clicked.connect(lambda: self.navigasi("ke_pembelian"))
        grid_btn_toko.addWidget(btn_beli, 1, 1)

        lay_toko.addLayout(grid_btn_toko)
        split_unit_lay.addWidget(panel_toko, 1)

        layout.addLayout(split_unit_lay)

        # 5. Baris Navigasi Laporan & Penutupan Buku
        lbl_laporan_sec = QLabel("LAPORAN DAN PENUTUPAN BUKU (CLOSING)", self)
        lbl_laporan_sec.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_laporan_sec.setStyleSheet("color: #475569; letter-spacing: 0.5px; margin-top: 4px;")
        layout.addWidget(lbl_laporan_sec)

        grid_lap = QHBoxLayout()
        grid_lap.setSpacing(10)

        btn_lap_mingguan = self._buat_tombol_aksi("Laporan Mingguan SP", "#0D9488", "laporan")
        btn_lap_mingguan.clicked.connect(lambda: self.navigasi("ke_laporan"))
        grid_lap.addWidget(btn_lap_mingguan)

        btn_lap_bulanan = self._buat_tombol_aksi("Laporan Bulanan SP", "#0284C7", "laporan")
        btn_lap_bulanan.clicked.connect(lambda: self.navigasi("ke_laporan_bulanan"))
        grid_lap.addWidget(btn_lap_bulanan)

        btn_lap_toko = self._buat_tombol_aksi("Laporan Toko Retail", "#059669", "laporan")
        btn_lap_toko.clicked.connect(lambda: self.navigasi("ke_laporan_toko"))
        grid_lap.addWidget(btn_lap_toko)

        btn_closing_sp = self._buat_tombol_aksi("Closing SP Bulanan", "#7C3AED", "closing")
        btn_closing_sp.clicked.connect(lambda: self.navigasi("ke_closing"))
        grid_lap.addWidget(btn_closing_sp)

        btn_closing_toko = self._buat_tombol_aksi("Closing Unit Toko", "#9333EA", "closing")
        btn_closing_toko.clicked.connect(lambda: self.navigasi("ke_closing_toko"))
        grid_lap.addWidget(btn_closing_toko)

        layout.addLayout(grid_lap)

        self.muat_data()

    def _buat_kartu_metrik(self, judul: str, nilai_awal: str, warna_teks: str, bg_color: str) -> dict:
        """Membuat komponen kartu metrik yang bersih, rapi, dan mudah dibaca."""
        box = QFrame(self)
        box.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
        """)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(14, 12, 14, 12)
        box_layout.setSpacing(4)

        lay_h = QHBoxLayout()
        lay_h.setContentsMargins(0, 0, 0, 0)
        lay_h.setSpacing(6)

        dot = QFrame(box)
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background-color: {warna_teks}; border-radius: 4px; border: none;")
        lay_h.addWidget(dot)

        lbl_j = QLabel(judul, box)
        lbl_j.setFont(QFont("Segoe UI", 9.5, QFont.Weight.DemiBold))
        lbl_j.setStyleSheet("color: #64748B; border: none; background: transparent;")
        lay_h.addWidget(lbl_j, 1)
        box_layout.addLayout(lay_h)

        lbl_v = QLabel(nilai_awal, box)
        lbl_v.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        lbl_v.setStyleSheet(f"color: {warna_teks}; border: none; background: transparent;")
        box_layout.addWidget(lbl_v)

        return {"widget": box, "nilai_label": lbl_v}

    def _buat_tombol_aksi(self, teks: str, bg_color: str, nama_ikon: str = "") -> QPushButton:
        """Membuat tombol aksi berukuran ergonomis."""
        btn = QPushButton(teks, self)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setMinimumHeight(44)
        btn.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        if nama_ikon:
            btn.setIcon(_buat_ikon_vektor(nama_ikon, "#FFFFFF"))
            btn.setIconSize(QSize(18, 18))
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                color: #FFFFFF;
                border-radius: 6px;
                border: none;
                padding: 0 14px;
                outline: none;
            }}
            QPushButton:hover {{
                opacity: 0.92;
            }}
            QPushButton:pressed {{
                opacity: 0.82;
            }}
        """)
        return btn

    def muat_data(self) -> None:
        """Memuat ulang seluruh indikator dashboard secara akurat dari kedua domain data."""
        # 1. Muat metrik Simpan Pinjam
        dash_sp = ambil_ringkasan_dashboard(self.conn)
        self.data_sp = dash_sp

        # 2. Muat metrik Unit Toko
        dash_toko = ambil_ringkasan_dasbor_toko(self.conn)
        self.data_toko = dash_toko

        # 3. Update Status Backup
        info_b = ambil_info_backup_terakhir()
        self.lbl_backup_info.setText(f"Backup terakhir: {info_b}" if info_b else "Belum ada backup")

        # 4. Update Metrik Likuiditas Kas
        kas_sp = dash_sp.get("posisi_kas", 0)
        kas_toko = dash_toko.get("kas_toko", 0)
        total_kas = kas_sp + kas_toko

        self.card_kas_sp["nilai_label"].setText(format_rupiah(kas_sp))
        self.card_kas_toko["nilai_label"].setText(format_rupiah(kas_toko))
        self.card_kas_total["nilai_label"].setText(format_rupiah(total_kas))

        # 5. Update Metrik Simpan Pinjam
        self.card_simpanan["nilai_label"].setText(format_rupiah(dash_sp.get("simpanan_masuk_hari_ini", 0)))
        self.card_angsuran["nilai_label"].setText(format_rupiah(dash_sp.get("angsuran_masuk_hari_ini", 0)))
        self.card_pinjaman["nilai_label"].setText(format_rupiah(dash_sp.get("pinjaman_cair_hari_ini", 0)))
        self.card_admin["nilai_label"].setText(format_rupiah(dash_sp.get("biaya_admin_hari_ini", 0)))
        self.lbl_tempo_info.setText(f"{dash_sp.get('jumlah_jatuh_tempo_minggu_ini', 0)} Angsuran")
        self.lbl_menunggak_info.setText(f"{dash_sp.get('jumlah_anggota_menunggak', 0)} Anggota")

        # 6. Update Metrik Unit Toko
        self.card_penjualan["nilai_label"].setText(format_rupiah(dash_toko.get("penjualan_hari_ini", 0)))
        self.card_laba["nilai_label"].setText(format_rupiah(dash_toko.get("laba_kotor_hari_ini", 0)))
        self.card_piutang["nilai_label"].setText(format_rupiah(dash_toko.get("total_piutang", 0)))
        self.card_penitip["nilai_label"].setText(format_rupiah(dash_toko.get("hutang_penitip", 0)))

        str_perhatian = f"{dash_toko.get('jumlah_nota_telat', 0)} Nota Telat | {dash_toko.get('jumlah_stok_menipis', 0)} Stok Min"
        self.lbl_perhatian_toko.setText(str_perhatian)

        # 7. Update Banner Pengingat Terpadu
        while self.layout_pengingat.count():
            item = self.layout_pengingat.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Pengingat SP: Laporan Mingguan
        if dash_sp.get("pengingat_laporan_mingguan"):
            banner_lap = QLabel(
                "<b>Pengingat Simpan Pinjam:</b> Laporan mingguan belum dibuat dalam 7 hari terakhir.",
                self.box_pengingat
            )
            banner_lap.setStyleSheet(
                "background-color: #FEF3C7; color: #92400E; padding: 7px 12px; border-radius: 6px; border: 1px solid #FCD34D;"
            )
            self.layout_pengingat.addWidget(banner_lap)

        # Pengingat SP: Closing
        if dash_sp.get("pengingat_closing"):
            banner_cl_sp = QLabel(
                f"<b>Perhatian Simpan Pinjam:</b> Closing periode {dash_sp.get('periode_lalu_butuh_closing')} belum dilakukan.",
                self.box_pengingat
            )
            banner_cl_sp.setStyleSheet(
                "background-color: #FEE2E2; color: #991B1B; padding: 7px 12px; border-radius: 6px; border: 1px solid #FCA5A5;"
            )
            self.layout_pengingat.addWidget(banner_cl_sp)

        # Pengingat Toko: Closing Toko & Opname Toko
        try:
            thn, bln = date.today().year, date.today().month
            bln_lalu = bln - 1 if bln > 1 else 12
            thn_lalu = thn if bln > 1 else thn - 1
            periode_lalu = f"{thn_lalu:04d}-{bln_lalu:02d}"
            nama_bln_lalu = f"{calendar.month_name[bln_lalu]} {thn_lalu}"

            cur = self.conn.cursor()
            cur.execute("SELECT 1 FROM closing_toko WHERE periode = ? AND status = 'closed';", (periode_lalu,))
            if not cur.fetchone():
                banner_cl_toko = QLabel(
                    f"<b>Perhatian Unit Toko:</b> Closing toko periode {nama_bln_lalu} belum dilakukan.",
                    self.box_pengingat
                )
                banner_cl_toko.setStyleSheet(
                    "background-color: #FEE2E2; color: #991B1B; padding: 7px 12px; border-radius: 6px; border: 1px solid #FCA5A5;"
                )
                self.layout_pengingat.addWidget(banner_cl_toko)

            periode_ini = f"{thn:04d}-{bln:02d}"
            cur.execute("SELECT 1 FROM opname_sesi WHERE periode = ? AND status = 'final';", (periode_ini,))
            if not cur.fetchone():
                banner_opname = QLabel(
                    "<b>Pengingat Unit Toko:</b> Stock opname toko bulan ini belum dilakukan atau belum difinalkan.",
                    self.box_pengingat
                )
                banner_opname.setStyleSheet(
                    "background-color: #FEF3C7; color: #92400E; padding: 7px 12px; border-radius: 6px; border: 1px solid #FCD34D;"
                )
                self.layout_pengingat.addWidget(banner_opname)
        except Exception:
            pass

    def _lihat_daftar_tempo(self) -> None:
        daftar = self.data_sp.get("daftar_tempo_minggu_ini", [])
        dlg = QDialog(self)
        dlg.setWindowTitle("Daftar Angsuran Jatuh Tempo Minggu Ini")
        dlg.resize(850, 460)
        dlg.setMinimumSize(750, 380)

        d_layout = QVBoxLayout(dlg)
        d_layout.setContentsMargins(18, 18, 18, 18)
        d_layout.setSpacing(12)

        tabel = QTableWidget(dlg)
        tabel.setColumnCount(5)
        tabel.setHorizontalHeaderLabels([
            "Jatuh Tempo", "No. Pinjaman", "Nama dan No. Anggota", "Angsuran", "Sisa Tagihan"
        ])
        tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tabel.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        tabel.setColumnWidth(0, 130)
        tabel.setColumnWidth(1, 130)
        tabel.setColumnWidth(3, 110)
        tabel.setColumnWidth(4, 150)
        tabel.setRowCount(len(daftar))
        tabel.verticalHeader().setDefaultSectionSize(40)

        for b, r in enumerate(daftar):
            tabel.setItem(b, 0, QTableWidgetItem(format_tanggal_indo(r["jatuh_tempo"])))
            tabel.setItem(b, 1, QTableWidgetItem(r["no_pinjaman"]))
            tabel.setItem(b, 2, QTableWidgetItem(f"{r['nama_anggota']} ({r['no_anggota']})"))
            tabel.setItem(b, 3, QTableWidgetItem(f"Ke-{r['angsuran_ke']}"))
            
            sisa_item = QTableWidgetItem(format_rupiah(r["sisa_tagihan"]))
            sisa_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tabel.setItem(b, 4, sisa_item)

        d_layout.addWidget(tabel)
        
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_tutup = QPushButton("Tutup", dlg)
        btn_tutup.setMinimumHeight(40)
        btn_tutup.clicked.connect(dlg.accept)
        btn_box.addWidget(btn_tutup)
        d_layout.addLayout(btn_box)
        dlg.exec()

    def _lihat_daftar_menunggak(self) -> None:
        daftar = self.data_sp.get("daftar_anggota_menunggak", [])
        dlg = QDialog(self)
        dlg.setWindowTitle("Daftar Anggota Menunggak")
        dlg.resize(850, 460)
        dlg.setMinimumSize(750, 380)

        d_layout = QVBoxLayout(dlg)
        d_layout.setContentsMargins(18, 18, 18, 18)
        d_layout.setSpacing(12)

        tabel = QTableWidget(dlg)
        tabel.setColumnCount(4)
        tabel.setHorizontalHeaderLabels([
            "Nama dan No. Anggota", "No. Telepon / WA", "Cicilan Telat", "Total Tunggakan (Rp)"
        ])
        tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tabel.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tabel.setColumnWidth(1, 160)
        tabel.setColumnWidth(2, 130)
        tabel.setColumnWidth(3, 170)
        tabel.setRowCount(len(daftar))
        tabel.verticalHeader().setDefaultSectionSize(40)

        for b, r in enumerate(daftar):
            tabel.setItem(b, 0, QTableWidgetItem(f"{r['nama_anggota']} ({r['no_anggota']})"))
            tabel.setItem(b, 1, QTableWidgetItem(r["no_hp"] or "-"))
            tabel.setItem(b, 2, QTableWidgetItem(f"{r['jumlah_cicilan_telat']} bulan"))

            tot_item = QTableWidgetItem(format_rupiah(r["total_tunggakan"]))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tot_item.setForeground(Qt.GlobalColor.darkRed)
            tabel.setItem(b, 3, tot_item)

        d_layout.addWidget(tabel)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_tutup = QPushButton("Tutup", dlg)
        btn_tutup.setMinimumHeight(40)
        btn_tutup.clicked.connect(dlg.accept)
        btn_box.addWidget(btn_tutup)
        d_layout.addLayout(btn_box)
        dlg.exec()
