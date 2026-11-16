"""
app/ui/layar_pembelian.py — Layar Pembelian Toko (Barang Masuk) & Hutang Supplier.
Fitur:
- Satu faktur banyak baris detail barang
- Form input cepat keyboard-friendly (Tab/Enter)
- Menampilkan langsung hasil konversi live ("3 dus = 60 pcs") dan total biaya
- Pemilihan barang dari autocomplete / dropdown pencarian (tanpa ketik ulang nama)
- Status bayar tunai (potong kas toko) atau belum dibayar (hutang supplier)
- Dialog pelunasan / cicilan hutang supplier
- Dialog pembatalan (pembalik) faktur pembelian dengan validasi lot belum terpakai
"""
import sqlite3
from datetime import date
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QComboBox, QSpinBox,
    QDateEdit, QGroupBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QDate

from app.db.repo_pembelian import (
    buat_faktur_pembelian, ambil_daftar_faktur_pembelian,
    ambil_detail_faktur_pembelian, balik_faktur_pembelian,
    bayar_hutang_pembelian
)
from app.db.repo_pihak import ambil_daftar_pihak
from app.db.repo_barang import cari_barang, ambil_satuan_barang, ambil_barang_by_id
from app.util.format import format_rupiah, format_tanggal_indo
from app.ui.komponen.input_rupiah import InputRupiah
from app.layanan.bus_sinyal import langganan, lepas_langganan


class DialogBayarHutang(QDialog):
    """Dialog Pembayaran Hutang Dagang Supplier."""

    def __init__(self, conn: sqlite3.Connection, faktur_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.conn = conn
        self.faktur = faktur_data
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle(f"Bayar Hutang - Faktur {self.faktur['no_faktur']}")
        self.setMinimumWidth(450)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        sisa = self.faktur["sisa_hutang"]
        info = QLabel(
            f"<b>Supplier:</b> {self.faktur['nama_supplier']}<br>"
            f"<b>Total Faktur:</b> {format_rupiah(self.faktur['total_biaya'])}<br>"
            f"<b>Sisa Hutang:</b> <span style='color: #DC2626; font-weight: bold;'>{format_rupiah(sisa)}</span>",
            self
        )
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(10)

        self.input_tanggal = QDateEdit(self)
        self.input_tanggal.setCalendarPopup(True)
        self.input_tanggal.setDate(QDate.currentDate())
        self.input_tanggal.setMinimumHeight(38)
        form.addRow("Tanggal Pembayaran:", self.input_tanggal)

        self.input_nominal = InputRupiah(self)
        self.input_nominal.set_nilai(sisa)
        self.input_nominal.setMinimumHeight(38)
        form.addRow("Nominal Bayar (Rp):", self.input_nominal)

        self.input_ket = QLineEdit(self)
        self.input_ket.setPlaceholderText("Keterangan (misal: Cicilan 1 / Pelunasan)")
        self.input_ket.setMinimumHeight(38)
        form.addRow("Keterangan:", self.input_ket)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_batal = QPushButton("Batal", self)
        btn_batal.setMinimumHeight(42)
        btn_batal.clicked.connect(self.reject)

        btn_simpan = QPushButton("Simpan Pembayaran", self)
        btn_simpan.setMinimumHeight(42)
        btn_simpan.setStyleSheet("background-color: #10B981; color: white; font-weight: bold;")
        btn_simpan.clicked.connect(self._simpan)

        btn_box.addStretch()
        btn_box.addWidget(btn_batal)
        btn_box.addWidget(btn_simpan)
        layout.addLayout(btn_box)

    def _simpan(self) -> None:
        nom = self.input_nominal.ambil_nilai()
        if nom <= 0:
            QMessageBox.warning(self, "Perhatian", "Nominal pembayaran harus lebih dari Rp 0.")
            return

        tgl_str = self.input_tanggal.date().toString("yyyy-MM-dd")
        ket = self.input_ket.text().strip()

        try:
            bayar_hutang_pembelian(self.conn, self.faktur["id"], tgl_str, nom, ket)
            QMessageBox.information(self, "Berhasil", "Pembayaran hutang berhasil disimpan dan kas toko telah dipotong.")
            self.accept()
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Tidak dapat menyimpan pembayaran: {err}")


class DialogInputFaktur(QDialog):
    """Dialog Input Faktur Pembelian Lengkap Multi-Baris."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.items_faktur: List[Dict[str, Any]] = []
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle("Input Pembelian (Faktur Baru)")
        self.resize(850, 620)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header Form: Supplier, No Faktur, Tanggal, Status Bayar
        grp_header = QGroupBox("Informasi Faktur", self)
        lay_header = QFormLayout(grp_header)
        lay_header.setSpacing(10)

        # Baris 1: Supplier & No Faktur
        baris_1 = QHBoxLayout()
        self.combo_supplier = QComboBox(self)
        self.combo_supplier.setMinimumHeight(38)
        self._muat_supplier()
        baris_1.addWidget(self.combo_supplier, stretch=2)

        self.input_no_faktur = QLineEdit(self)
        self.input_no_faktur.setPlaceholderText("Nomor Faktur Supplier")
        self.input_no_faktur.setMinimumHeight(38)
        baris_1.addWidget(self.input_no_faktur, stretch=1)
        lay_header.addRow("Supplier dan No. Faktur *:", baris_1)

        # Baris 2: Tanggal & Status Bayar
        baris_2 = QHBoxLayout()
        self.input_tgl = QDateEdit(self)
        self.input_tgl.setCalendarPopup(True)
        self.input_tgl.setDate(QDate.currentDate())
        self.input_tgl.setMinimumHeight(38)
        baris_2.addWidget(self.input_tgl, stretch=1)

        self.combo_status_bayar = QComboBox(self)
        self.combo_status_bayar.addItem("Tunai (Potong Kas Toko)", "tunai")
        self.combo_status_bayar.addItem("Belum Dibayar (Hutang Dagang)", "belum_dibayar")
        self.combo_status_bayar.setMinimumHeight(38)
        baris_2.addWidget(self.combo_status_bayar, stretch=1)
        lay_header.addRow("Tanggal dan Status Bayar:", baris_2)

        layout.addWidget(grp_header)

        # Input Baris Barang Cepat (Keyboard friendly)
        grp_baris = QGroupBox("Tambah Baris Barang", self)
        lay_baris = QVBoxLayout(grp_baris)
        lay_baris.setSpacing(8)

        bar_input = QHBoxLayout()
        self.combo_barang = QComboBox(self)
        self.combo_barang.setMinimumHeight(38)
        self.combo_barang.setPlaceholderText("-- Pilih Barang --")
        self._muat_barang()
        self.combo_barang.currentIndexChanged.connect(self._on_barang_changed)
        bar_input.addWidget(self.combo_barang, stretch=3)

        self.spin_jumlah = QSpinBox(self)
        self.spin_jumlah.setRange(1, 100000)
        self.spin_jumlah.setValue(1)
        self.spin_jumlah.setMinimumHeight(38)
        self.spin_jumlah.valueChanged.connect(self._update_label_preview)
        bar_input.addWidget(self.spin_jumlah, stretch=1)

        self.combo_satuan = QComboBox(self)
        self.combo_satuan.setMinimumHeight(38)
        self.combo_satuan.currentIndexChanged.connect(self._update_label_preview)
        bar_input.addWidget(self.combo_satuan, stretch=1)

        self.input_harga_satuan = InputRupiah(self)
        self.input_harga_satuan.setPlaceholderText("Harga Beli / Satuan")
        self.input_harga_satuan.setMinimumHeight(38)
        self.input_harga_satuan.textChanged.connect(self._update_label_preview)
        bar_input.addWidget(self.input_harga_satuan, stretch=2)

        btn_tambah_baris = QPushButton("+ Tambah", self)
        btn_tambah_baris.setMinimumHeight(38)
        btn_tambah_baris.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold;")
        btn_tambah_baris.clicked.connect(self._tambah_baris_ke_tabel)
        bar_input.addWidget(btn_tambah_baris)

        lay_baris.addLayout(bar_input)

        # Preview konversi live: contoh "3 dus = 60 pcs | Total: Rp 300.000"
        self.lbl_preview_konversi = QLabel("Hasil Konversi: -", self)
        self.lbl_preview_konversi.setStyleSheet("color: #1D4ED8; font-weight: bold;")
        lay_baris.addWidget(self.lbl_preview_konversi)

        layout.addWidget(grp_baris)

        # Tabel Daftar Baris Barang
        self.tabel = QTableWidget(self)
        self.tabel.setColumnCount(6)
        self.tabel.setHorizontalHeaderLabels([
            "Barang", "Jumlah Input", "Satuan", "Hasil Satuan Dasar", "Harga Satuan", "Total Biaya"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(1, 100)  # Jumlah Input
        self.tabel.setColumnWidth(2, 90)   # Satuan
        self.tabel.setColumnWidth(3, 140)  # Hasil Satuan Dasar
        self.tabel.setColumnWidth(4, 130)  # Harga Satuan
        self.tabel.setColumnWidth(5, 140)  # Total Biaya
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(self.tabel)

        # Ringkasan Total Faktur dan Tombol Aksi
        bot_bar = QHBoxLayout()
        btn_hapus_baris = QPushButton("Hapus Baris Terpilih", self)
        btn_hapus_baris.clicked.connect(self._hapus_baris)
        bot_bar.addWidget(btn_hapus_baris)

        bot_bar.addStretch()

        self.lbl_total_faktur = QLabel("TOTAL: Rp 0", self)
        self.lbl_total_faktur.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_total_faktur.setStyleSheet("color: #047857; margin-right: 15px;")
        bot_bar.addWidget(self.lbl_total_faktur)

        btn_batal = QPushButton("Batal", self)
        btn_batal.setMinimumHeight(42)
        btn_batal.clicked.connect(self.reject)
        bot_bar.addWidget(btn_batal)

        btn_simpan = QPushButton("Simpan Faktur Pembelian", self)
        btn_simpan.setMinimumHeight(42)
        btn_simpan.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; padding: 0 20px;")
        btn_simpan.clicked.connect(self._simpan_faktur)
        bot_bar.addWidget(btn_simpan)

        layout.addLayout(bot_bar)

    def _muat_supplier(self) -> None:
        self.combo_supplier.clear()
        self.combo_supplier.addItem("-- Pilih Supplier --", None)
        supps = ambil_daftar_pihak(self.conn, "supplier", hanya_aktif=True)
        for s in supps:
            self.combo_supplier.addItem(s["nama"], s["id"])

    def _muat_barang(self) -> None:
        self.combo_barang.clear()
        self.combo_barang.addItem("-- Pilih Barang --", None)
        brgs = cari_barang(self.conn, "", hanya_aktif=True, limit=500)
        for b in brgs:
            self.combo_barang.addItem(f"{b['kode']} - {b['nama']}", b["id"])

    def _on_barang_changed(self) -> None:
        b_id = self.combo_barang.currentData()
        self.combo_satuan.clear()
        if not b_id:
            return

        sats = ambil_satuan_barang(self.conn, b_id)
        for s in sats:
            self.combo_satuan.addItem(s["nama_satuan"], s["isi_dalam_satuan_dasar"])
        self._update_label_preview()

    def _update_label_preview(self) -> None:
        b_id = self.combo_barang.currentData()
        if not b_id:
            self.lbl_preview_konversi.setText("Hasil Konversi: -")
            return

        b = ambil_barang_by_id(self.conn, b_id)
        jml = self.spin_jumlah.value()
        sat_nama = self.combo_satuan.currentText()
        isi = self.combo_satuan.currentData() or 1
        hrg = self.input_harga_satuan.ambil_nilai()

        tot_dasar = jml * isi
        tot_biaya = jml * hrg

        self.lbl_preview_konversi.setText(
            f"Hasil Konversi: <b>{jml} {sat_nama} = {tot_dasar:,} {b['satuan_dasar']}</b> | "
            f"Total Biaya: <b>{format_rupiah(tot_biaya)}</b>".replace(",", ".")
        )

    def _tambah_baris_ke_tabel(self) -> None:
        b_id = self.combo_barang.currentData()
        if not b_id:
            QMessageBox.warning(self, "Perhatian", "Silakan pilih barang terlebih dahulu.")
            return

        b = ambil_barang_by_id(self.conn, b_id)
        jml = self.spin_jumlah.value()
        sat_nama = self.combo_satuan.currentText()
        isi = self.combo_satuan.currentData() or 1
        hrg = self.input_harga_satuan.ambil_nilai()

        if jml <= 0 or isi <= 0:
            QMessageBox.warning(self, "Perhatian", "Jumlah dan isi konversi harus > 0.")
            return
        if hrg <= 0:
            QMessageBox.warning(self, "Perhatian", "Harga satuan harus > Rp 0.")
            return

        tot_dasar = jml * isi
        tot_biaya = jml * hrg

        item_baru = {
            "barang_id": b_id,
            "nama_barang": b["nama"],
            "kode_barang": b["kode"],
            "satuan_dasar": b["satuan_dasar"],
            "jumlah_input": jml,
            "satuan_input": sat_nama,
            "isi_per_satuan": isi,
            "jumlah_dasar": tot_dasar,
            "harga_per_satuan_input": hrg,
            "total_biaya": tot_biaya
        }
        self.items_faktur.append(item_baru)
        self._refresh_tabel_items()

        # Reset baris input
        self.spin_jumlah.setValue(1)
        self.input_harga_satuan.set_nilai(0)
        self.combo_barang.setFocus()

    def _refresh_tabel_items(self) -> None:
        self.tabel.setRowCount(len(self.items_faktur))
        total_semua = 0

        for r_idx, it in enumerate(self.items_faktur):
            total_semua += it["total_biaya"]
            self.tabel.setItem(r_idx, 0, QTableWidgetItem(f"{it['kode_barang']} - {it['nama_barang']}"))
            self.tabel.setItem(r_idx, 1, QTableWidgetItem(str(it["jumlah_input"])))
            self.tabel.setItem(r_idx, 2, QTableWidgetItem(it["satuan_input"]))

            dasar_str = f"{it['jumlah_dasar']:,} {it['satuan_dasar']}".replace(",", ".")
            self.tabel.setItem(r_idx, 3, QTableWidgetItem(dasar_str))

            hrg_item = QTableWidgetItem(format_rupiah(it["harga_per_satuan_input"]))
            hrg_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(r_idx, 4, hrg_item)

            tot_item = QTableWidgetItem(format_rupiah(it["total_biaya"]))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(r_idx, 5, tot_item)

        self.lbl_total_faktur.setText(f"TOTAL: {format_rupiah(total_semua)}")

    def _hapus_baris(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.items_faktur):
            return
        self.items_faktur.pop(baris)
        self._refresh_tabel_items()

    def _simpan_faktur(self) -> None:
        supp_id = self.combo_supplier.currentData()
        no_faktur = self.input_no_faktur.text().strip()
        tgl_str = self.input_tgl.date().toString("yyyy-MM-dd")
        status_bayar = self.combo_status_bayar.currentData()

        if not supp_id:
            QMessageBox.warning(self, "Perhatian", "Silakan pilih supplier.")
            return
        if not no_faktur:
            QMessageBox.warning(self, "Perhatian", "Nomor faktur supplier wajib diisi.")
            return
        if not self.items_faktur:
            QMessageBox.warning(self, "Perhatian", "Faktur harus memiliki minimal 1 baris barang.")
            return

        try:
            buat_faktur_pembelian(
                self.conn,
                no_faktur=no_faktur,
                supplier_id=supp_id,
                tanggal=tgl_str,
                status_bayar=status_bayar,
                items=self.items_faktur
            )
            QMessageBox.information(self, "Berhasil", f"Faktur pembelian {no_faktur} berhasil disimpan!")
            self.accept()
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Tidak dapat menyimpan faktur: {err}")


class LayarPembelian(QWidget):
    """Layar Utama Pembelian dan Hutang Dagang Supplier."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.daftar_faktur: List[Dict[str, Any]] = []
        self._inisialisasi_ui()
        langganan("pembelian_berubah", self.muat_data)

    def closeEvent(self, event):
        lepas_langganan("pembelian_berubah", self.muat_data)
        super().closeEvent(event)

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(12)

        # Header dan Pencarian
        top_bar = QHBoxLayout()
        lbl_cari = QLabel("Cari Faktur / Supplier:", self)
        lbl_cari.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        top_bar.addWidget(lbl_cari)

        self.input_cari = QLineEdit(self)
        self.input_cari.setPlaceholderText("Ketik nomor faktur atau nama supplier...")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.textChanged.connect(self.muat_data)
        top_bar.addWidget(self.input_cari)

        btn_input_baru = QPushButton("+ Input Pembelian Baru", self)
        btn_input_baru.setMinimumHeight(40)
        btn_input_baru.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 0 16px;")
        btn_input_baru.clicked.connect(self._buka_input_faktur)
        top_bar.addWidget(btn_input_baru)

        layout.addLayout(top_bar)

        # Tabel Riwayat Faktur
        self.tabel = QTableWidget(self)
        self.tabel.setColumnCount(8)
        self.tabel.setHorizontalHeaderLabels([
            "ID", "Tanggal", "No. Faktur", "Supplier", "Total Biaya",
            "Metode Bayar", "Status Pelunasan", "Status Efektif"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 50)   # ID
        self.tabel.setColumnWidth(1, 115)  # Tanggal
        self.tabel.setColumnWidth(2, 130)  # No. Faktur
        self.tabel.setColumnWidth(4, 140)  # Total Biaya
        self.tabel.setColumnWidth(5, 120)  # Metode Bayar
        self.tabel.setColumnWidth(6, 130)  # Status Pelunasan
        self.tabel.setColumnWidth(7, 110)  # Status Efektif
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setDefaultSectionSize(40)
        layout.addWidget(self.tabel)

        # Bar Tombol Bawah
        bot_bar = QHBoxLayout()
        btn_bayar = QPushButton("Bayar Hutang Supplier", self)
        btn_bayar.setMinimumHeight(42)
        btn_bayar.setStyleSheet("background-color: #10B981; color: white; font-weight: bold;")
        btn_bayar.clicked.connect(self._bayar_hutang)

        btn_detail = QPushButton("Lihat Rincian Barang", self)
        btn_detail.setMinimumHeight(42)
        btn_detail.clicked.connect(self._lihat_rincian)

        btn_batal = QPushButton("Batalkan Faktur (Pembalik)", self)
        btn_batal.setMinimumHeight(42)
        btn_batal.clicked.connect(self._batalkan_faktur)

        bot_bar.addWidget(btn_bayar)
        bot_bar.addWidget(btn_detail)
        bot_bar.addWidget(btn_batal)
        bot_bar.addStretch()
        layout.addLayout(bot_bar)

        self.muat_data()

    def muat_data(self) -> None:
        k = self.input_cari.text().strip()
        self.daftar_faktur = ambil_daftar_faktur_pembelian(self.conn, kata_kunci=k, limit=150)
        self.tabel.setRowCount(len(self.daftar_faktur))

        for idx, f in enumerate(self.daftar_faktur):
            self.tabel.setItem(idx, 0, QTableWidgetItem(str(f["id"])))
            self.tabel.setItem(idx, 1, QTableWidgetItem(format_tanggal_indo(f["tanggal"])))
            self.tabel.setItem(idx, 2, QTableWidgetItem(f["no_faktur"]))
            self.tabel.setItem(idx, 3, QTableWidgetItem(f["nama_supplier"]))

            tot_item = QTableWidgetItem(format_rupiah(f["total_biaya"]))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(idx, 4, tot_item)

            metode_str = "Tunai" if f["status_bayar"] == "tunai" else "Hutang Dagang"
            self.tabel.setItem(idx, 5, QTableWidgetItem(metode_str))

            status_item = QTableWidgetItem(f["status_lunas"])
            if "Belum" in f["status_lunas"]:
                status_item.setForeground(Qt.GlobalColor.darkRed)
            else:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            self.tabel.setItem(idx, 6, status_item)

            efek_str = f.get("status_efektif", "NORMAL")
            efek_item = QTableWidgetItem(efek_str)
            efek_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if efek_str == "DIBATALKAN":
                efek_item.setForeground(Qt.GlobalColor.gray)
            elif efek_str == "PEMBALIK":
                efek_item.setForeground(Qt.GlobalColor.darkRed)
            self.tabel.setItem(idx, 7, efek_item)

    def _ambil_terpilih(self) -> Optional[Dict[str, Any]]:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_faktur):
            QMessageBox.information(self, "Pilih Faktur", "Silakan klik baris faktur terlebih dahulu.")
            return None
        return self.daftar_faktur[baris]

    def _buka_input_faktur(self) -> None:
        dlg = DialogInputFaktur(self.conn, parent=self)
        if dlg.exec():
            self.muat_data()

    def _bayar_hutang(self) -> None:
        f = self._ambil_terpilih()
        if not f:
            return
        if f["status_bayar"] == "tunai":
            QMessageBox.information(self, "Informasi", "Faktur ini dibayar tunai (tidak memiliki hutang).")
            return
        if f["sisa_hutang"] <= 0:
            QMessageBox.information(self, "Informasi", "Hutang faktur ini sudah lunas sepenuhnya.")
            return

        dlg = DialogBayarHutang(self.conn, f, parent=self)
        if dlg.exec():
            self.muat_data()

    def _lihat_rincian(self) -> None:
        f = self._ambil_terpilih()
        if not f:
            return
        try:
            detail = ambil_detail_faktur_pembelian(self.conn, f["id"])
            teks = f"Rincian Faktur: {detail['no_faktur']} ({detail['nama_supplier']})\n\n"
            for it in detail["items"]:
                teks += (
                    f"- {it['kode_barang']} {it['nama_barang']}: "
                    f"{it['jumlah_input']} {it['satuan_input']} ({it['jumlah_dasar']} {it['satuan_dasar']}) "
                    f"@ {format_rupiah(it['harga_per_satuan_input'])} = {format_rupiah(it['total_biaya'])}\n"
                )
            QMessageBox.information(self, "Rincian Barang Faktur", teks)
        except Exception as err:
            QMessageBox.critical(self, "Error", f"Gagal membaca rincian: {err}")

    def _batalkan_faktur(self) -> None:
        f = self._ambil_terpilih()
        if not f:
            return
        if f.get("status_efektif") != "NORMAL":
            QMessageBox.warning(self, "Perhatian", "Hanya faktur dengan status NORMAL yang dapat dibatalkan.")
            return

        tanya = QMessageBox.question(
            self, "Konfirmasi Pembatalan Faktur",
            f"Apakah Anda yakin ingin membatalkan Faktur {f['no_faktur']}?\n\n"
            "Catatan: Pembatalan hanya dapat dilakukan jika lot stok belum terpakai.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if tanya == QMessageBox.StandardButton.Yes:
            tgl_hari_ini = date.today().isoformat()
            try:
                balik_faktur_pembelian(self.conn, f["id"], tgl_hari_ini, "Pembatalan oleh admin")
                QMessageBox.information(self, "Berhasil", f"Faktur {f['no_faktur']} berhasil dibatalkan!")
                self.muat_data()
            except Exception as err:
                QMessageBox.critical(self, "Gagal Membatalkan", str(err))
