"""
app/ui/layar_anggota.py — Tampilan antarmuka Manajemen Data Anggota.
Sesuai prinsip RULES.md:
- Font >= 12 pt, tombol tinggi >= 40 px, kontras jelas
- Keyboard-first: Enter menyimpan, Esc membatalkan
- Pesan berbahasa Indonesia sederhana dan ramah
- Tidak ada hapus permanen jika anggota memiliki riwayat transaksi
"""
import sqlite3
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QDialog, QFormLayout, QTextEdit,
    QDateEdit
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QDate

from app.db.repo_anggota import (
    ambil_daftar_anggota, tambah_anggota, ubah_anggota,
    set_status_anggota, hapus_anggota_jika_tanpa_transaksi,
    buat_nomor_anggota_berikutnya, ambil_anggota_by_id
)
from app.util.format import format_tanggal_indo


class DialogFormAnggota(QDialog):
    """Dialog Tambah/Ubah Data Anggota."""

    def __init__(self, conn: sqlite3.Connection, anggota_id: int = None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.anggota_id = anggota_id
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        judul = "Ubah Data Anggota" if self.anggota_id else "Tambah Anggota Baru"
        self.setWindowTitle(judul)
        self.setMinimumWidth(450)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        # Field input
        self.input_no = QLineEdit(self)
        self.input_no.setMinimumHeight(40)
        self.input_nama = QLineEdit(self)
        self.input_nama.setMinimumHeight(40)
        self.input_nik = QLineEdit(self)
        self.input_nik.setMinimumHeight(40)
        self.input_unit = QLineEdit(self)
        self.input_unit.setMinimumHeight(40)
        self.input_hp = QLineEdit(self)
        self.input_hp.setMinimumHeight(40)
        self.input_alamat = QLineEdit(self)
        self.input_alamat.setMinimumHeight(40)
        
        self.input_tgl_masuk = QDateEdit(self)
        self.input_tgl_masuk.setMinimumHeight(40)
        self.input_tgl_masuk.setCalendarPopup(True)
        self.input_tgl_masuk.setDate(QDate.currentDate())
        self.input_tgl_masuk.setDisplayFormat("dd/MM/yyyy")

        self.input_catatan = QTextEdit(self)
        self.input_catatan.setMaximumHeight(80)

        form_layout.addRow("No. Anggota *:", self.input_no)
        form_layout.addRow("Nama Lengkap *:", self.input_nama)
        form_layout.addRow("NIK Karyawan:", self.input_nik)
        form_layout.addRow("Unit / Bagian:", self.input_unit)
        form_layout.addRow("No. HP / WA:", self.input_hp)
        form_layout.addRow("Alamat:", self.input_alamat)
        form_layout.addRow("Tanggal Masuk:", self.input_tgl_masuk)
        form_layout.addRow("Catatan Tambahan:", self.input_catatan)

        layout.addLayout(form_layout)

        # Tombol Aksi
        btn_layout = QHBoxLayout()
        self.btn_simpan = QPushButton("Simpan", self)
        self.btn_simpan.setMinimumHeight(42)
        self.btn_simpan.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_simpan.clicked.connect(self._simpan)

        self.btn_batal = QPushButton("Batal", self)
        self.btn_batal.setMinimumHeight(42)
        self.btn_batal.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_batal)
        btn_layout.addWidget(self.btn_simpan)
        layout.addLayout(btn_layout)

        # Muat data awal jika mode ubah
        if self.anggota_id:
            self._muat_data_edit()
        else:
            self.input_no.setText(buat_nomor_anggota_berikutnya(self.conn))

        self.input_nama.setFocus()

    def _muat_data_edit(self) -> None:
        data = ambil_anggota_by_id(self.conn, self.anggota_id)
        if not data:
            return
        self.input_no.setText(data["no_anggota"])
        self.input_no.setReadOnly(True)  # No anggota tidak diubah saat edit
        self.input_nama.setText(data["nama"] or "")
        self.input_nik.setText(data["nik_karyawan"] or "")
        self.input_unit.setText(data["unit"] or "")
        self.input_hp.setText(data["no_hp"] or "")
        self.input_alamat.setText(data["alamat"] or "")
        self.input_catatan.setPlainText(data["catatan"] or "")
        self.input_tgl_masuk.setEnabled(False)  # Tanggal masuk dipertahankan

    def _simpan(self) -> None:
        nama = self.input_nama.text().strip()
        no_ang = self.input_no.text().strip()

        if not no_ang:
            QMessageBox.warning(self, "Perhatian", "Nomor anggota tidak boleh kosong.")
            self.input_no.setFocus()
            return
        if not nama:
            QMessageBox.warning(self, "Perhatian", "Nama lengkap anggota tidak boleh kosong.")
            self.input_nama.setFocus()
            return

        try:
            if self.anggota_id:
                ubah_anggota(
                    self.conn,
                    anggota_id=self.anggota_id,
                    nama=nama,
                    nik_karyawan=self.input_nik.text().strip() or None,
                    unit=self.input_unit.text().strip() or None,
                    no_hp=self.input_hp.text().strip() or None,
                    alamat=self.input_alamat.text().strip() or None,
                    catatan=self.input_catatan.toPlainText().strip() or None
                )
            else:
                tgl_iso = self.input_tgl_masuk.date().toString("yyyy-MM-dd")
                tambah_anggota(
                    self.conn,
                    no_anggota=no_ang,
                    nama=nama,
                    nik_karyawan=self.input_nik.text().strip() or None,
                    unit=self.input_unit.text().strip() or None,
                    no_hp=self.input_hp.text().strip() or None,
                    alamat=self.input_alamat.text().strip() or None,
                    tanggal_masuk=tgl_iso,
                    catatan=self.input_catatan.toPlainText().strip() or None
                )
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Perhatian", f"Nomor anggota '{no_ang}' sudah terdaftar.")
        except Exception as err:
            QMessageBox.warning(self, "Gagal Menyimpan", f"Terjadi kendala saat menyimpan: {err}")


class LayarAnggota(QWidget):
    """Layar manajemen anggota (pencarian, daftar tabel, tambah, ubah, nonaktifkan)."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header: Judul & Tombol Tambah
        header_layout = QHBoxLayout()
        label_judul = QLabel("Data Anggota Koperasi", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(label_judul)

        header_layout.addStretch()

        self.btn_tambah = QPushButton("+ Tambah Anggota", self)
        self.btn_tambah.setProperty("tipe", "sukses")
        self.btn_tambah.clicked.connect(self._buka_dialog_tambah)
        header_layout.addWidget(self.btn_tambah)

        layout.addLayout(header_layout)

        # Baris Pencarian & Filter Cepat
        filter_layout = QHBoxLayout()
        self.input_cari = QLineEdit(self)
        self.input_cari.setPlaceholderText("Ketik nama, no. anggota, NIK, atau unit...")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.textChanged.connect(self.muat_data)

        self.combo_status = QComboBox(self)
        self.combo_status.setMinimumHeight(40)
        self.combo_status.addItem("Semua Status", "semua")
        self.combo_status.addItem("Hanya Aktif", "aktif")
        self.combo_status.addItem("Hanya Keluar", "keluar")
        self.combo_status.currentIndexChanged.connect(self.muat_data)

        self.btn_segar = QPushButton("Segarkan", self)
        self.btn_segar.setMinimumHeight(40)
        self.btn_segar.clicked.connect(self.muat_data)

        filter_layout.addWidget(self.input_cari, 4)
        filter_layout.addWidget(self.combo_status, 1)
        filter_layout.addWidget(self.btn_segar, 1)
        layout.addLayout(filter_layout)

        # Tabel Data Anggota
        self.tabel = QTableWidget(self)
        self.tabel.setFont(QFont("Segoe UI", 11))
        self.tabel.setColumnCount(7)
        self.tabel.setHorizontalHeaderLabels([
            "ID", "No. Anggota", "Nama Lengkap", "NIK", "Unit / Bagian", "Tgl Masuk", "Status"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabel.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 50)   # ID
        self.tabel.setColumnWidth(1, 110)  # No. Anggota
        self.tabel.setColumnWidth(3, 110)  # NIK
        self.tabel.setColumnWidth(5, 115)  # Tgl Masuk
        self.tabel.setColumnWidth(6, 95)   # Status
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setDefaultSectionSize(36)
        self.tabel.doubleClicked.connect(self._buka_dialog_ubah)

        layout.addWidget(self.tabel)

        # Tombol Aksi Bawah
        aksi_layout = QHBoxLayout()
        self.btn_ubah = QPushButton("Ubah Data", self)
        self.btn_ubah.clicked.connect(self._buka_dialog_ubah)

        self.btn_status = QPushButton("Ubah Status (Aktif/Keluar)", self)
        self.btn_status.clicked.connect(self._toggle_status)

        self.btn_hapus = QPushButton("Hapus (Hanya Tanpa Transaksi)", self)
        self.btn_hapus.setProperty("tipe", "bahaya")
        self.btn_hapus.clicked.connect(self._hapus_anggota)

        aksi_layout.addWidget(self.btn_ubah)
        aksi_layout.addWidget(self.btn_status)
        aksi_layout.addWidget(self.btn_hapus)
        aksi_layout.addStretch()

        layout.addLayout(aksi_layout)

        # Muat data pertama kali
        self.muat_data()

    def muat_data(self) -> None:
        """Mengambil data dari database dan menampilkan di tabel."""
        kata_kunci = self.input_cari.text().strip()
        status = self.combo_status.currentData()

        daftar = ambil_daftar_anggota(self.conn, kata_kunci=kata_kunci, status_filter=status)
        self.tabel.setRowCount(len(daftar))

        for baris, row in enumerate(daftar):
            id_item = QTableWidgetItem(str(row["id"]))
            no_item = QTableWidgetItem(row["no_anggota"])
            nama_item = QTableWidgetItem(row["nama"])
            nik_item = QTableWidgetItem(row["nik_karyawan"] or "-")
            unit_item = QTableWidgetItem(row["unit"] or "-")
            tgl_item = QTableWidgetItem(format_tanggal_indo(row["tanggal_masuk"]))
            status_item = QTableWidgetItem("Aktif" if row["status"] == "aktif" else "Keluar")

            if row["status"] == "keluar":
                status_item.setForeground(Qt.GlobalColor.darkRed)
            else:
                status_item.setForeground(Qt.GlobalColor.darkGreen)

            self.tabel.setItem(baris, 0, id_item)
            self.tabel.setItem(baris, 1, no_item)
            self.tabel.setItem(baris, 2, nama_item)
            self.tabel.setItem(baris, 3, nik_item)
            self.tabel.setItem(baris, 4, unit_item)
            self.tabel.setItem(baris, 5, tgl_item)
            self.tabel.setItem(baris, 6, status_item)

    def _id_terpilih(self) -> int:
        baris = self.tabel.currentRow()
        if baris < 0:
            return 0
        return int(self.tabel.item(baris, 0).text())

    def _buka_dialog_tambah(self) -> None:
        dlg = DialogFormAnggota(self.conn, parent=self)
        if dlg.exec():
            self.muat_data()

    def _buka_dialog_ubah(self) -> None:
        anggota_id = self._id_terpilih()
        if not anggota_id:
            QMessageBox.information(self, "Pilih Anggota", "Silakan klik baris anggota yang ingin diubah.")
            return
        dlg = DialogFormAnggota(self.conn, anggota_id=anggota_id, parent=self)
        if dlg.exec():
            self.muat_data()

    def _toggle_status(self) -> None:
        anggota_id = self._id_terpilih()
        if not anggota_id:
            QMessageBox.information(self, "Pilih Anggota", "Silakan klik baris anggota terlebih dahulu.")
            return

        anggota = ambil_anggota_by_id(self.conn, anggota_id)
        if not anggota:
            return

        status_lama = anggota["status"]
        status_baru = "keluar" if status_lama == "aktif" else "aktif"
        tgl_hari_ini = datetime.now().strftime("%Y-%m-%d") if status_baru == "keluar" else None

        pesan = (
            f"Ubah status '{anggota['nama']}' menjadi '{status_baru.upper()}'?"
            if status_baru == "aktif"
            else f"Nonaktifkan '{anggota['nama']}' (status keluar)? Anggota yang keluar tidak bisa mengambil pinjaman baru."
        )

        jawaban = QMessageBox.question(
            self, "Konfirmasi Status", pesan,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if jawaban == QMessageBox.StandardButton.Yes:
            set_status_anggota(self.conn, anggota_id, status=status_baru, tanggal_keluar=tgl_hari_ini)
            self.muat_data()

    def _hapus_anggota(self) -> None:
        anggota_id = self._id_terpilih()
        if not anggota_id:
            QMessageBox.information(self, "Pilih Anggota", "Silakan klik baris anggota terlebih dahulu.")
            return

        anggota = ambil_anggota_by_id(self.conn, anggota_id)
        if not anggota:
            return

        jawaban = QMessageBox.question(
            self,
            "Konfirmasi Hapus",
            f"Hapus data anggota '{anggota['nama']}'?\nCatatan: Hanya bisa dihapus jika anggota belum memiliki transaksi sama sekali.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if jawaban == QMessageBox.StandardButton.Yes:
            try:
                hapus_anggota_jika_tanpa_transaksi(self.conn, anggota_id)
                QMessageBox.information(self, "Berhasil", f"Data anggota '{anggota['nama']}' berhasil dihapus.")
                self.muat_data()
            except ValueError as err:
                QMessageBox.warning(self, "Tidak Dapat Dihapus", str(err))

