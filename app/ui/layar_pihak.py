"""
app/ui/layar_pihak.py — Tampilan Master Data Pihak Terkait Toko (Supplier, Penitip, Pembeli).
Font besar, tombol besar, istilah sederhana, peringatan nama mirip (fuzzy match),
dan sinkronisasi real-time via event bus.
"""
import sqlite3
from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QTextEdit, QTabWidget,
    QCheckBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from app.db.repo_pihak import (
    ambil_daftar_pihak, tambah_pihak, ubah_pihak, cek_nama_mirip_pihak
)
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global
from app.layanan.bus_sinyal import langganan, lepas_langganan


class DialogFormPihak(QDialog):
    """Dialog Tambah / Edit Pihak (Supplier, Penitip, atau Pembeli)."""

    def __init__(self, conn: sqlite3.Connection, jenis_pihak: str, data_edit: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.jenis_pihak = jenis_pihak
        self.data_edit = data_edit
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        judul_jenis = self.jenis_pihak.capitalize()
        aksi_judul = "Ubah Data" if self.data_edit else "Tambah"
        self.setWindowTitle(f"{aksi_judul} {judul_jenis}")
        self.setMinimumWidth(480)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.input_nama = QLineEdit(self)
        self.input_nama.setPlaceholderText(f"Nama lengkap {self.jenis_pihak}")
        self.input_nama.setMinimumHeight(40)
        form.addRow("Nama *:", self.input_nama)

        self.input_hp = QLineEdit(self)
        self.input_hp.setPlaceholderText("Nomor telepon / WhatsApp")
        self.input_hp.setMinimumHeight(40)
        form.addRow("Nomor HP:", self.input_hp)

        self.input_alamat = QLineEdit(self)
        self.input_alamat.setPlaceholderText("Alamat atau lokasi")
        self.input_alamat.setMinimumHeight(40)
        form.addRow("Alamat:", self.input_alamat)

        self.input_catatan = QTextEdit(self)
        self.input_catatan.setPlaceholderText("Catatan tambahan (opsional)")
        self.input_catatan.setMaximumHeight(80)
        form.addRow("Catatan:", self.input_catatan)

        self.chk_aktif = QCheckBox("Status Aktif", self)
        self.chk_aktif.setChecked(True)
        if self.data_edit:
            form.addRow("Status:", self.chk_aktif)
        else:
            self.chk_aktif.hide()

        layout.addLayout(form)

        # Tombol aksi
        btn_box = QHBoxLayout()
        btn_batal = QPushButton("Batal", self)
        btn_batal.setMinimumHeight(42)
        btn_batal.clicked.connect(self.reject)

        self.btn_simpan = QPushButton("Simpan", self)
        self.btn_simpan.setMinimumHeight(42)
        self.btn_simpan.setStyleSheet("background-color: #10B981; color: white; font-weight: bold;")
        self.btn_simpan.clicked.connect(self._simpan)

        btn_box.addStretch()
        btn_box.addWidget(btn_batal)
        btn_box.addWidget(self.btn_simpan)
        layout.addLayout(btn_box)

        # Isi data jika edit
        if self.data_edit:
            self.input_nama.setText(self.data_edit.get("nama", ""))
            self.input_hp.setText(self.data_edit.get("no_hp", "") or "")
            self.input_alamat.setText(self.data_edit.get("alamat", "") or "")
            self.input_catatan.setPlainText(self.data_edit.get("catatan", "") or "")
            self.chk_aktif.setChecked(bool(self.data_edit.get("aktif", 1)))

    def _simpan(self) -> None:
        nama = self.input_nama.text().strip()
        if not nama:
            QMessageBox.warning(self, "Perhatian", f"Nama {self.jenis_pihak} wajib diisi.")
            self.input_nama.setFocus()
            return

        # Peringatan nama mirip (fuzzy matching)
        id_edit = self.data_edit["id"] if self.data_edit else None
        mirip = cek_nama_mirip_pihak(self.conn, self.jenis_pihak, nama, kecualikan_id=id_edit)
        if mirip:
            nama_mirip_str = "\n".join(f"- {m['nama']} (kemiripan {m['persen']}%)" for m in mirip[:3])
            tanya = QMessageBox.question(
                self,
                "Peringatan Nama Mirip",
                f"Ditemukan nama yang mirip sudah terdaftar:\n{nama_mirip_str}\n\nApakah Anda yakin ingin tetap menyimpan?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if tanya != QMessageBox.StandardButton.Yes:
                return

        no_hp = self.input_hp.text().strip()
        alamat = self.input_alamat.text().strip()
        catatan = self.input_catatan.toPlainText().strip()

        try:
            if self.data_edit:
                ubah_pihak(
                    self.conn, self.jenis_pihak, id_edit,
                    nama, no_hp, alamat, catatan,
                    aktif=1 if self.chk_aktif.isChecked() else 0
                )
            else:
                tambah_pihak(self.conn, self.jenis_pihak, nama, no_hp, alamat, catatan)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Gagal", f"Tidak dapat menyimpan data: {e}")


class LayarPihak(QWidget):
    """Layar Pengelolaan Master Supplier, Penitip, dan Pembeli."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._inisialisasi_ui()
        langganan("pihak_berubah", self.muat_data)

    def closeEvent(self, event):
        lepas_langganan("pihak_berubah", self.muat_data)
        super().closeEvent(event)

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Tab Widget untuk Supplier, Penitip, Pembeli
        self.tabs = QTabWidget(self)
        self.tabs.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))

        self.tab_supplier = self._buat_halaman_pihak("supplier")
        self.tab_penitip = self._buat_halaman_pihak("penitip")
        self.tab_pembeli = self._buat_halaman_pihak("pembeli")

        self.tabs.addTab(self.tab_supplier, "Pemasok (Supplier)")
        self.tabs.addTab(self.tab_penitip, "Penitip Barang")
        self.tabs.addTab(self.tab_pembeli, "Pelanggan (Pembeli)")

        layout.addWidget(self.tabs)
        self.muat_data()

    def _buat_halaman_pihak(self, jenis: str) -> QWidget:
        wadah = QWidget(self)
        lay = QVBoxLayout(wadah)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)

        # Bar aksi atas
        bar = QHBoxLayout()
        btn_tambah = QPushButton(f"+ Tambah {jenis.capitalize()}", wadah)
        btn_tambah.setMinimumHeight(42)
        btn_tambah.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 0 16px;")
        btn_tambah.clicked.connect(lambda: self._buka_dialog_tambah(jenis))

        btn_edit = QPushButton("Ubah Data", wadah)
        btn_edit.setMinimumHeight(42)
        btn_edit.clicked.connect(lambda: self._buka_dialog_edit(jenis))

        bar.addWidget(btn_tambah)
        bar.addWidget(btn_edit)
        bar.addStretch()
        lay.addLayout(bar)

        # Tabel
        tabel = QTableWidget(wadah)
        tabel.setColumnCount(6)
        tabel.setHorizontalHeaderLabels(["ID", "Nama", "Nomor HP", "Alamat", "Catatan", "Status"])
        tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tabel.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        tabel.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        tabel.setColumnWidth(0, 50)   # ID
        tabel.setColumnWidth(2, 140)  # Nomor HP
        tabel.setColumnWidth(4, 180)  # Catatan
        tabel.setColumnWidth(5, 90)   # Status
        terapkan_style_tabel_global(
            tabel,
            kolom_status=5,
            kolom_sembunyi=[0]
        )
        lay.addWidget(tabel)

        setattr(self, f"tabel_{jenis}", tabel)
        setattr(self, f"data_{jenis}", [])
        return wadah

    def muat_data(self) -> None:
        for jenis in ("supplier", "penitip", "pembeli"):
            tabel: QTableWidget = getattr(self, f"tabel_{jenis}")
            daftar = ambil_daftar_pihak(self.conn, jenis, hanya_aktif=False)
            setattr(self, f"data_{jenis}", daftar)
            tabel.setRowCount(len(daftar))

            for row_idx, p in enumerate(daftar):
                id_item = QTableWidgetItem(str(p["id"]))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                nama_item = QTableWidgetItem(p["nama"])
                hp_item = QTableWidgetItem(p["no_hp"] or "-")
                alm_item = QTableWidgetItem(p["alamat"] or "-")
                cat_item = QTableWidgetItem(p["catatan"] or "-")
                status_str = "Aktif" if p["aktif"] else "Nonaktif"
                st_item = QTableWidgetItem(status_str)
                st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if not p["aktif"]:
                    st_item.setForeground(Qt.GlobalColor.gray)

                tabel.setItem(row_idx, 0, id_item)
                tabel.setItem(row_idx, 1, nama_item)
                tabel.setItem(row_idx, 2, hp_item)
                tabel.setItem(row_idx, 3, alm_item)
                tabel.setItem(row_idx, 4, cat_item)
                tabel.setItem(row_idx, 5, st_item)

    def _buka_dialog_tambah(self, jenis: str) -> None:
        dlg = DialogFormPihak(self.conn, jenis, parent=self)
        if dlg.exec():
            self.muat_data()

    def _buka_dialog_edit(self, jenis: str) -> None:
        tabel: QTableWidget = getattr(self, f"tabel_{jenis}")
        data_list = getattr(self, f"data_{jenis}")
        baris = tabel.currentRow()
        if baris < 0 or baris >= len(data_list):
            QMessageBox.information(self, "Pilih Data", f"Silakan pilih baris {jenis} yang ingin diubah.")
            return

        p_terpilih = data_list[baris]
        dlg = DialogFormPihak(self.conn, jenis, data_edit=p_terpilih, parent=self)
        if dlg.exec():
            self.muat_data()
