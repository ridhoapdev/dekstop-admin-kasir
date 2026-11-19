"""
app/ui/layar_barang.py — Layar Master Data Barang dan Satuan Konversi Melekat.
Font besar, tombol besar, istilah sederhana, live search toleran kata kunci/kode/nama,
serta dialog manajemen konversi satuan melekat per barang.
"""
import sqlite3
from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QTextEdit, QComboBox,
    QSpinBox, QCheckBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from app.db.repo_barang import (
    tambah_barang, ubah_barang, cari_barang, nonaktifkan_barang,
    ambil_satuan_barang, tambah_satuan_barang, ubah_satuan_barang,
    cek_nama_mirip_barang, ambil_barang_by_id
)
from app.db.repo_pihak import ambil_daftar_pihak
from app.util.format import format_rupiah
from app.ui.komponen.input_rupiah import InputRupiah
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global
from app.layanan.bus_sinyal import langganan, lepas_langganan


class DialogSatuanBarang(QDialog):
    """Dialog Kelola Satuan dan Konversi Melekat pada Barang."""

    def __init__(self, conn: sqlite3.Connection, barang_id: int, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.barang_id = barang_id
        self.barang = ambil_barang_by_id(conn, barang_id)
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle(f"Satuan dan Konversi - {self.barang['nama']}")
        self.resize(650, 420)
        self.setMinimumWidth(620)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        info = QLabel(
            f"<b>Satuan Dasar:</b> {self.barang['satuan_dasar']}<br>"
            "<small style='color: #4B5563;'>Setiap satuan di bawah ini menentukan berapa isi dalam satuan dasar.<br>"
            "Contoh: jika satuan dasar 'pcs', maka 1 dus = 20 pcs.</small>",
            self
        )
        layout.addWidget(info)

        # Tabel satuan
        self.tabel = QTableWidget(self)
        self.tabel.setColumnCount(4)
        self.tabel.setHorizontalHeaderLabels(["ID", "Nama Satuan", "Isi Satuan Dasar", "Status"])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 50)
        self.tabel.setColumnWidth(2, 160)
        self.tabel.setColumnWidth(3, 220)
        terapkan_style_tabel_global(
            self.tabel,
            rata_kanan_kolom=[2],
            kolom_sembunyi=[0]
        )
        layout.addWidget(self.tabel)

        # Form tambah satuan baru
        box_input = QHBoxLayout()
        box_input.setSpacing(8)
        self.input_nama_satuan = QLineEdit(self)
        self.input_nama_satuan.setPlaceholderText("Nama (misal: dus, renteng, box)")
        self.input_nama_satuan.setMinimumHeight(38)

        self.input_isi = QSpinBox(self)
        self.input_isi.setRange(1, 1000000)
        self.input_isi.setValue(10)
        self.input_isi.setMinimumHeight(38)
        self.input_isi.setMinimumWidth(130)
        self.input_isi.setSuffix(f" {self.barang['satuan_dasar']}")

        btn_tambah = QPushButton("+ Tambah Satuan", self)
        btn_tambah.setMinimumHeight(38)
        btn_tambah.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold;")
        btn_tambah.clicked.connect(self._tambah_satuan)

        box_input.addWidget(self.input_nama_satuan, 3)
        box_input.addWidget(self.input_isi, 2)
        box_input.addWidget(btn_tambah, 2)
        layout.addLayout(box_input)

        # Tombol Tutup
        btn_tutup = QPushButton("Tutup", self)
        btn_tutup.setMinimumHeight(40)
        btn_tutup.clicked.connect(self.accept)
        layout.addWidget(btn_tutup)

        self.muat_satuan()

    def muat_satuan(self) -> None:
        daftar = ambil_satuan_barang(self.conn, self.barang_id)
        self.tabel.setRowCount(len(daftar))
        for r_idx, s in enumerate(daftar):
            self.tabel.setItem(r_idx, 0, QTableWidgetItem(str(s["id"])))
            self.tabel.setItem(r_idx, 1, QTableWidgetItem(s["nama_satuan"]))
            isi_str = f"{s['isi_dalam_satuan_dasar']} {self.barang['satuan_dasar']}"
            item_isi = QTableWidgetItem(isi_str)
            item_isi.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(r_idx, 2, item_isi)

            st_str = "Terkunci (Dipakai Transaksi)" if s["terkunci"] else "Dapat Diubah"
            st_item = QTableWidgetItem(st_str)
            if s["terkunci"]:
                st_item.setForeground(Qt.GlobalColor.darkRed)
            self.tabel.setItem(r_idx, 3, st_item)

    def _tambah_satuan(self) -> None:
        nama = self.input_nama_satuan.text().strip().lower()
        isi = self.input_isi.value()
        if not nama:
            QMessageBox.warning(self, "Perhatian", "Nama satuan tidak boleh kosong.")
            return

        try:
            tambah_satuan_barang(self.conn, self.barang_id, nama, isi)
            self.input_nama_satuan.clear()
            self.input_isi.setValue(10)
            self.muat_satuan()
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal menambahkan satuan: {err}")


class DialogFormBarang(QDialog):
    """Dialog Tambah / Ubah Master Barang."""

    def __init__(self, conn: sqlite3.Connection, data_edit: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.data_edit = data_edit
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        aksi = "Ubah Data" if self.data_edit else "Tambah"
        self.setWindowTitle(f"{aksi} Master Barang")
        self.setMinimumWidth(560)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.input_kode = QLineEdit(self)
        self.input_kode.setPlaceholderText("Kode unik (misal: BRG-0001, atau barcode)")
        self.input_kode.setMinimumHeight(38)
        form.addRow("Kode Barang *:", self.input_kode)

        self.input_nama = QLineEdit(self)
        self.input_nama.setPlaceholderText("Nama produk / barang")
        self.input_nama.setMinimumHeight(38)
        form.addRow("Nama Barang *:", self.input_nama)

        self.input_kategori = QLineEdit(self)
        self.input_kategori.setPlaceholderText("Kategori (misal: Minuman, Sembako)")
        self.input_kategori.setMinimumHeight(38)
        form.addRow("Kategori:", self.input_kategori)

        self.input_satuan_dasar = QLineEdit(self)
        self.input_satuan_dasar.setPlaceholderText("Satuan terkecil bulat (misal: pcs, botol, g, butir)")
        self.input_satuan_dasar.setMinimumHeight(38)
        form.addRow("Satuan Dasar *:", self.input_satuan_dasar)

        self.input_kata_kunci = QLineEdit(self)
        self.input_kata_kunci.setPlaceholderText("Alias pencarian (misal: pucuk harum teh melati)")
        self.input_kata_kunci.setMinimumHeight(38)
        form.addRow("Kata Kunci (Alias):", self.input_kata_kunci)

        self.input_harga_jual = InputRupiah(self)
        self.input_harga_jual.setMinimumHeight(38)
        form.addRow("Harga Jual Default:", self.input_harga_jual)

        self.combo_kepemilikan = QComboBox(self)
        self.combo_kepemilikan.addItems(["milik_koperasi", "titipan"])
        self.combo_kepemilikan.setItemText(0, "Milik Koperasi")
        self.combo_kepemilikan.setItemText(1, "Barang Titipan")
        self.combo_kepemilikan.setMinimumHeight(38)
        self.combo_kepemilikan.currentIndexChanged.connect(self._toggle_penitip)
        form.addRow("Kepemilikan:", self.combo_kepemilikan)

        self.combo_penitip = QComboBox(self)
        self.combo_penitip.setMinimumHeight(38)
        self._muat_penitip()
        form.addRow("Pihak Penitip:", self.combo_penitip)

        self.spin_stok_min = QSpinBox(self)
        self.spin_stok_min.setRange(0, 1000000)
        self.spin_stok_min.setMinimumHeight(38)
        form.addRow("Stok Minimum:", self.spin_stok_min)

        self.chk_aktif = QCheckBox("Barang Aktif", self)
        self.chk_aktif.setChecked(True)
        if self.data_edit:
            form.addRow("Status:", self.chk_aktif)
        else:
            self.chk_aktif.hide()

        layout.addLayout(form)

        # Tombol Aksi
        btn_box = QHBoxLayout()
        btn_batal = QPushButton("Batal", self)
        btn_batal.setMinimumHeight(42)
        btn_batal.clicked.connect(self.reject)

        btn_simpan = QPushButton("Simpan", self)
        btn_simpan.setMinimumHeight(42)
        btn_simpan.setStyleSheet("background-color: #10B981; color: white; font-weight: bold;")
        btn_simpan.clicked.connect(self._simpan)

        btn_box.addStretch()
        btn_box.addWidget(btn_batal)
        btn_box.addWidget(btn_simpan)
        layout.addLayout(btn_box)

        self._toggle_penitip()

        if self.data_edit:
            self._isi_data_edit()

    def _muat_penitip(self) -> None:
        self.combo_penitip.clear()
        self.combo_penitip.addItem("-- Pilih Penitip --", None)
        penitip_list = ambil_daftar_pihak(self.conn, "penitip", hanya_aktif=True)
        for p in penitip_list:
            self.combo_penitip.addItem(p["nama"], p["id"])

    def _toggle_penitip(self) -> None:
        is_titipan = (self.combo_kepemilikan.currentIndex() == 1)
        self.combo_penitip.setEnabled(is_titipan)

    def _isi_data_edit(self) -> None:
        d = self.data_edit
        self.input_kode.setText(d.get("kode", ""))
        self.input_nama.setText(d.get("nama", ""))
        self.input_kategori.setText(d.get("kategori", "") or "")
        self.input_satuan_dasar.setText(d.get("satuan_dasar", ""))
        self.input_kata_kunci.setText(d.get("kata_kunci", "") or "")
        self.input_harga_jual.set_nilai(d.get("harga_jual", 0))

        idx_kep = 1 if d.get("jenis_kepemilikan") == "titipan" else 0
        self.combo_kepemilikan.setCurrentIndex(idx_kep)
        p_id = d.get("penitip_id")
        if p_id:
            idx_p = self.combo_penitip.findData(p_id)
            if idx_p >= 0:
                self.combo_penitip.setCurrentIndex(idx_p)

        self.spin_stok_min.setValue(d.get("stok_minimum", 0))
        self.chk_aktif.setChecked(bool(d.get("aktif", 1)))

    def _simpan(self) -> None:
        kode = self.input_kode.text().strip()
        nama = self.input_nama.text().strip()
        satuan = self.input_satuan_dasar.text().strip()
        kategori = self.input_kategori.text().strip()
        kata_kunci = self.input_kata_kunci.text().strip()
        harga_jual = self.input_harga_jual.ambil_nilai()
        jenis_kep = "titipan" if self.combo_kepemilikan.currentIndex() == 1 else "milik_koperasi"
        penitip_id = self.combo_penitip.currentData() if jenis_kep == "titipan" else None
        stok_min = self.spin_stok_min.value()

        if not kode or not nama or not satuan:
            QMessageBox.warning(self, "Perhatian", "Kode, Nama, dan Satuan Dasar wajib diisi.")
            return

        if jenis_kep == "titipan" and not penitip_id:
            QMessageBox.warning(self, "Perhatian", "Untuk barang titipan, wajib memilih penitip.")
            return

        # Peringatan fuzzy match nama mirip
        id_edit = self.data_edit["id"] if self.data_edit else None
        mirip = cek_nama_mirip_barang(self.conn, nama, kecualikan_id=id_edit)
        if mirip:
            str_mirip = "\n".join(f"- {m['nama']} ({m['persen']}% mirip)" for m in mirip[:3])
            tanya = QMessageBox.question(
                self, "Peringatan Nama Mirip",
                f"Barang dengan nama serupa sudah ada:\n{str_mirip}\n\nTetap simpan data ini?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if tanya != QMessageBox.StandardButton.Yes:
                return

        try:
            if self.data_edit:
                ubah_barang(
                    self.conn, id_edit, kode, nama, satuan,
                    kategori, kata_kunci, harga_jual, jenis_kep,
                    penitip_id, stok_min, aktif=1 if self.chk_aktif.isChecked() else 0
                )
            else:
                tambah_barang(
                    self.conn, kode, nama, satuan,
                    kategori, kata_kunci, harga_jual, jenis_kep,
                    penitip_id, stok_min
                )
            self.accept()
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal menyimpan barang: {err}")


class LayarBarang(QWidget):
    """Layar Utama Master Barang."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.daftar_barang: List[Dict[str, Any]] = []
        self._inisialisasi_ui()
        langganan("barang_berubah", self.muat_data)

    def closeEvent(self, event):
        lepas_langganan("barang_berubah", self.muat_data)
        super().closeEvent(event)

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(12)

        # Header dan Kotak Pencarian
        top_bar = QHBoxLayout()
        lbl_cari = QLabel("Cari Barang:", self)
        lbl_cari.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        top_bar.addWidget(lbl_cari)

        self.input_cari = QLineEdit(self)
        self.input_cari.setPlaceholderText("Ketik nama, kode, atau kata kunci (contoh: 'pucuk')...")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.textChanged.connect(self.muat_data)
        top_bar.addWidget(self.input_cari)

        btn_tambah = QPushButton("+ Tambah Barang Baru", self)
        btn_tambah.setMinimumHeight(40)
        btn_tambah.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 0 16px;")
        btn_tambah.clicked.connect(self._buka_dialog_tambah)
        top_bar.addWidget(btn_tambah)

        layout.addLayout(top_bar)

        # Tabel Barang
        self.tabel = QTableWidget(self)
        self.tabel.setColumnCount(8)
        self.tabel.setHorizontalHeaderLabels([
            "ID", "Kode", "Nama Barang", "Kategori", "Satuan Dasar",
            "Harga Jual Default", "Kepemilikan", "Status"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 50)   # ID
        self.tabel.setColumnWidth(1, 110)  # Kode
        self.tabel.setColumnWidth(3, 120)  # Kategori
        self.tabel.setColumnWidth(4, 110)  # Satuan Dasar
        self.tabel.setColumnWidth(5, 140)  # Harga Jual
        self.tabel.setColumnWidth(6, 130)  # Kepemilikan
        self.tabel.setColumnWidth(7, 90)   # Status
        terapkan_style_tabel_global(
            self.tabel,
            rata_kanan_kolom=[5],
            kolom_status=7,
            kolom_sembunyi=[0]
        )
        layout.addWidget(self.tabel)

        # Bar Tombol Bawah
        bot_bar = QHBoxLayout()
        btn_edit = QPushButton("Ubah Data Barang", self)
        btn_edit.setMinimumHeight(42)
        btn_edit.clicked.connect(self._buka_dialog_edit)

        btn_satuan = QPushButton("Atur Satuan Konversi", self)
        btn_satuan.setMinimumHeight(42)
        btn_satuan.setStyleSheet("background-color: #0284C7; color: white; font-weight: bold;")
        btn_satuan.clicked.connect(self._buka_dialog_satuan)

        btn_nonaktif = QPushButton("Nonaktifkan / Hapus", self)
        btn_nonaktif.setMinimumHeight(42)
        btn_nonaktif.clicked.connect(self._nonaktifkan_barang)

        bot_bar.addWidget(btn_edit)
        bot_bar.addWidget(btn_satuan)
        bot_bar.addWidget(btn_nonaktif)
        bot_bar.addStretch()
        layout.addLayout(bot_bar)

        self.muat_data()

    def muat_data(self) -> None:
        kata_kunci = self.input_cari.text().strip()
        self.daftar_barang = cari_barang(self.conn, kata_kunci, hanya_aktif=False, limit=100)
        self.tabel.setRowCount(len(self.daftar_barang))

        for idx, b in enumerate(self.daftar_barang):
            self.tabel.setItem(idx, 0, QTableWidgetItem(str(b["id"])))
            self.tabel.setItem(idx, 1, QTableWidgetItem(b["kode"]))
            self.tabel.setItem(idx, 2, QTableWidgetItem(b["nama"]))
            self.tabel.setItem(idx, 3, QTableWidgetItem(b["kategori"] or "-"))
            self.tabel.setItem(idx, 4, QTableWidgetItem(b["satuan_dasar"]))

            hrg_item = QTableWidgetItem(format_rupiah(b["harga_jual"]))
            hrg_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(idx, 5, hrg_item)

            kep_str = "Titipan" if b["jenis_kepemilikan"] == "titipan" else "Koperasi"
            if b.get("nama_penitip"):
                kep_str += f" ({b['nama_penitip']})"
            self.tabel.setItem(idx, 6, QTableWidgetItem(kep_str))

            st_str = "Aktif" if b["aktif"] else "Nonaktif"
            st_item = QTableWidgetItem(st_str)
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if not b["aktif"]:
                st_item.setForeground(Qt.GlobalColor.gray)
            self.tabel.setItem(idx, 7, st_item)

    def _ambil_terpilih(self) -> Optional[Dict[str, Any]]:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_barang):
            QMessageBox.information(self, "Pilih Barang", "Silakan klik baris barang terlebih dahulu.")
            return None
        return self.daftar_barang[baris]

    def _buka_dialog_tambah(self) -> None:
        dlg = DialogFormBarang(self.conn, parent=self)
        if dlg.exec():
            self.muat_data()

    def _buka_dialog_edit(self) -> None:
        b = self._ambil_terpilih()
        if not b:
            return
        dlg = DialogFormBarang(self.conn, data_edit=b, parent=self)
        if dlg.exec():
            self.muat_data()

    def _buka_dialog_satuan(self) -> None:
        b = self._ambil_terpilih()
        if not b:
            return
        dlg = DialogSatuanBarang(self.conn, b["id"], parent=self)
        dlg.exec()

    def _nonaktifkan_barang(self) -> None:
        b = self._ambil_terpilih()
        if not b:
            return
        tanya = QMessageBox.question(
            self, "Konfirmasi",
            f"Apakah Anda yakin ingin menonaktifkan atau menghapus barang '{b['nama']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if tanya == QMessageBox.StandardButton.Yes:
            try:
                nonaktifkan_barang(self.conn, b["id"])
                self.muat_data()
            except Exception as e:
                QMessageBox.critical(self, "Gagal", f"Gagal memproses barang: {e}")
