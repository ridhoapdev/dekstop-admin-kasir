"""
app/ui/layar_filter_cepat.py — Layar Filter Cepat (SPEC.md 4.6 C).
Tombol filter instan: Hari ini | Minggu ini | Bulan ini | Pilih tanggal | Pinjaman aktif | Menunggak.
Menampilkan tabel hasil, baris total kalkulasi, dan tombol Ekspor Excel / Cetak.
"""
import sqlite3
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDateEdit,
    QFileDialog, QMessageBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QDate

from app.db.repo_kartu_anggota import ambil_transaksi_filter_cepat
from app.util.format import format_rupiah, format_tanggal_indo
from app.layanan.ekspor_excel import ekspor_tabel_ke_excel


class LayarFilterCepat(QWidget):
    """Layar Filter Cepat Transaksi dan Pinjaman."""

    def __init__(self, conn: sqlite3.Connection, navigasi_kartu_callback=None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.navigasi_kartu = navigasi_kartu_callback
        self.mode_aktif = "hari_ini"
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        self.lbl_judul = QLabel("Pencarian dan Filter Cepat", self)
        self.lbl_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(self.lbl_judul)

        header_layout.addStretch()

        self.btn_ekspor = QPushButton("Ekspor ke Excel", self)
        self.btn_ekspor.setProperty("tipe", "sukses")
        self.btn_ekspor.clicked.connect(self._ekspor_excel)
        header_layout.addWidget(self.btn_ekspor)

        layout.addLayout(header_layout)

        # Baris Tombol Filter Cepat (SPEC.md 4.6 C)
        filter_bar = QHBoxLayout()
        self.btn_hari_ini = QPushButton("Hari Ini", self)
        self.btn_minggu_ini = QPushButton("Minggu Ini", self)
        self.btn_bulan_ini = QPushButton("Bulan Ini", self)
        self.btn_pinjaman_aktif = QPushButton("Pinjaman Aktif", self)
        self.btn_menunggak = QPushButton("Menunggak", self)

        for btn in (self.btn_hari_ini, self.btn_minggu_ini, self.btn_bulan_ini, self.btn_pinjaman_aktif, self.btn_menunggak):
            btn.setCheckable(True)
            filter_bar.addWidget(btn)

        self.btn_hari_ini.setChecked(True)
        self.btn_hari_ini.clicked.connect(lambda: self._set_filter("hari_ini"))
        self.btn_minggu_ini.clicked.connect(lambda: self._set_filter("minggu_ini"))
        self.btn_bulan_ini.clicked.connect(lambda: self._set_filter("bulan_ini"))
        self.btn_pinjaman_aktif.clicked.connect(lambda: self._set_filter("pinjaman_aktif"))
        self.btn_menunggak.clicked.connect(lambda: self._set_filter("menunggak"))

        # Pilih Tanggal Spesifik
        filter_bar.addSpacing(15)
        self.input_tgl_spesifik = QDateEdit(self)
        self.input_tgl_spesifik.setCalendarPopup(True)
        self.input_tgl_spesifik.setDate(QDate.currentDate())
        self.input_tgl_spesifik.setDisplayFormat("dd/MM/yyyy")
        self.btn_terapkan_tgl = QPushButton("Pilih Tanggal", self)
        self.btn_terapkan_tgl.clicked.connect(lambda: self._set_filter("pilih_tanggal"))

        filter_bar.addWidget(self.input_tgl_spesifik)
        filter_bar.addWidget(self.btn_terapkan_tgl)

        layout.addLayout(filter_bar)

        # Tabel Hasil
        self.tabel = QTableWidget(self)
        self.tabel.setFont(QFont("Segoe UI", 11))
        self.tabel.setColumnCount(5)
        self.tabel.setHorizontalHeaderLabels([
            "Tanggal", "Nama dan No. Anggota", "Rincian Transaksi / Pinjaman", "Nominal (Rp)", "Keterangan / Status"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabel.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabel.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 115)  # Tanggal
        self.tabel.setColumnWidth(3, 140)  # Nominal (Rp)
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setDefaultSectionSize(36)
        self.tabel.doubleClicked.connect(self._klik_baris)
        layout.addWidget(self.tabel)

        # Baris Ringkasan Total
        bottom_layout = QHBoxLayout()
        self.lbl_info_total = QLabel("Total: 0 Data | Total Nominal: Rp 0", self)
        self.lbl_info_total.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_info_total.setStyleSheet("color: #1E3A8A; padding: 6px 0;")
        bottom_layout.addWidget(self.lbl_info_total)

        bottom_layout.addStretch()

        self.btn_buka_kartu = QPushButton("Buka Kartu Anggota Terpilih", self)
        self.btn_buka_kartu.setProperty("tipe", "utama")
        self.btn_buka_kartu.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 0 16px;")
        self.btn_buka_kartu.clicked.connect(self._klik_baris)
        bottom_layout.addWidget(self.btn_buka_kartu)

        layout.addLayout(bottom_layout)

        self.daftar_data = []
        self.muat_data()

    def _set_filter(self, mode: str) -> None:
        self.mode_aktif = mode
        # Update check state
        self.btn_hari_ini.setChecked(mode == "hari_ini")
        self.btn_minggu_ini.setChecked(mode == "minggu_ini")
        self.btn_bulan_ini.setChecked(mode == "bulan_ini")
        self.btn_pinjaman_aktif.setChecked(mode == "pinjaman_aktif")
        self.btn_menunggak.setChecked(mode == "menunggak")
        self.muat_data()

    def muat_data(self) -> None:
        tgl_spesifik = self.input_tgl_spesifik.date().toString("yyyy-MM-dd")
        self.daftar_data = ambil_transaksi_filter_cepat(
            self.conn, mode_filter=self.mode_aktif, tanggal_spesifik=tgl_spesifik
        )
        self.tabel.setRowCount(len(self.daftar_data))

        total_nominal = 0
        for baris, r in enumerate(self.daftar_data):
            total_nominal += r["nominal"]
            self.tabel.setItem(baris, 0, QTableWidgetItem(format_tanggal_indo(r["tanggal"])))
            self.tabel.setItem(baris, 1, QTableWidgetItem(r["entitas"]))
            self.tabel.setItem(baris, 2, QTableWidgetItem(r["rincian"]))

            nom_item = QTableWidgetItem(format_rupiah(r["nominal"]))
            nom_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(baris, 3, nom_item)

            stat_item = QTableWidgetItem(r["status_info"])
            if self.mode_aktif == "menunggak":
                stat_item.setForeground(Qt.GlobalColor.darkRed)
            self.tabel.setItem(baris, 4, stat_item)

        label_mode = {
            "hari_ini": "Hari Ini",
            "minggu_ini": "Minggu Ini",
            "bulan_ini": "Bulan Ini",
            "pilih_tanggal": f"Tanggal {format_tanggal_indo(tgl_spesifik)}",
            "pinjaman_aktif": "Seluruh Pinjaman Aktif",
            "menunggak": "Daftar Pinjaman Menunggak"
        }.get(self.mode_aktif, "")

        self.lbl_info_total.setText(
            f"Filter: {label_mode} | Total: {len(self.daftar_data)} Data | Total Nominal: {format_rupiah(total_nominal)}"
        )

    def _klik_baris(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_data):
            QMessageBox.information(self, "Pilih Data", "Silakan klik baris pada tabel terlebih dahulu.")
            return

        anggota_id = self.daftar_data[baris].get("anggota_id")
        if anggota_id and self.navigasi_kartu:
            self.navigasi_kartu(anggota_id)

    def _ekspor_excel(self) -> None:
        if not self.daftar_data:
            QMessageBox.information(self, "Kosong", "Tidak ada data untuk diekspor.")
            return

        nama_file_default = f"Laporan_Filter_{self.mode_aktif}.xlsx"
        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Simpan Laporan Excel", nama_file_default, "Excel Files (*.xlsx)"
        )
        if not path_simpan:
            return

        kolom = ["Tanggal", "Nama dan No. Anggota", "Rincian Transaksi / Pinjaman", "Nominal (Rp)", "Keterangan / Status"]
        baris_data = []
        total_nom = 0
        for r in self.daftar_data:
            total_nom += r["nominal"]
            baris_data.append([
                r["tanggal"],
                r["entitas"],
                r["rincian"],
                r["nominal"],
                r["status_info"]
            ])

        baris_total = ["TOTAL", "", "", total_nom, f"{len(self.daftar_data)} Data"]
        judul = f"LAPORAN FILTER: {self.mode_aktif.upper()}"

        try:
            ekspor_tabel_ke_excel(judul, kolom, baris_data, path_simpan, baris_total)
            QMessageBox.information(self, "Ekspor Berhasil", f"Data berhasil disimpan ke:\n{path_simpan}")
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal mengekspor data: {err}")

