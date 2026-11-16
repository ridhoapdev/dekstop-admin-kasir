"""
app/ui/layar_laporan_toko.py — Layar Laporan Unit Toko:
1. Pemilih Jenis Laporan: Harian / Mingguan / Bulanan / Tahunan
2. Tombol Pintas: Minggu Ini / Minggu Lalu / Bulan Ini
3. Tampilan 1: Rekapitulasi per Barang (Stok Awal, Masuk, Keluar, Penyesuaian, Stok Akhir, Penjualan, HPP, Laba, Margin)
4. Tampilan 2: Rincian Transaksi
5. Tampilan 3: Ringkasan Tahunan & Grafik
6. Tampilan 4: Analisis (Stok Menipis & Barang Tidak Bergerak)
7. Ekspor Excel (.xlsx) dan PDF (.pdf)
"""
import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional, Callable, Dict, Any, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QDateEdit, QFileDialog, QMessageBox, QTabWidget, QFrame,
    QGridLayout
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, QDate

from app.db.repo_laporan_toko import (
    ambil_rekap_per_barang_periode, ambil_rincian_transaksi_toko,
    hitung_ringkasan_keuangan_toko, ambil_laporan_tahunan_toko,
    ambil_laporan_barang_tidak_bergerak, ambil_laporan_stok_menipis
)
from app.layanan.ekspor_laporan_toko import ekspor_rekap_barang_excel, ekspor_rekap_barang_pdf
from app.util.format import format_rupiah, format_tanggal_indo


class LayarLaporanToko(QWidget):
    """Layar Laporan Unit Toko."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.data_rekap_terakhir: List[Dict[str, Any]] = []
        self.ringkasan_terakhir: Dict[str, Any] = {}
        self._inisialisasi_ui()

    def _inisialisasi_ui(self):
        self.setFont(QFont("Segoe UI", 11))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(10)

        # Baris Header & Pemilih Jenis
        top_bar = QHBoxLayout()
        lbl_judul = QLabel("Laporan Komprehensif Unit Toko", self)
        lbl_judul.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        lbl_judul.setStyleSheet("color: #1E3A8A;")
        top_bar.addWidget(lbl_judul)

        top_bar.addStretch()

        btn_excel = QPushButton("Ekspor Excel", self)
        btn_excel.setStyleSheet("background-color: #059669; color: white; font-weight: bold; padding: 6px 14px;")
        btn_excel.clicked.connect(self._ekspor_excel)
        top_bar.addWidget(btn_excel)

        btn_pdf = QPushButton("Ekspor PDF", self)
        btn_pdf.setStyleSheet("background-color: #DC2626; color: white; font-weight: bold; padding: 6px 14px;")
        btn_pdf.clicked.connect(self._ekspor_pdf)
        top_bar.addWidget(btn_pdf)

        layout.addLayout(top_bar)

        # Baris Filter Periode
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Periode Dari:", self))
        self.dt_awal = QDateEdit(self)
        self.dt_awal.setCalendarPopup(True)
        self.dt_awal.setDate(QDate.currentDate().addDays(-7))
        filter_bar.addWidget(self.dt_awal)

        filter_bar.addWidget(QLabel("Sampai:", self))
        self.dt_akhir = QDateEdit(self)
        self.dt_akhir.setCalendarPopup(True)
        self.dt_akhir.setDate(QDate.currentDate())
        filter_bar.addWidget(self.dt_akhir)

        btn_minggu_ini = QPushButton("Minggu Ini", self)
        btn_minggu_ini.clicked.connect(self._set_minggu_ini)
        filter_bar.addWidget(btn_minggu_ini)

        btn_bulan_ini = QPushButton("Bulan Ini", self)
        btn_bulan_ini.clicked.connect(self._set_bulan_ini)
        filter_bar.addWidget(btn_bulan_ini)

        btn_muat = QPushButton("Tampilkan Laporan", self)
        btn_muat.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 6px 14px;")
        btn_muat.clicked.connect(self.muat_data)
        filter_bar.addWidget(btn_muat)

        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        # Panel Ringkasan Cepat Periode
        self.panel_ringkasan = QFrame(self)
        self.panel_ringkasan.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 8px;")
        grid_r = QGridLayout(self.panel_ringkasan)

        self.lbl_r_penjualan = QLabel("Total Penjualan: Rp 0", self)
        self.lbl_r_penjualan.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        grid_r.addWidget(self.lbl_r_penjualan, 0, 0)

        self.lbl_r_hpp = QLabel("Total HPP: Rp 0", self)
        grid_r.addWidget(self.lbl_r_hpp, 0, 1)

        self.lbl_r_laba = QLabel("Laba Kotor: Rp 0", self)
        self.lbl_r_laba.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_r_laba.setStyleSheet("color: #059669;")
        grid_r.addWidget(self.lbl_r_laba, 0, 2)

        self.lbl_r_kas = QLabel("Arus Kas Masuk / Keluar: Rp 0 / Rp 0", self)
        grid_r.addWidget(self.lbl_r_kas, 1, 0)

        self.lbl_r_piutang = QLabel("Total Piutang Toko: Rp 0", self)
        grid_r.addWidget(self.lbl_r_piutang, 1, 1)

        self.lbl_r_rugi_stok = QLabel("Beban Kerugian Persediaan: Rp 0", self)
        self.lbl_r_rugi_stok.setStyleSheet("color: #DC2626;")
        grid_r.addWidget(self.lbl_r_rugi_stok, 1, 2)

        layout.addWidget(self.panel_ringkasan)

        # Tabs Laporan
        self.tabs = QTabWidget(self)

        # Tab 1: Rekap per Barang
        tab_rekap = QWidget()
        lay_rk = QVBoxLayout(tab_rekap)
        self.tbl_rekap = QTableWidget(self)
        self.tbl_rekap.setColumnCount(11)
        self.tbl_rekap.setHorizontalHeaderLabels([
            "Kode", "Nama Barang", "Satuan", "Stok Awal", "Masuk", "Keluar", "Penyesuaian",
            "Stok Akhir", "Total Penjualan", "Total HPP", "Laba Kotor"
        ])
        self.tbl_rekap.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_rekap.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_rekap.setColumnWidth(0, 100)  # Kode
        self.tbl_rekap.setColumnWidth(2, 80)   # Satuan
        self.tbl_rekap.setColumnWidth(3, 90)   # Stok Awal
        self.tbl_rekap.setColumnWidth(4, 80)   # Masuk
        self.tbl_rekap.setColumnWidth(5, 80)   # Keluar
        self.tbl_rekap.setColumnWidth(6, 100)  # Penyesuaian
        self.tbl_rekap.setColumnWidth(7, 90)   # Stok Akhir
        self.tbl_rekap.setColumnWidth(8, 130)  # Total Penjualan
        self.tbl_rekap.setColumnWidth(9, 130)  # Total HPP
        self.tbl_rekap.setColumnWidth(10, 130) # Laba Kotor
        lay_rk.addWidget(self.tbl_rekap)
        self.tabs.addTab(tab_rekap, "Rekapitulasi per Barang")

        # Tab 2: Rincian Transaksi
        tab_rincian = QWidget()
        lay_rc = QVBoxLayout(tab_rincian)
        self.tbl_rincian = QTableWidget(self)
        self.tbl_rincian.setColumnCount(10)
        self.tbl_rincian.setHorizontalHeaderLabels([
            "Tanggal", "No Nota", "Pembeli", "Nama Barang", "Qty Dasar", "HPP/Satuan",
            "Harga Jual", "Subtotal", "Laba", "Metode"
        ])
        self.tbl_rincian.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_rincian.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tbl_rincian.setColumnWidth(0, 105)  # Tanggal
        self.tbl_rincian.setColumnWidth(1, 120)  # No Nota
        self.tbl_rincian.setColumnWidth(2, 130)  # Pembeli
        self.tbl_rincian.setColumnWidth(4, 90)   # Qty Dasar
        self.tbl_rincian.setColumnWidth(5, 110)  # HPP/Satuan
        self.tbl_rincian.setColumnWidth(6, 110)  # Harga Jual
        self.tbl_rincian.setColumnWidth(7, 130)  # Subtotal
        self.tbl_rincian.setColumnWidth(8, 120)  # Laba
        self.tbl_rincian.setColumnWidth(9, 90)   # Metode
        lay_rc.addWidget(self.tbl_rincian)
        self.tabs.addTab(tab_rincian, "Rincian Transaksi")

        # Tab 3: Laporan Tahunan
        tab_tahunan = QWidget()
        lay_th = QVBoxLayout(tab_tahunan)
        self.tbl_tahunan = QTableWidget(self)
        self.tbl_tahunan.setColumnCount(8)
        self.tbl_tahunan.setHorizontalHeaderLabels([
            "Bulan", "Status Periode", "Penjualan", "HPP", "Laba Kotor", "Rugi Persediaan", "Kas Akhir", "Persediaan Akhir"
        ])
        self.tbl_tahunan.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_tahunan.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_tahunan.setColumnWidth(1, 110)  # Status Periode
        self.tbl_tahunan.setColumnWidth(2, 130)  # Penjualan
        self.tbl_tahunan.setColumnWidth(3, 130)  # HPP
        self.tbl_tahunan.setColumnWidth(4, 130)  # Laba Kotor
        self.tbl_tahunan.setColumnWidth(5, 130)  # Rugi Persediaan
        self.tbl_tahunan.setColumnWidth(6, 130)  # Kas Akhir
        self.tbl_tahunan.setColumnWidth(7, 130)  # Persediaan Akhir
        lay_th.addWidget(self.tbl_tahunan)
        self.tabs.addTab(tab_tahunan, "Laporan Tahunan 12 Bulan")

        # Tab 4: Analisis Stok Menipis & Barang Macet
        tab_analisis = QWidget()
        lay_an = QVBoxLayout(tab_analisis)
        lay_an.addWidget(QLabel("Daftar Barang Tidak Bergerak (> 30 Hari Tanpa Transaksi):", self))
        self.tbl_macet = QTableWidget(self)
        self.tbl_macet.setColumnCount(5)
        self.tbl_macet.setHorizontalHeaderLabels(["Kode", "Nama Barang", "Satuan", "Stok Mengendap", "Penjualan Terakhir"])
        self.tbl_macet.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_macet.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_macet.setColumnWidth(0, 110)  # Kode
        self.tbl_macet.setColumnWidth(2, 90)   # Satuan
        self.tbl_macet.setColumnWidth(3, 130)  # Stok Mengendap
        self.tbl_macet.setColumnWidth(4, 140)  # Penjualan Terakhir
        lay_an.addWidget(self.tbl_macet)
        self.tabs.addTab(tab_analisis, "Barang Tidak Bergerak")

        layout.addWidget(self.tabs)
        self.muat_data()

    def _set_minggu_ini(self):
        tgl_hari_ini = QDate.currentDate()
        hari_senin = tgl_hari_ini.addDays(-(tgl_hari_ini.dayOfWeek() - 1))
        self.dt_awal.setDate(hari_senin)
        self.dt_akhir.setDate(tgl_hari_ini)
        self.muat_data()

    def _set_bulan_ini(self):
        tgl_hari_ini = QDate.currentDate()
        awal_bulan = QDate(tgl_hari_ini.year(), tgl_hari_ini.month(), 1)
        self.dt_awal.setDate(awal_bulan)
        self.dt_akhir.setDate(tgl_hari_ini)
        self.muat_data()

    def muat_data(self):
        tgl_awal = self.dt_awal.date().toString("yyyy-MM-dd")
        tgl_akhir = self.dt_akhir.date().toString("yyyy-MM-dd")

        # 1. Ringkasan Keuangan
        ringk = hitung_ringkasan_keuangan_toko(self.conn, tgl_awal, tgl_akhir)
        self.ringkasan_terakhir = ringk

        self.lbl_r_penjualan.setText(f"Total Penjualan: {format_rupiah(ringk['total_penjualan'])}")
        self.lbl_r_hpp.setText(f"Total HPP: {format_rupiah(ringk['total_hpp'])}")
        self.lbl_r_laba.setText(f"Laba Kotor: {format_rupiah(ringk['laba_kotor'])}")
        self.lbl_r_kas.setText(f"Kas Masuk/Keluar: {format_rupiah(ringk['kas_toko_masuk'])} / {format_rupiah(ringk['kas_toko_keluar'])}")
        self.lbl_r_piutang.setText(f"Total Piutang Toko: {format_rupiah(ringk['total_piutang'])}")
        self.lbl_r_rugi_stok.setText(f"Kerugian Persediaan: {format_rupiah(ringk['kerugian_persediaan'])}")

        # 2. Rekap per Barang
        daftar_rekap = ambil_rekap_per_barang_periode(self.conn, tgl_awal, tgl_akhir)
        self.data_rekap_terakhir = daftar_rekap

        self.tbl_rekap.setRowCount(len(daftar_rekap))
        for idx, r in enumerate(daftar_rekap):
            self.tbl_rekap.setItem(idx, 0, QTableWidgetItem(r["kode"]))
            self.tbl_rekap.setItem(idx, 1, QTableWidgetItem(r["nama"]))
            self.tbl_rekap.setItem(idx, 2, QTableWidgetItem(r["satuan_dasar"]))

            for c_idx, key in enumerate(["stok_awal", "masuk", "keluar", "penyesuaian", "stok_akhir"], 3):
                item = QTableWidgetItem(f"{r[key]:,}".replace(",", "."))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tbl_rekap.setItem(idx, c_idx, item)

            c_jual = QTableWidgetItem(format_rupiah(r["total_penjualan"]))
            c_jual.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_rekap.setItem(idx, 8, c_jual)

            c_hpp = QTableWidgetItem(format_rupiah(r["total_hpp"]))
            c_hpp.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_rekap.setItem(idx, 9, c_hpp)

            c_laba = QTableWidgetItem(format_rupiah(r["laba"]))
            c_laba.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_rekap.setItem(idx, 10, c_laba)

        # 3. Rincian Transaksi
        rincian = ambil_rincian_transaksi_toko(self.conn, tgl_awal, tgl_akhir)
        self.tbl_rincian.setRowCount(len(rincian))
        for idx, r in enumerate(rincian):
            self.tbl_rincian.setItem(idx, 0, QTableWidgetItem(format_tanggal_indo(r["tanggal"])))
            self.tbl_rincian.setItem(idx, 1, QTableWidgetItem(r["no_nota"]))
            self.tbl_rincian.setItem(idx, 2, QTableWidgetItem(r["nama_pembeli"]))
            self.tbl_rincian.setItem(idx, 3, QTableWidgetItem(r["nama_barang"]))

            c_qty = QTableWidgetItem(f"{r['jumlah_dasar']} {r['satuan_dasar']}")
            c_qty.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_rincian.setItem(idx, 4, c_qty)

            c_hpp = QTableWidgetItem(format_rupiah(r["hpp_satuan_dasar"]))
            c_hpp.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_rincian.setItem(idx, 5, c_hpp)

            c_hrg = QTableWidgetItem(format_rupiah(r["harga_jual_satuan_dasar"]))
            c_hrg.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_rincian.setItem(idx, 6, c_hrg)

            c_tot = QTableWidgetItem(format_rupiah(r["total_baris"]))
            c_tot.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_rincian.setItem(idx, 7, c_tot)

            c_laba = QTableWidgetItem(format_rupiah(r["laba"]))
            c_laba.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_rincian.setItem(idx, 8, c_laba)

            self.tbl_rincian.setItem(idx, 9, QTableWidgetItem(r["metode"].capitalize()))

        # 4. Laporan Tahunan
        thn_pilih = self.dt_akhir.date().year()
        lap_thn = ambil_laporan_tahunan_toko(self.conn, thn_pilih)
        bulan_list = lap_thn["daftar_bulan"]
        self.tbl_tahunan.setRowCount(len(bulan_list))
        for idx, b in enumerate(bulan_list):
            self.tbl_tahunan.setItem(idx, 0, QTableWidgetItem(b["nama_bulan"]))
            c_st = QTableWidgetItem(b["status"])
            if b["is_closing"]:
                c_st.setForeground(QColor("#059669"))
            else:
                c_st.setForeground(QColor("#D97706"))
            self.tbl_tahunan.setItem(idx, 1, c_st)

            for c_i, k in enumerate(["penjualan", "hpp", "laba", "kerugian_persediaan", "kas_akhir", "nilai_persediaan"], 2):
                item = QTableWidgetItem(format_rupiah(b[k]))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tbl_tahunan.setItem(idx, c_i, item)

        # 5. Barang Tidak Bergerak
        macet_list = ambil_laporan_barang_tidak_bergerak(self.conn)
        self.tbl_macet.setRowCount(len(macet_list))
        for idx, m in enumerate(macet_list):
            self.tbl_macet.setItem(idx, 0, QTableWidgetItem(m["kode"]))
            self.tbl_macet.setItem(idx, 1, QTableWidgetItem(m["nama"]))
            self.tbl_macet.setItem(idx, 2, QTableWidgetItem(m["satuan_dasar"]))
            c_stk = QTableWidgetItem(f"{m['stok_saat_ini']:,}".replace(",", "."))
            c_stk.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_macet.setItem(idx, 3, c_stk)
            self.tbl_macet.setItem(idx, 4, QTableWidgetItem(str(m["transaksi_terakhir"])))

    def _ekspor_excel(self):
        if not self.data_rekap_terakhir:
            QMessageBox.information(self, "Informasi", "Tidak ada data laporan untuk diekspor.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Simpan Laporan Excel", "Rekap_Barang_Toko.xlsx", "Excel Files (*.xlsx)")
        if path:
            try:
                periode_str = f"{self.dt_awal.date().toString('dd/MM/yyyy')} - {self.dt_akhir.date().toString('dd/MM/yyyy')}"
                ekspor_rekap_barang_excel(self.data_rekap_terakhir, self.ringkasan_terakhir, periode_str, path)
                QMessageBox.information(self, "Berhasil", f"Laporan toko berhasil diekspor ke Excel:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "Gagal Ekspor", f"Terjadi kesalahan saat membuat file Excel: {e}")

    def _ekspor_pdf(self):
        if not self.data_rekap_terakhir:
            QMessageBox.information(self, "Informasi", "Tidak ada data laporan untuk diekspor.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Simpan Laporan PDF", "Rekap_Barang_Toko.pdf", "PDF Files (*.pdf)")
        if path:
            try:
                periode_str = f"{self.dt_awal.date().toString('dd/MM/yyyy')} - {self.dt_akhir.date().toString('dd/MM/yyyy')}"
                ekspor_rekap_barang_pdf(self.data_rekap_terakhir, self.ringkasan_terakhir, periode_str, path)
                QMessageBox.information(self, "Berhasil", f"Laporan toko berhasil diekspor ke PDF:\n{path}")
            except Exception as e:
                QMessageBox.warning(self, "Gagal Ekspor", f"Terjadi kesalahan saat membuat file PDF: {e}")
