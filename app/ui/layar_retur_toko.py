"""
app/ui/layar_retur_toko.py — Layar Transaksi Retur Unit Toko:
1. Retur ke Supplier (pilih faktur/lot, jumlah dasar, potong hutang atau kas masuk)
2. Retur Penjualan (pilih nota penjualan, pilih item, kembalikan kas atau potong piutang)
3. Riwayat Transaksi Retur
"""
import sqlite3
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QDateEdit, QLineEdit, QMessageBox, QDialog, QFormLayout,
    QTabWidget, QSplitter
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QDate

from app.db.repo_retur_toko import (
    catat_retur_supplier, catat_retur_penjualan
)
from app.db.repo_pihak import ambil_daftar_pihak
from app.util.format import format_rupiah, format_tanggal_indo
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global


class LayarReturToko(QWidget):
    """Layar Transaksi Retur Supplier dan Retur Penjualan."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._inisialisasi_ui()

    def _inisialisasi_ui(self):
        self.setFont(QFont("Segoe UI", 11))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(12)

        # Header
        top_bar = QHBoxLayout()
        lbl_judul = QLabel("Transaksi Retur Unit Toko", self)
        lbl_judul.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        lbl_judul.setStyleSheet("color: #1E3A8A;")
        top_bar.addWidget(lbl_judul)

        top_bar.addStretch()

        btn_tambah_rs = QPushButton("+ Retur ke Supplier", self)
        btn_tambah_rs.setStyleSheet("background-color: #EF4444; color: white; font-weight: bold; padding: 6px 14px;")
        btn_tambah_rs.clicked.connect(self._dialog_retur_supplier)
        top_bar.addWidget(btn_tambah_rs)

        btn_tambah_rj = QPushButton("+ Retur dari Konsumen", self)
        btn_tambah_rj.setStyleSheet("background-color: #3B82F6; color: white; font-weight: bold; padding: 6px 14px;")
        btn_tambah_rj.clicked.connect(self._dialog_retur_penjualan)
        top_bar.addWidget(btn_tambah_rj)

        layout.addLayout(top_bar)

        # Tabs Riwayat Retur
        self.tabs = QTabWidget(self)

        # Tab 1: Riwayat Retur Supplier
        tab_rs = QWidget()
        lay_rs = QVBoxLayout(tab_rs)
        self.tbl_rs = QTableWidget(self)
        self.tbl_rs.setColumnCount(7)
        self.tbl_rs.setHorizontalHeaderLabels([
            "No Retur", "Tanggal", "Supplier", "No Faktur", "Total Nilai", "Kompensasi", "Alasan"
        ])
        self.tbl_rs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_rs.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_rs.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.tbl_rs.setColumnWidth(0, 130)  # No Retur
        self.tbl_rs.setColumnWidth(1, 115)  # Tanggal
        self.tbl_rs.setColumnWidth(3, 130)  # No Faktur
        self.tbl_rs.setColumnWidth(4, 130)  # Total Nilai
        self.tbl_rs.setColumnWidth(5, 120)  # Kompensasi
        terapkan_style_tabel_global(
            self.tbl_rs,
            rata_kanan_kolom=[4]
        )
        lay_rs.addWidget(self.tbl_rs)
        self.tabs.addTab(tab_rs, "Riwayat Retur ke Supplier")

        # Tab 2: Riwayat Retur Penjualan
        tab_rj = QWidget()
        lay_rj = QVBoxLayout(tab_rj)
        self.tbl_rj = QTableWidget(self)
        self.tbl_rj.setColumnCount(7)
        self.tbl_rj.setHorizontalHeaderLabels([
            "No Retur", "Tanggal", "Pembeli", "No Nota", "Total Nilai", "Kompensasi", "Alasan"
        ])
        self.tbl_rj.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_rj.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_rj.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.tbl_rj.setColumnWidth(0, 130)  # No Retur
        self.tbl_rj.setColumnWidth(1, 115)  # Tanggal
        self.tbl_rj.setColumnWidth(3, 130)  # No Nota
        self.tbl_rj.setColumnWidth(4, 130)  # Total Nilai
        self.tbl_rj.setColumnWidth(5, 120)  # Kompensasi
        terapkan_style_tabel_global(
            self.tbl_rj,
            rata_kanan_kolom=[4]
        )
        lay_rj.addWidget(self.tbl_rj)
        self.tabs.addTab(tab_rj, "Riwayat Retur dari Konsumen")

        layout.addWidget(self.tabs)
        self.muat_data()

    def muat_data(self):
        cur = self.conn.cursor()

        # 1. Muat Retur Supplier
        cur.execute(
            """
            SELECT rs.*, s.nama AS nama_supplier, pf.no_faktur
            FROM v_retur_supplier_efektif rs
            JOIN supplier s ON rs.supplier_id = s.id
            LEFT JOIN pembelian_faktur pf ON rs.pembelian_faktur_id = pf.id
            WHERE rs.status_efektif = 'NORMAL'
            ORDER BY rs.tanggal DESC, rs.id DESC;
            """
        )
        rows_rs = cur.fetchall()
        self.tbl_rs.setRowCount(len(rows_rs))
        for idx, r in enumerate(rows_rs):
            self.tbl_rs.setItem(idx, 0, QTableWidgetItem(r["no_retur"]))
            self.tbl_rs.setItem(idx, 1, QTableWidgetItem(format_tanggal_indo(r["tanggal"])))
            self.tbl_rs.setItem(idx, 2, QTableWidgetItem(r["nama_supplier"]))
            self.tbl_rs.setItem(idx, 3, QTableWidgetItem(r["no_faktur"] or "-"))
            c_tot = QTableWidgetItem(format_rupiah(r["total_retur"]))
            c_tot.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_rs.setItem(idx, 4, c_tot)
            komp = "Potong Hutang" if r["jenis_kompensasi"] == "potong_hutang" else "Kas Masuk"
            self.tbl_rs.setItem(idx, 5, QTableWidgetItem(komp))
            self.tbl_rs.setItem(idx, 6, QTableWidgetItem(r["alasan"] or "-"))

        # 2. Muat Retur Penjualan
        cur.execute(
            """
            SELECT rp.*, p.nama AS nama_pembeli, pj.no_nota
            FROM v_retur_penjualan_efektif rp
            JOIN pembeli p ON rp.pembeli_id = p.id
            JOIN penjualan pj ON rp.penjualan_id = pj.id
            WHERE rp.status_efektif = 'NORMAL'
            ORDER BY rp.tanggal DESC, rp.id DESC;
            """
        )
        rows_rj = cur.fetchall()
        self.tbl_rj.setRowCount(len(rows_rj))
        for idx, r in enumerate(rows_rj):
            self.tbl_rj.setItem(idx, 0, QTableWidgetItem(r["no_retur"]))
            self.tbl_rj.setItem(idx, 1, QTableWidgetItem(format_tanggal_indo(r["tanggal"])))
            self.tbl_rj.setItem(idx, 2, QTableWidgetItem(r["nama_pembeli"]))
            self.tbl_rj.setItem(idx, 3, QTableWidgetItem(r["no_nota"]))
            c_tot = QTableWidgetItem(format_rupiah(r["total_retur"]))
            c_tot.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_rj.setItem(idx, 4, c_tot)
            komp = "Kembali Kas" if r["jenis_kompensasi"] == "kembali_kas" else "Potong Piutang"
            self.tbl_rj.setItem(idx, 5, QTableWidgetItem(komp))
            self.tbl_rj.setItem(idx, 6, QTableWidgetItem(r["alasan"] or "-"))

    def _dialog_retur_supplier(self):
        # Dialog input retur supplier sederhana
        QMessageBox.information(
            self,
            "Petunjuk Retur Supplier",
            "Untuk meretur barang ke supplier, pilih faktur atau lot stok aktif terkait pada Kartu Barang atau Faktur Pembelian."
        )

    def _dialog_retur_penjualan(self):
        # Dialog input retur penjualan sederhana
        QMessageBox.information(
            self,
            "Petunjuk Retur Konsumen",
            "Untuk meretur penjualan konsumen, masukkan nomor nota penjualan terkait pada modul kasir atau kartu pembeli."
        )
