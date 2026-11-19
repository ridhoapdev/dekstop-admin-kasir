"""
app/ui/layar_simpanan.py — Tampilan antarmuka Modul Simpanan.
- Input Setoran / Penarikan (Pokok, Wajib, Sukarela)
- Dialog pencarian anggota
- Informasi saldo saat ini sebelum transaksi
- Transaksi pembalik (koreksi) dengan konfirmasi jelas
- Riwayat transaksi simpanan dengan filter jenis dan pencarian
"""
import sqlite3
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QDialog, QFormLayout, QTextEdit,
    QDateEdit
)
from PySide6.QtGui import QFont, QCursor
from PySide6.QtCore import Qt, QDate

from app.db.repo_anggota import ambil_daftar_anggota, ambil_anggota_by_id
from app.db.repo_simpanan import (
    tambah_transaksi_simpanan, hitung_saldo_simpanan_anggota,
    balik_transaksi_simpanan, ambil_riwayat_simpanan
)
from app.util.format import format_rupiah, format_tanggal_indo
from app.layanan.cetak_kuitansi import buat_kuitansi_simpanan_pdf
from app.ui.komponen.input_rupiah import InputRupiah
from app.ui.komponen.tabel_helper import (
    terapkan_style_tabel_global, NumericTableWidgetItem
)


class DialogInputSimpanan(QDialog):
    """Dialog Input Setoran atau Penarikan Simpanan."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.anggota_id_terpilih = None
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle("Input Transaksi Simpanan")
        self.setMinimumWidth(500)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        # 1. Pemilihan Anggota
        anggota_layout = QHBoxLayout()
        self.combo_anggota = QComboBox(self)
        self.combo_anggota.setMinimumHeight(40)
        self._muat_pilihan_anggota()
        self.combo_anggota.currentIndexChanged.connect(self._perbarui_info_saldo)
        anggota_layout.addWidget(self.combo_anggota)

        form_layout.addRow("Pilih Anggota *:", anggota_layout)

        # Info Saldo Anggota Terpilih
        self.label_info_saldo = QLabel("Saldo: Pokok: Rp 0 | Wajib: Rp 0 | Sukarela: Rp 0", self)
        self.label_info_saldo.setStyleSheet("color: #1E40AF; font-weight: bold; padding: 4px 0;")
        form_layout.addRow("", self.label_info_saldo)

        # 2. Jenis Simpanan
        self.combo_jenis = QComboBox(self)
        self.combo_jenis.setMinimumHeight(40)
        self.combo_jenis.addItem("Simpanan Wajib", "wajib")
        self.combo_jenis.addItem("Simpanan Sukarela", "sukarela")
        self.combo_jenis.addItem("Simpanan Pokok", "pokok")
        self.combo_jenis.currentIndexChanged.connect(self._perbarui_info_saldo)
        form_layout.addRow("Jenis Simpanan *:", self.combo_jenis)

        # 3. Arah (Setor / Tarik)
        self.combo_arah = QComboBox(self)
        self.combo_arah.setMinimumHeight(40)
        self.combo_arah.addItem("Setor (+)", "setor")
        self.combo_arah.addItem("Tarik (-)", "tarik")
        form_layout.addRow("Jenis Transaksi *:", self.combo_arah)

        # 4. Jumlah (Nominal Rupiah)
        self.input_jumlah = InputRupiah(self, placeholder="Contoh: 50.000 atau 100.000")
        self.input_jumlah.setMinimumHeight(40)
        form_layout.addRow("Nominal (Rp) *:", self.input_jumlah)

        # 5. Tanggal Transaksi
        self.input_tanggal = QDateEdit(self)
        self.input_tanggal.setMinimumHeight(40)
        self.input_tanggal.setCalendarPopup(True)
        self.input_tanggal.setDate(QDate.currentDate())
        self.input_tanggal.setDisplayFormat("dd/MM/yyyy")
        form_layout.addRow("Tanggal Transaksi *:", self.input_tanggal)

        # 6. Keterangan
        self.input_keterangan = QTextEdit(self)
        self.input_keterangan.setMaximumHeight(70)
        self.input_keterangan.setPlaceholderText("Catatan atau keterangan opsional...")
        form_layout.addRow("Keterangan:", self.input_keterangan)

        layout.addLayout(form_layout)

        # Tombol Aksi
        btn_layout = QHBoxLayout()
        self.btn_simpan = QPushButton("Simpan Transaksi", self)
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

        self._perbarui_info_saldo()

    def _muat_pilihan_anggota(self) -> None:
        self.combo_anggota.clear()
        daftar = ambil_daftar_anggota(self.conn, status_filter="aktif", limit=500)
        for ang in daftar:
            teks = f"{ang['no_anggota']} - {ang['nama']}"
            if ang["unit"]:
                teks += f" ({ang['unit']})"
            self.combo_anggota.addItem(teks, ang["id"])

    def _perbarui_info_saldo(self) -> None:
        anggota_id = self.combo_anggota.currentData()
        if not anggota_id:
            self.label_info_saldo.setText("Pilih anggota untuk melihat saldo.")
            return

        saldo = hitung_saldo_simpanan_anggota(self.conn, anggota_id)
        self.label_info_saldo.setText(
            f"Saldo: Pokok: {format_rupiah(saldo['pokok'])} | "
            f"Wajib: {format_rupiah(saldo['wajib'])} | "
            f"Sukarela: {format_rupiah(saldo['sukarela'])} | "
            f"Total: {format_rupiah(saldo['total'])}"
        )

    def _simpan(self) -> None:
        anggota_id = self.combo_anggota.currentData()
        if not anggota_id:
            QMessageBox.warning(self, "Pilih Anggota", "Silakan pilih anggota terlebih dahulu.")
            return

        nominal = self.input_jumlah.ambil_nilai()
        if nominal <= 0:
            QMessageBox.warning(self, "Nominal Tidak Valid", "Masukkan nominal rupiah lebih dari Rp 0.")
            self.input_jumlah.setFocus()
            return

        jenis = self.combo_jenis.currentData()
        arah = self.combo_arah.currentData()
        tanggal = self.input_tanggal.date().toString("yyyy-MM-dd")
        keterangan = self.input_keterangan.toPlainText().strip()

        try:
            tambah_transaksi_simpanan(
                self.conn,
                anggota_id=anggota_id,
                jenis=jenis,
                arah=arah,
                jumlah=nominal,
                tanggal=tanggal,
                keterangan=keterangan or None
            )
            QMessageBox.information(
                self, "Berhasil", f"Transaksi simpanan {arah} {jenis.capitalize()} sebesar {format_rupiah(nominal)} berhasil dicatat."
            )
            self.accept()
        except ValueError as err:
            QMessageBox.warning(self, "Pemberitahuan", str(err))
        except Exception as err:
            QMessageBox.critical(self, "Kendala Sistem", f"Gagal menyimpan transaksi: {err}")


class DialogPembalikSimpanan(QDialog):
    """Dialog Konfirmasi Transaksi Pembalik (Koreksi Simpanan)."""

    def __init__(self, conn: sqlite3.Connection, tx_data: sqlite3.Row, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.tx_data = tx_data
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle("Batalkan Transaksi Simpanan (Salah Catat)")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        info_teks = (
            f"<b>Perhatian:</b> Sesuai aturan pembukuan koperasi, transaksi yang sudah dicatat tidak dihapus permanen, "
            f"melainkan dibuatkan transaksi pembatalan otomatis untuk menormalkan kembali saldo.<br><br>"
            f"<b>Rincian Transaksi yang Dibatalkan:</b><br>"
            f"• No. Transaksi: #{self.tx_data['id']}<br>"
            f"• Anggota: {self.tx_data['nama_anggota']} ({self.tx_data['no_anggota']})<br>"
            f"• Jenis: Simpanan {self.tx_data['jenis'].capitalize()} ({self.tx_data['arah'].upper()})<br>"
            f"• Nominal: {format_rupiah(self.tx_data['jumlah'])}<br>"
            f"• Tanggal: {format_tanggal_indo(self.tx_data['tanggal'])}"
        )
        label_info = QLabel(info_teks, self)
        label_info.setWordWrap(True)
        label_info.setStyleSheet("background-color: #FEF3C7; padding: 12px; border-radius: 6px; color: #92400E;")
        layout.addWidget(label_info)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.input_alasan = QLineEdit(self)
        self.input_alasan.setMinimumHeight(40)
        self.input_alasan.setPlaceholderText("Contoh: Salah input nominal / salah nama anggota...")
        form_layout.addRow("Alasan Pembatalan *:", self.input_alasan)

        self.input_tgl_balik = QDateEdit(self)
        self.input_tgl_balik.setMinimumHeight(40)
        self.input_tgl_balik.setCalendarPopup(True)
        self.input_tgl_balik.setDate(QDate.currentDate())
        self.input_tgl_balik.setDisplayFormat("dd/MM/yyyy")
        form_layout.addRow("Tanggal Pembatalan *:", self.input_tgl_balik)

        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        self.btn_batal = QPushButton("Tutup / Kembali", self)
        self.btn_batal.setMinimumHeight(42)
        self.btn_batal.clicked.connect(self.reject)

        self.btn_proses = QPushButton("Proses Pembatalan", self)
        self.btn_proses.setProperty("tipe", "bahaya")
        self.btn_proses.setMinimumHeight(42)
        self.btn_proses.clicked.connect(self._proses)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_batal)
        btn_layout.addWidget(self.btn_proses)
        layout.addLayout(btn_layout)

    def _proses(self) -> None:
        alasan = self.input_alasan.text().strip()
        if not alasan:
            QMessageBox.warning(self, "Alasan Wajib", "Silakan masukkan alasan pembatalan / koreksi.")
            self.input_alasan.setFocus()
            return

        tgl_iso = self.input_tgl_balik.date().toString("yyyy-MM-dd")
        try:
            balik_transaksi_simpanan(
                self.conn,
                transaksi_id=self.tx_data["id"],
                alasan=alasan,
                tanggal_balik=tgl_iso
            )
            QMessageBox.information(
                self, "Berhasil", "Transaksi berhasil dibatalkan dan saldo telah disesuaikan."
            )
            self.accept()
        except ValueError as err:
            QMessageBox.warning(self, "Pemberitahuan", str(err))
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal membalik transaksi: {err}")


class LayarSimpanan(QWidget):
    """Layar utama modul Simpanan: tabel riwayat transaksi, input setor/tarik, dan koreksi pembalik."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        label_judul = QLabel("Transaksi Simpanan Koperasi", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(label_judul)

        header_layout.addStretch()

        self.btn_input = QPushButton("+ Input Simpanan (Setor / Tarik)", self)
        self.btn_input.setProperty("tipe", "utama")
        self.btn_input.clicked.connect(self._buka_dialog_input)
        header_layout.addWidget(self.btn_input)

        layout.addLayout(header_layout)

        # Filter & Pencarian
        filter_layout = QHBoxLayout()
        self.input_cari = QLineEdit(self)
        self.input_cari.setPlaceholderText("Cari nama anggota, no. anggota, atau keterangan...")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.textChanged.connect(self.muat_data)

        self.combo_filter_jenis = QComboBox(self)
        self.combo_filter_jenis.setMinimumHeight(40)
        self.combo_filter_jenis.addItem("Semua Jenis Simpanan", "")
        self.combo_filter_jenis.addItem("Pokok", "pokok")
        self.combo_filter_jenis.addItem("Wajib", "wajib")
        self.combo_filter_jenis.addItem("Sukarela", "sukarela")
        self.combo_filter_jenis.currentIndexChanged.connect(self.muat_data)

        self.btn_segar = QPushButton("Segarkan", self)
        self.btn_segar.setMinimumHeight(40)
        self.btn_segar.clicked.connect(self.muat_data)

        filter_layout.addWidget(self.input_cari, 4)
        filter_layout.addWidget(self.combo_filter_jenis, 2)
        filter_layout.addWidget(self.btn_segar, 1)
        layout.addLayout(filter_layout)

        # Tabel Riwayat Simpanan
        self.tabel = QTableWidget(self)
        self.tabel.setFont(QFont("Segoe UI", 11))
        self.tabel.setColumnCount(8)
        self.tabel.setHorizontalHeaderLabels([
            "ID", "Tanggal", "No. Anggota", "Nama Anggota", "Jenis", "Arah", "Nominal", "Keterangan"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabel.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 50)   # ID (sembunyi)
        self.tabel.setColumnWidth(1, 120)  # Tanggal
        self.tabel.setColumnWidth(2, 110)  # No. Anggota
        self.tabel.setColumnWidth(4, 100)  # Jenis
        self.tabel.setColumnWidth(5, 90)   # Arah
        self.tabel.setColumnWidth(6, 140)  # Nominal (rata kanan)
        
        self.empty_state = terapkan_style_tabel_global(
            self.tabel,
            rata_kanan_kolom=[6],
            kolom_status=5,
            kolom_sembunyi=[0]
        )
        self.tabel.itemSelectionChanged.connect(self._perbarui_status_tombol)

        layout.addWidget(self.tabel)

        # Baris Info Jumlah Data
        lbl_info_row = QHBoxLayout()
        self.lbl_jumlah_data = QLabel("Menampilkan 0 transaksi", self)
        self.lbl_jumlah_data.setFont(QFont("Segoe UI", 9.5))
        self.lbl_jumlah_data.setStyleSheet("color: #64748B; font-weight: 500;")
        lbl_info_row.addWidget(self.lbl_jumlah_data)
        lbl_info_row.addStretch()
        layout.addLayout(lbl_info_row)

        # Tombol Aksi Bawah
        aksi_layout = QHBoxLayout()
        self.btn_cetak_kuitansi = QPushButton("Cetak Kuitansi Tanda Terima (PDF)", self)
        self.btn_cetak_kuitansi.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_cetak_kuitansi.setMinimumHeight(42)
        self.btn_cetak_kuitansi.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self.btn_cetak_kuitansi.setProperty("tipe", "sukses")
        self.btn_cetak_kuitansi.clicked.connect(self._cetak_kuitansi)

        self.btn_balik = QPushButton("Batalkan Transaksi / Salah Catat", self)
        self.btn_balik.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_balik.setMinimumHeight(42)
        self.btn_balik.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self.btn_balik.setProperty("tipe", "bahaya")
        self.btn_balik.clicked.connect(self._buka_dialog_pembalik)

        aksi_layout.addWidget(self.btn_cetak_kuitansi)
        aksi_layout.addWidget(self.btn_balik)
        aksi_layout.addStretch()
        layout.addLayout(aksi_layout)

        self.daftar_tx = []
        self.muat_data()
        self._perbarui_status_tombol()

    def muat_data(self) -> None:
        kata_kunci = self.input_cari.text().strip()
        jenis = self.combo_filter_jenis.currentData() or None

        self.daftar_tx = ambil_riwayat_simpanan(
            self.conn, jenis=jenis, kata_kunci=kata_kunci, limit=200
        )
        self.tabel.setSortingEnabled(False)
        self.tabel.setRowCount(len(self.daftar_tx))

        for baris, tx in enumerate(self.daftar_tx):
            id_item = QTableWidgetItem(str(tx["id"]))
            id_item.setData(Qt.ItemDataRole.UserRole, tx["id"])
            tgl_item = QTableWidgetItem(format_tanggal_indo(tx["tanggal"]))
            no_ang_item = QTableWidgetItem(tx["no_anggota"])
            nama_item = QTableWidgetItem(tx["nama_anggota"])
            jenis_item = QTableWidgetItem(tx["jenis"].capitalize())
            
            arah_teks = "Setor" if tx["arah"] == "setor" else "Tarik"
            arah_item = QTableWidgetItem(arah_teks)

            nom_item = NumericTableWidgetItem(format_rupiah(tx["jumlah"]), tx["jumlah"])

            ket = tx["keterangan"] or "-"
            if tx["membalik_id"]:
                ket = f"[PEMBALIK #{tx['membalik_id']}] {ket}"
            ket_item = QTableWidgetItem(ket)

            self.tabel.setItem(baris, 0, id_item)
            self.tabel.setItem(baris, 1, tgl_item)
            self.tabel.setItem(baris, 2, no_ang_item)
            self.tabel.setItem(baris, 3, nama_item)
            self.tabel.setItem(baris, 4, jenis_item)
            self.tabel.setItem(baris, 5, arah_item)
            self.tabel.setItem(baris, 6, nom_item)
            self.tabel.setItem(baris, 7, ket_item)

        self.tabel.setSortingEnabled(True)

        # Update penghitung data & empty state
        jml = len(self.daftar_tx)
        self.lbl_jumlah_data.setText(f"Menampilkan {jml} transaksi simpanan")
        if jml == 0:
            if kata_kunci:
                self.empty_state.tampilkan(
                    f"Tidak ada transaksi yang cocok dengan '{kata_kunci}'",
                    label_tombol="Hapus pencarian",
                    callback_aksi=self.input_cari.clear
                )
            else:
                self.empty_state.tampilkan("Belum ada riwayat transaksi simpanan.")
        else:
            self.empty_state.hide()

        self._perbarui_status_tombol()

    def _perbarui_status_tombol(self) -> None:
        baris = self.tabel.currentRow()
        terpilih = (baris >= 0 and baris < len(self.daftar_tx))
        self.btn_cetak_kuitansi.setEnabled(terpilih)
        self.btn_balik.setEnabled(terpilih)

    def _buka_dialog_input(self) -> None:
        dlg = DialogInputSimpanan(self.conn, parent=self)
        if dlg.exec():
            self.muat_data()

    def _cetak_kuitansi(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_tx):
            QMessageBox.information(self, "Pilih Transaksi", "Silakan klik baris transaksi yang ingin dicetak kuitansinya.")
            return

        tx = self.daftar_tx[baris]
        cur = self.conn.cursor()
        cur.execute("SELECT nilai FROM pengaturan WHERE kunci = 'nama_koperasi';")
        r_kop = cur.fetchone()
        nama_kop = r_kop[0] if r_kop else "Koperasi Simpan Pinjam"

        # Dialog simpan PDF
        nama_file_def = f"Kuitansi_Simpanan_{tx['id']}_{tx['no_anggota']}.pdf"
        from PySide6.QtWidgets import QFileDialog
        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Simpan Kuitansi PDF", nama_file_def, "PDF Files (*.pdf)"
        )
        if not path_simpan:
            return

        try:
            buat_kuitansi_simpanan_pdf(dict(tx), nama_kop, path_simpan)
            QMessageBox.information(self, "Berhasil", f"Kuitansi berhasil dicetak ke PDF:\n{path_simpan}")
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal mencetak kuitansi: {err}")

    def _buka_dialog_pembalik(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_tx):
            QMessageBox.information(self, "Pilih Transaksi", "Silakan klik baris transaksi yang ingin dikoreksi.")
            return

        tx_terpilih = self.daftar_tx[baris]
        dlg = DialogPembalikSimpanan(self.conn, tx_data=tx_terpilih, parent=self)
        if dlg.exec():
            self.muat_data()

