"""
app/ui/layar_kartu_barang.py — Layar Kartu Barang (Single View Terpadu Sesuai SPEC Modul 15):
1. Info Dasar Barang (kode, nama, kategori, satuan dasar, satuan besar, kepemilikan, harga jual, stok minimum)
2. Stok Sekarang (satuan dasar & satuan besar '47 pcs = 2 dus + 7 pcs', status aman/hampir habis/habis, nilai persediaan)
3. Lot FIFO Aktif (tanggal masuk, asal/supplier/penitip, sisa, harga beli per unit dasar, urutan keluar)
4. Laba & Margin (laba per satuan berikutnya, penjualan & laba hari ini, minggu ini, bulan ini, tahun ini, total)
5. Riwayat Kartu Stok (mutasi efektif, filter jenis & tanggal, saldo berjalan kumulatif)
6. Supplier Terakhir, Harga Beli Terakhir, Pembeli Terbanyak
7. Tombol Cepat: Tambah Stok (Pembelian), Catat Rusak/Hilang, Ubah Harga Jual
"""
import sqlite3
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QDateEdit, QLineEdit, QMessageBox, QDialog, QFormLayout,
    QFrame, QGridLayout, QTabWidget
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, QDate

from app.db.repo_kartu_toko import ambil_data_kartu_barang
from app.db.repo_opname_toko import catat_penyesuaian_manual
from app.db.repo_barang import ubah_barang, ambil_barang_by_id
from app.ui.komponen.input_rupiah import InputRupiah
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global
from app.util.format import format_rupiah, format_tanggal_indo
from app.layanan.bus_sinyal import langganan, lepas_langganan


class DialogPenyesuaianCepat(QDialog):
    """Dialog Catat Barang Rusak, Hilang, atau Kedaluwarsa."""

    def __init__(self, conn: sqlite3.Connection, barang_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.barang_id = barang_id
        self.setWindowTitle("Catat Penyesuaian Barang Rusak atau Hilang")
        self.resize(450, 300)
        self._inisialisasi_ui()

    def _inisialisasi_ui(self):
        self.setFont(QFont("Segoe UI", 11))
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.cmb_jenis = QComboBox(self)
        self.cmb_jenis.addItems(["rusak", "hilang", "kedaluwarsa"])
        form.addRow("Jenis Kejadian:", self.cmb_jenis)

        self.tgl_input = QDateEdit(self)
        self.tgl_input.setCalendarPopup(True)
        self.tgl_input.setDate(QDate.currentDate())
        form.addRow("Tanggal:", self.tgl_input)

        self.inp_qty = QLineEdit(self)
        self.inp_qty.setPlaceholderText("Jumlah dalam satuan dasar...")
        form.addRow("Jumlah Unit:", self.inp_qty)

        self.inp_catatan = QLineEdit(self)
        self.inp_catatan.setPlaceholderText("Alasan / keterangan...")
        form.addRow("Keterangan:", self.inp_catatan)

        lay.addLayout(form)

        btn_box = QHBoxLayout()
        btn_batal = QPushButton("Batal", self)
        btn_batal.clicked.connect(self.reject)
        btn_simpan = QPushButton("Simpan Penyesuaian", self)
        btn_simpan.setStyleSheet("background-color: #DC2626; color: white; font-weight: bold; padding: 8px 16px;")
        btn_simpan.clicked.connect(self._simpan)

        btn_box.addStretch()
        btn_box.addWidget(btn_batal)
        btn_box.addWidget(btn_simpan)
        lay.addLayout(btn_box)

    def _simpan(self):
        try:
            qty = int(self.inp_qty.text().strip())
            if qty <= 0:
                raise ValueError("Jumlah unit harus lebih besar dari 0.")
            catat_penyesuaian_manual(
                conn=self.conn,
                barang_id=self.barang_id,
                tanggal=self.tgl_input.date().toString("yyyy-MM-dd"),
                jenis=self.cmb_jenis.currentText(),
                jumlah_dasar=qty,
                catatan=self.inp_catatan.text().strip()
            )
            QMessageBox.information(self, "Berhasil", "Penyesuaian stok berhasil disimpan dan dicatat sebagai beban kerugian persediaan.")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Perhatian", f"Gagal menyimpan penyesuaian: {e}")


class DialogUbahHargaJual(QDialog):
    """Dialog Cepat Ubah Harga Jual Barang."""

    def __init__(self, conn: sqlite3.Connection, barang_id: int, harga_lama: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.barang_id = barang_id
        self.setWindowTitle("Ubah Harga Jual Barang")
        self.resize(400, 200)
        self._inisialisasi_ui(harga_lama)

    def _inisialisasi_ui(self, harga_lama: int):
        self.setFont(QFont("Segoe UI", 11))
        lay = QVBoxLayout(self)
        form = QFormLayout()

        lbl_lama = QLabel(format_rupiah(harga_lama), self)
        form.addRow("Harga Jual Lama:", lbl_lama)

        self.inp_harga_baru = InputRupiah(self)
        self.inp_harga_baru.set_nilai(harga_lama)
        form.addRow("Harga Jual Baru:", self.inp_harga_baru)

        lay.addLayout(form)

        btn_box = QHBoxLayout()
        btn_batal = QPushButton("Batal", self)
        btn_batal.clicked.connect(self.reject)
        btn_simpan = QPushButton("Simpan Perubahan", self)
        btn_simpan.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 8px 16px;")
        btn_simpan.clicked.connect(self._simpan)

        btn_box.addStretch()
        btn_box.addWidget(btn_batal)
        btn_box.addWidget(btn_simpan)
        lay.addLayout(btn_box)

    def _simpan(self):
        try:
            hrg_baru = self.inp_harga_baru.ambil_nilai()
            brg = ambil_barang_by_id(self.conn, self.barang_id)
            if not brg:
                raise ValueError("Data barang tidak ditemukan.")
            ubah_barang(
                conn=self.conn,
                barang_id=self.barang_id,
                kode=brg["kode"],
                nama=brg["nama"],
                satuan_dasar=brg["satuan_dasar"],
                kategori=brg["kategori"],
                kata_kunci=brg["kata_kunci"],
                harga_jual=hrg_baru,
                jenis_kepemilikan=brg["jenis_kepemilikan"],
                penitip_id=brg["penitip_id"],
                stok_minimum=brg["stok_minimum"]
            )
            QMessageBox.information(self, "Berhasil", "Harga jual barang berhasil diperbarui.")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Perhatian", f"Gagal mengubah harga jual: {e}")


class LayarKartuBarang(QWidget):
    """Layar Kartu Barang Lengkap."""

    def __init__(self, conn: sqlite3.Connection, navigasi_callback: Optional[Callable[[str], None]] = None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.navigasi_cb = navigasi_callback
        self.barang_id_terpilih: Optional[int] = None
        self._inisialisasi_ui()

        langganan("stok_berubah", self.muat_data)
        langganan("penjualan_berubah", self.muat_data)

    def closeEvent(self, event):
        lepas_langganan("stok_berubah", self.muat_data)
        lepas_langganan("penjualan_berubah", self.muat_data)
        super().closeEvent(event)

    def set_barang_id(self, barang_id: int):
        self.barang_id_terpilih = barang_id
        self.muat_data()

    def _inisialisasi_ui(self):
        self.setFont(QFont("Segoe UI", 11))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(12)

        # Baris Judul & Tombol Cepat
        top_bar = QHBoxLayout()
        self.lbl_judul = QLabel("Kartu Riwayat dan Profil Barang Toko", self)
        self.lbl_judul.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        self.lbl_judul.setStyleSheet("color: #1E3A8A;")
        top_bar.addWidget(self.lbl_judul)

        top_bar.addStretch()

        self.btn_tambah_stok = QPushButton("+ Pembelian Stok", self)
        self.btn_tambah_stok.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_tambah_stok.clicked.connect(self._ke_pembelian)
        top_bar.addWidget(self.btn_tambah_stok)

        self.btn_catat_rusak = QPushButton("Catat Rusak atau Hilang", self)
        self.btn_catat_rusak.setStyleSheet("background-color: #EF4444; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_catat_rusak.clicked.connect(self._buka_dialog_rusak)
        top_bar.addWidget(self.btn_catat_rusak)

        self.btn_ubah_harga = QPushButton("Ubah Harga Jual", self)
        self.btn_ubah_harga.setStyleSheet("background-color: #3B82F6; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_ubah_harga.clicked.connect(self._buka_dialog_ubah_harga)
        top_bar.addWidget(self.btn_ubah_harga)

        layout.addLayout(top_bar)

        # Panel Info Ringkas & Stok
        panel_info = QFrame(self)
        panel_info.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 10px;")
        grid_info = QGridLayout(panel_info)
        grid_info.setSpacing(8)

        self.lbl_nama_kode = QLabel("Pilih barang dari pencarian global di atas...", self)
        self.lbl_nama_kode.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        grid_info.addWidget(self.lbl_nama_kode, 0, 0, 1, 2)

        self.lbl_stok_representasi = QLabel("Stok Sekarang: -", self)
        self.lbl_stok_representasi.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_stok_representasi.setStyleSheet("color: #059669;")
        grid_info.addWidget(self.lbl_stok_representasi, 0, 2)

        self.lbl_nilai_persediaan = QLabel("Nilai Persediaan: -", self)
        grid_info.addWidget(self.lbl_nilai_persediaan, 0, 3)

        self.lbl_kepemilikan = QLabel("Kepemilikan: -", self)
        grid_info.addWidget(self.lbl_kepemilikan, 1, 0)

        self.lbl_harga_jual = QLabel("Harga Jual: -", self)
        grid_info.addWidget(self.lbl_harga_jual, 1, 1)

        self.lbl_laba_satuan = QLabel("Laba Per Satuan Lot Terdekat: -", self)
        grid_info.addWidget(self.lbl_laba_satuan, 1, 2)

        self.lbl_suplier_terakhir = QLabel("Supplier Terakhir: -", self)
        grid_info.addWidget(self.lbl_suplier_terakhir, 1, 3)

        layout.addWidget(panel_info)

        # Tab Widget: Riwayat Mutasi vs Lot FIFO Aktif
        self.tabs = QTabWidget(self)

        # Tab 1: Riwayat Kartu Stok
        tab_mutasi = QWidget()
        lay_m = QVBoxLayout(tab_mutasi)
        lay_m.setContentsMargins(5, 8, 5, 5)

        # Filter Mutasi
        bar_filter = QHBoxLayout()
        bar_filter.addWidget(QLabel("Filter Jenis:", self))
        self.cmb_filter_jenis = QComboBox(self)
        self.cmb_filter_jenis.addItems(["Semua Jenis", "masuk", "keluar_jual", "retur_supplier", "retur_penitip", "rusak", "hilang", "penyesuaian_opname"])
        self.cmb_filter_jenis.currentIndexChanged.connect(self.muat_data)
        bar_filter.addWidget(self.cmb_filter_jenis)

        bar_filter.addStretch()
        btn_segarkan = QPushButton("Segarkan", self)
        btn_segarkan.clicked.connect(self.muat_data)
        bar_filter.addWidget(btn_segarkan)
        lay_m.addLayout(bar_filter)

        self.tbl_mutasi = QTableWidget(self)
        self.tbl_mutasi.setColumnCount(7)
        self.tbl_mutasi.setHorizontalHeaderLabels([
            "Tanggal", "Jenis Mutasi", "Keterangan / Referensi", "Masuk", "Keluar", "Saldo Berjalan", "Nilai Biaya"
        ])
        self.tbl_mutasi.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_mutasi.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_mutasi.setColumnWidth(0, 115)  # Tanggal
        self.tbl_mutasi.setColumnWidth(1, 140)  # Jenis Mutasi
        self.tbl_mutasi.setColumnWidth(3, 90)   # Masuk
        self.tbl_mutasi.setColumnWidth(4, 90)   # Keluar
        self.tbl_mutasi.setColumnWidth(5, 110)  # Saldo Berjalan
        self.tbl_mutasi.setColumnWidth(6, 130)  # Nilai Biaya
        terapkan_style_tabel_global(
            self.tbl_mutasi,
            rata_kanan_kolom=[3, 4, 5, 6]
        )
        lay_m.addWidget(self.tbl_mutasi)

        self.tabs.addTab(tab_mutasi, "Riwayat Kartu Stok")

        # Tab 2: Lot FIFO Aktif
        tab_lot = QWidget()
        lay_l = QVBoxLayout(tab_lot)
        lay_l.setContentsMargins(5, 8, 5, 5)

        self.tbl_lot = QTableWidget(self)
        self.tbl_lot.setColumnCount(7)
        self.tbl_lot.setHorizontalHeaderLabels([
            "Urutan Keluar", "Tanggal Masuk", "Asal Lot", "Pihak (Supplier/Penitip)", "Sisa Unit", "Harga Beli Dasar", "Total Biaya Sisa"
        ])
        self.tbl_lot.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_lot.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tbl_lot.setColumnWidth(0, 110)  # Urutan Keluar
        self.tbl_lot.setColumnWidth(1, 115)  # Tanggal Masuk
        self.tbl_lot.setColumnWidth(2, 110)  # Asal Lot
        self.tbl_lot.setColumnWidth(4, 100)  # Sisa Unit
        self.tbl_lot.setColumnWidth(5, 130)  # Harga Beli Dasar
        self.tbl_lot.setColumnWidth(6, 140)  # Total Biaya Sisa
        terapkan_style_tabel_global(
            self.tbl_lot,
            rata_kanan_kolom=[4, 5, 6]
        )
        lay_l.addWidget(self.tbl_lot)

        self.tabs.addTab(tab_lot, "Daftar Lot FIFO Aktif")

        layout.addWidget(self.tabs)

    def muat_data(self):
        if not self.barang_id_terpilih:
            return

        jenis_f = self.cmb_filter_jenis.currentText()
        filter_jenis = "semua" if jenis_f == "Semua Jenis" else jenis_f

        data = ambil_data_kartu_barang(self.conn, self.barang_id_terpilih, filter_jenis=filter_jenis)
        if not data:
            return

        b = data["info"]
        self.lbl_nama_kode.setText(f"{b['kode']} — {b['nama']} ({b['satuan_dasar']})")
        self.lbl_stok_representasi.setText(f"Stok: {data['stok_representasi']} ({data['status_stok'].upper()})")
        self.lbl_nilai_persediaan.setText(f"Nilai Persediaan: {format_rupiah(data['nilai_persediaan'])}")

        penitip_str = f"Titipan: {b['nama_penitip']}" if b["jenis_kepemilikan"] == "titipan" else "Milik Koperasi"
        self.lbl_kepemilikan.setText(f"Kepemilikan: {penitip_str}")
        self.lbl_harga_jual.setText(f"Harga Jual: {format_rupiah(b['harga_jual'])}")
        self.lbl_laba_satuan.setText(f"Estimasi Laba Berikutnya: {format_rupiah(data['laba_per_satuan_berikutnya'])}")

        supp_str = data["supplier_terakhir"]["nama_supplier"] if data["supplier_terakhir"] else "-"
        self.lbl_suplier_terakhir.setText(f"Supplier Terakhir: {supp_str}")

        # Tabel Mutasi
        mutasi_list = data["riwayat_mutasi"]
        self.tbl_mutasi.setRowCount(len(mutasi_list))
        for row_idx, m in enumerate(mutasi_list):
            self.tbl_mutasi.setItem(row_idx, 0, QTableWidgetItem(format_tanggal_indo(m["tanggal"])))
            
            # Label bahasa ramah untuk jenis mutasi
            peta_jenis = {
                "masuk": "Barang Masuk",
                "keluar_jual": "Penjualan",
                "retur_supplier": "Retur ke Supplier",
                "retur_penitip": "Retur ke Penitip",
                "rusak": "Barang Rusak",
                "hilang": "Barang Hilang",
                "kedaluwarsa": "Kedaluwarsa",
                "penyesuaian_opname": "Penyesuaian Opname"
            }
            jenis_teks = peta_jenis.get(m["jenis"], m["jenis"].capitalize())
            self.tbl_mutasi.setItem(row_idx, 1, QTableWidgetItem(jenis_teks))
            self.tbl_mutasi.setItem(row_idx, 2, QTableWidgetItem(str(m["keterangan_ref"])))

            c_msk = QTableWidgetItem(f"{m['masuk']:,}".replace(",", ".") if m["masuk"] > 0 else "-")
            c_msk.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_mutasi.setItem(row_idx, 3, c_msk)

            c_klr = QTableWidgetItem(f"{m['keluar']:,}".replace(",", ".") if m["keluar"] > 0 else "-")
            c_klr.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_mutasi.setItem(row_idx, 4, c_klr)

            c_sld = QTableWidgetItem(f"{m['saldo_berjalan']:,}".replace(",", "."))
            c_sld.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_mutasi.setItem(row_idx, 5, c_sld)

            c_bya = QTableWidgetItem(format_rupiah(m["biaya"]))
            c_bya.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_mutasi.setItem(row_idx, 6, c_bya)

        # Tabel Lot FIFO
        lots = data["lot_aktif"]
        self.tbl_lot.setRowCount(len(lots))
        for idx, lot in enumerate(lots):
            self.tbl_lot.setItem(idx, 0, QTableWidgetItem(f"Lot Ke-{idx + 1} (Keluar Pertama)" if idx == 0 else f"Lot Ke-{idx + 1}"))
            self.tbl_lot.setItem(idx, 1, QTableWidgetItem(format_tanggal_indo(lot["tanggal_masuk"])))
            self.tbl_lot.setItem(idx, 2, QTableWidgetItem(lot["asal"].capitalize()))
            pihak = lot["nama_penitip"] or lot["nama_supplier"] or "Koperasi"
            self.tbl_lot.setItem(idx, 3, QTableWidgetItem(str(pihak)))

            c_sisa = QTableWidgetItem(f"{lot['qty_sisa']:,}".replace(",", "."))
            c_sisa.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_lot.setItem(idx, 4, c_sisa)

            c_beli = QTableWidgetItem(format_rupiah(lot["harga_beli_per_unit"]))
            c_beli.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_lot.setItem(idx, 5, c_beli)

            c_tbya = QTableWidgetItem(format_rupiah(lot["biaya_sisa"]))
            c_tbya.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_lot.setItem(idx, 6, c_tbya)

    def _buka_dialog_rusak(self):
        if not self.barang_id_terpilih:
            return
        dlg = DialogPenyesuaianCepat(self.conn, self.barang_id_terpilih, self)
        if dlg.exec():
            self.muat_data()

    def _buka_dialog_ubah_harga(self):
        if not self.barang_id_terpilih:
            return
        brg = ambil_barang_by_id(self.conn, self.barang_id_terpilih)
        if not brg:
            return
        dlg = DialogUbahHargaJual(self.conn, self.barang_id_terpilih, brg["harga_jual"], self)
        if dlg.exec():
            self.muat_data()

    def _ke_pembelian(self):
        if self.navigasi_cb:
            self.navigasi_cb("buka_pembelian")
