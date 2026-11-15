"""
app/ui/layar_kas.py — Layar Buku Kas & Pencatatan Kas Operasional Manual.
- Mencatat kas masuk / keluar operasional (listrik, ATK, konsumsi, dana talangan, dll.)
- Melihat mutasi buku kas lengkap (baik dari simpanan/pinjaman/angsuran otomatis maupun manual)
- Menampilkan posisi saldo kas berjalan real-time
- Koreksi pembalik untuk kas manual
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

from app.db.repo_kas import tambah_kas_manual, ambil_daftar_buku_kas, balik_kas_manual
from app.db.repo_ringkasan import hitung_saldo_kas_saat_ini
from app.util.format import format_rupiah, format_tanggal_indo
from app.ui.komponen.input_rupiah import InputRupiah


class DialogInputKasManual(QDialog):
    """Dialog Input Kas Operasional Manual."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle("Catat Kas Masuk / Keluar Operasional")
        self.resize(480, 360)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)

        self.combo_jenis = QComboBox(self)
        self.combo_jenis.setMinimumHeight(40)
        self.combo_jenis.addItem("Kas Keluar (Pengeluaran Operasional / ATK / Listrik)", "keluar")
        self.combo_jenis.addItem("Kas Masuk (Pemasukan Non-Transaksi / Modal)", "masuk")
        form.addRow("Jenis Kas *:", self.combo_jenis)

        self.input_nominal = InputRupiah(self, placeholder="Contoh: 50.000")
        self.input_nominal.setMinimumHeight(40)
        form.addRow("Nominal (Rp) *:", self.input_nominal)

        self.input_tgl = QDateEdit(self)
        self.input_tgl.setMinimumHeight(40)
        self.input_tgl.setCalendarPopup(True)
        self.input_tgl.setDate(QDate.currentDate())
        self.input_tgl.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Tanggal *:", self.input_tgl)

        self.input_ket = QTextEdit(self)
        self.input_ket.setMaximumHeight(80)
        self.input_ket.setPlaceholderText("Keterangan keperluan kas...")
        form.addRow("Keterangan *:", self.input_ket)

        layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_batal = QPushButton("Batal", self)
        btn_batal.setMinimumHeight(40)
        btn_batal.clicked.connect(self.reject)

        btn_simpan = QPushButton("Simpan Kas", self)
        btn_simpan.setMinimumHeight(40)
        btn_simpan.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold;")
        btn_simpan.clicked.connect(self._simpan)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_batal)
        btn_layout.addWidget(btn_simpan)
        layout.addLayout(btn_layout)

    def _simpan(self) -> None:
        nominal = self.input_nominal.ambil_nilai()
        if nominal <= 0:
            QMessageBox.warning(self, "Nominal Tidak Valid", "Masukkan nominal rupiah lebih dari Rp 0.")
            self.input_nominal.setFocus()
            return

        ket = self.input_ket.toPlainText().strip()
        if not ket:
            QMessageBox.warning(self, "Keterangan Wajib", "Keterangan kas operasional wajib diisi.")
            return

        jenis = self.combo_jenis.currentData()
        tgl_iso = self.input_tgl.date().toString("yyyy-MM-dd")

        try:
            tambah_kas_manual(self.conn, tanggal=tgl_iso, keterangan=ket, jenis_arus=jenis, nominal=nominal)
            QMessageBox.information(self, "Berhasil", f"Kas {jenis} sebesar {format_rupiah(nominal)} berhasil dicatat.")
            self.accept()
        except ValueError as err:
            QMessageBox.warning(self, "Gagal", str(err))


class LayarKas(QWidget):
    """Layar Utama Buku Kas Operasional."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header_layout = QHBoxLayout()
        label_judul = QLabel("Buku Kas Operasional Koperasi", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(label_judul)

        header_layout.addStretch()

        self.lbl_saldo_kas = QLabel("Posisi Kas: Rp 0", self)
        self.lbl_saldo_kas.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.lbl_saldo_kas.setStyleSheet("background-color: #EFF6FF; color: #1E3A8A; padding: 6px 12px; border-radius: 6px;")
        header_layout.addWidget(self.lbl_saldo_kas)

        self.btn_tambah_kas = QPushButton("+ Catat Kas Operasional", self)
        self.btn_tambah_kas.setProperty("tipe", "utama")
        self.btn_tambah_kas.clicked.connect(self._buka_dialog_tambah)
        header_layout.addWidget(self.btn_tambah_kas)

        layout.addLayout(header_layout)

        # Baris Filter
        filter_bar = QHBoxLayout()
        self.input_cari = QLineEdit(self)
        self.input_cari.setPlaceholderText("Cari keterangan buku kas...")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.textChanged.connect(self.muat_data)

        self.combo_sumber = QComboBox(self)
        self.combo_sumber.setMinimumHeight(40)
        self.combo_sumber.addItem("Semua Sumber Kas", "")
        self.combo_sumber.addItem("Kas Manual (Operasional)", "manual")
        self.combo_sumber.addItem("Simpanan", "simpanan")
        self.combo_sumber.addItem("Pencairan Pinjaman", "pencairan")
        self.combo_sumber.addItem("Angsuran", "angsuran")
        self.combo_sumber.addItem("Biaya Admin", "biaya_admin")
        self.combo_sumber.currentIndexChanged.connect(self.muat_data)

        filter_bar.addWidget(self.input_cari, 4)
        filter_bar.addWidget(self.combo_sumber, 2)
        layout.addLayout(filter_bar)

        # Tabel Buku Kas
        self.tabel = QTableWidget(self)
        self.tabel.setFont(QFont("Segoe UI", 11))
        self.tabel.setColumnCount(6)
        self.tabel.setHorizontalHeaderLabels([
            "ID", "Tanggal", "Keterangan", "Kas Masuk", "Kas Keluar", "Sumber"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 50)   # ID
        self.tabel.setColumnWidth(1, 115)  # Tanggal
        self.tabel.setColumnWidth(3, 140)  # Kas Masuk
        self.tabel.setColumnWidth(4, 140)  # Kas Keluar
        self.tabel.setColumnWidth(5, 120)  # Sumber
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(self.tabel)

        # Tombol Aksi Bawah
        aksi_bottom = QHBoxLayout()
        self.btn_balik = QPushButton("Batalkan Catatan Kas Terpilih", self)
        self.btn_balik.setProperty("tipe", "bahaya")
        self.btn_balik.clicked.connect(self._balik_kas_terpilih)
        aksi_bottom.addWidget(self.btn_balik)
        aksi_bottom.addStretch()
        layout.addLayout(aksi_bottom)

        self.daftar_kas = []
        self.muat_data()

    def muat_data(self) -> None:
        cari = self.input_cari.text().strip()
        sumber = self.combo_sumber.currentData() or None

        self.daftar_kas = ambil_daftar_buku_kas(self.conn, sumber_filter=sumber, kata_kunci=cari, limit=300)
        self.tabel.setRowCount(len(self.daftar_kas))

        for b, r in enumerate(self.daftar_kas):
            self.tabel.setItem(b, 0, QTableWidgetItem(str(r["id"])))
            self.tabel.setItem(b, 1, QTableWidgetItem(format_tanggal_indo(r["tanggal"])))
            self.tabel.setItem(b, 2, QTableWidgetItem(r["keterangan"]))

            m_item = QTableWidgetItem(format_rupiah(r["masuk"]) if r["masuk"] > 0 else "-")
            m_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if r["masuk"] > 0:
                m_item.setForeground(Qt.GlobalColor.darkGreen)
            self.tabel.setItem(b, 3, m_item)

            k_item = QTableWidgetItem(format_rupiah(r["keluar"]) if r["keluar"] > 0 else "-")
            k_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if r["keluar"] > 0:
                k_item.setForeground(Qt.GlobalColor.darkRed)
            self.tabel.setItem(b, 4, k_item)

            self.tabel.setItem(b, 5, QTableWidgetItem(r["sumber"].capitalize()))

        saldo = hitung_saldo_kas_saat_ini(self.conn)
        self.lbl_saldo_kas.setText(f"Posisi Kas Operasional: {format_rupiah(saldo)}")

    def _buka_dialog_tambah(self) -> None:
        dlg = DialogInputKasManual(self.conn, parent=self)
        if dlg.exec():
            self.muat_data()

    def _balik_kas_terpilih(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0:
            QMessageBox.information(self, "Pilih Baris", "Silakan klik baris kas manual yang ingin dibalik.")
            return

        tx = self.daftar_kas[baris]
        if tx["sumber"] != "manual":
            QMessageBox.warning(
                self, "Tidak Diizinkan",
                "Hanya kas operasional 'Manual' yang dapat dibalik di sini.\n"
                "Untuk simpanan atau angsuran, lakukan pembalik melalui menunya masing-masing."
            )
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Batalkan Catatan Kas #{tx['id']}")
        dlg.resize(440, 240)

        d_layout = QVBoxLayout(dlg)
        form = QFormLayout()
        input_alasan = QLineEdit(dlg)
        input_alasan.setMinimumHeight(38)
        input_alasan.setPlaceholderText("Alasan pembatalan catatan kas...")
        form.addRow("Alasan *:", input_alasan)

        input_tgl = QDateEdit(dlg)
        input_tgl.setMinimumHeight(38)
        input_tgl.setCalendarPopup(True)
        input_tgl.setDate(QDate.currentDate())
        input_tgl.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Tanggal Pembatalan *:", input_tgl)
        d_layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_b = QPushButton("Tutup / Kembali", dlg)
        btn_b.setMinimumHeight(38)
        btn_b.clicked.connect(dlg.reject)
        btn_p = QPushButton("Proses Pembatalan", dlg)
        btn_p.setProperty("tipe", "bahaya")
        btn_p.setMinimumHeight(38)
        
        def do_p():
            alasan = input_alasan.text().strip()
            if not alasan:
                QMessageBox.warning(dlg, "Wajib", "Alasan wajib diisi.")
                return
            tgl = input_tgl.date().toString("yyyy-MM-dd")
            try:
                balik_kas_manual(self.conn, tx["id"], alasan, tgl)
                QMessageBox.information(dlg, "Berhasil", "Catatan kas berhasil dibatalkan dan saldo kas telah disesuaikan.")
                dlg.accept()
                self.muat_data()
            except Exception as err:
                QMessageBox.critical(dlg, "Gagal", str(err))

        btn_p.clicked.connect(do_p)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_b)
        btn_layout.addWidget(btn_p)
        d_layout.addLayout(btn_layout)
        dlg.exec()

