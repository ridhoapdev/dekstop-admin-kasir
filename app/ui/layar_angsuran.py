"""
app/ui/layar_angsuran.py — Tampilan antarmuka Pembayaran Angsuran.
- Input pembayaran angsuran dengan pemilihan pinjaman aktif
- Angsuran berikutnya yang harus dibayar otomatis ditampilkan dan nominal terisi otomatis
- Opsi pelunasan dipercepat (sisa pokok + jasa berjalan)
- Status per angsuran: belum, lunas, sebagian, telat
- Riwayat pembayaran dan tombol koreksi pembalik
"""
import sqlite3
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QDialog, QFormLayout, QTextEdit,
    QDateEdit, QCheckBox, QGroupBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QDate

from app.db.repo_pinjaman import ambil_daftar_pinjaman, ambil_pinjaman_by_id
from app.db.repo_angsuran import (
    ambil_daftar_angsuran_dengan_status, ambil_angsuran_berikutnya_yang_harus_dibayar,
    hitung_sisa_pokok_pinjaman, bayar_angsuran, balik_pembayaran_angsuran,
    ambil_riwayat_pembayaran_angsuran
)
from app.util.format import format_rupiah, format_tanggal_indo
from app.layanan.cetak_kuitansi import buat_kuitansi_angsuran_pdf
from app.ui.komponen.input_rupiah import InputRupiah


class DialogInputAngsuran(QDialog):
    """Dialog Input Pembayaran Angsuran."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.angsuran_aktif = None
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle("Input Pembayaran Angsuran")
        self.resize(650, 600)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        # 1. Pilihan Pinjaman Aktif
        self.combo_pinjaman = QComboBox(self)
        self.combo_pinjaman.setMinimumHeight(40)
        self._muat_pilihan_pinjaman()
        self.combo_pinjaman.currentIndexChanged.connect(self._pinjaman_berubah)
        form_layout.addRow("Pilih Pinjaman Aktif *:", self.combo_pinjaman)

        # Info Ringkasan Pinjaman
        self.label_info_pinjaman = QLabel("Pilih pinjaman untuk melihat tagihan.", self)
        self.label_info_pinjaman.setStyleSheet("background-color: #F1F5F9; padding: 8px; border-radius: 4px; color: #1E293B;")
        form_layout.addRow("", self.label_info_pinjaman)

        # Opsi Pelunasan Dipercepat
        self.chk_pelunasan_dipercepat = QCheckBox("Pelunasan Dipercepat (Lunasi Seluruh Sisa Pokok)", self)
        self.chk_pelunasan_dipercepat.stateChanged.connect(self._mode_pelunasan_dipercepat_diubah)
        form_layout.addRow("", self.chk_pelunasan_dipercepat)

        # Field Angsuran Target
        self.label_angsuran_target = QLabel("-", self)
        self.label_angsuran_target.setStyleSheet("font-weight: bold; color: #2563EB;")
        form_layout.addRow("Tagihan Yang Dibayar:", self.label_angsuran_target)

        # Bayar Pokok
        self.input_pokok = InputRupiah(self, placeholder="0")
        self.input_pokok.setMinimumHeight(40)
        self.input_pokok.textChanged.connect(self._hitung_total_bayar)
        form_layout.addRow("Bayar Pokok (Rp) *:", self.input_pokok)

        # Bayar Jasa
        self.input_jasa = InputRupiah(self, placeholder="0")
        self.input_jasa.setMinimumHeight(40)
        self.input_jasa.textChanged.connect(self._hitung_total_bayar)
        form_layout.addRow("Bayar Jasa (Rp) *:", self.input_jasa)

        # Denda (opsional)
        self.input_denda = InputRupiah(self, placeholder="0")
        self.input_denda.setMinimumHeight(40)
        self.input_denda.set_nilai(0)
        self.input_denda.textChanged.connect(self._hitung_total_bayar)
        form_layout.addRow("Denda (Rp):", self.input_denda)

        # Total Bayar
        self.label_total_bayar = QLabel("Total Bayar: Rp 0", self)
        self.label_total_bayar.setStyleSheet("font-size: 14pt; font-weight: bold; color: #16A34A; margin: 4px 0;")
        form_layout.addRow("", self.label_total_bayar)

        # Tanggal Bayar
        self.input_tanggal = QDateEdit(self)
        self.input_tanggal.setMinimumHeight(40)
        self.input_tanggal.setCalendarPopup(True)
        self.input_tanggal.setDate(QDate.currentDate())
        self.input_tanggal.setDisplayFormat("dd/MM/yyyy")
        form_layout.addRow("Tanggal Bayar *:", self.input_tanggal)

        # Keterangan
        self.input_keterangan = QTextEdit(self)
        self.input_keterangan.setMaximumHeight(70)
        self.input_keterangan.setPlaceholderText("Catatan pembayaran (opsional)...")
        form_layout.addRow("Keterangan:", self.input_keterangan)

        layout.addLayout(form_layout)

        # Tombol Aksi
        btn_layout = QHBoxLayout()
        self.btn_simpan = QPushButton("Simpan Pembayaran", self)
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

        self._pinjaman_berubah()

    def _muat_pilihan_pinjaman(self) -> None:
        self.combo_pinjaman.clear()
        daftar = ambil_daftar_pinjaman(self.conn, status_filter="aktif", limit=300)
        for p in daftar:
            teks = f"{p['no_pinjaman']} - {p['nama_anggota']} (Plafon: {format_rupiah(p['plafon'])})"
            self.combo_pinjaman.addItem(teks, p["id"])

    def _pinjaman_berubah(self) -> None:
        pinj_id = self.combo_pinjaman.currentData()
        if not pinj_id:
            self.label_info_pinjaman.setText("Tidak ada pinjaman aktif yang dipilih.")
            self.angsuran_aktif = None
            return

        pinj = ambil_pinjaman_by_id(self.conn, pinj_id)
        sisa_pokok = hitung_sisa_pokok_pinjaman(self.conn, pinj_id)
        self.label_info_pinjaman.setText(
            f"<b>{pinj['nama_anggota']}</b> &nbsp;|&nbsp; Plafon: {format_rupiah(pinj['plafon'])} &nbsp;|&nbsp; "
            f"Sisa Pokok: <b>{format_rupiah(sisa_pokok)}</b>"
        )

        if self.chk_pelunasan_dipercepat.isChecked():
            self._mode_pelunasan_dipercepat_diubah()
            return

        # Ambil angsuran berikutnya yang harus dibayar
        next_angsuran = ambil_angsuran_berikutnya_yang_harus_dibayar(self.conn, pinj_id)
        self.angsuran_aktif = next_angsuran

        if next_angsuran:
            self.label_angsuran_target.setText(
                f"Angsuran Ke-{next_angsuran['angsuran_ke']} (Jatuh tempo: {format_tanggal_indo(next_angsuran['jatuh_tempo'])})"
            )
            # Isi default nominal sesuai sisa tagihan angsuran tersebut
            self.input_pokok.set_nilai(next_angsuran["sisa_pokok"])
            self.input_jasa.set_nilai(next_angsuran["sisa_jasa"])
        else:
            self.label_angsuran_target.setText("Semua jadwal cicilan telah terbayar.")
            self.input_pokok.set_nilai(0)
            self.input_jasa.set_nilai(0)

    def _mode_pelunasan_dipercepat_diubah(self) -> None:
        pinj_id = self.combo_pinjaman.currentData()
        if not pinj_id:
            return

        if self.chk_pelunasan_dipercepat.isChecked():
            sisa_pokok = hitung_sisa_pokok_pinjaman(self.conn, pinj_id)
            self.label_angsuran_target.setText("Pelunasan Dipercepat (Seluruh Sisa Pokok)")
            self.input_pokok.set_nilai(sisa_pokok)
            self.input_pokok.setEnabled(False)
            
            # Hitung perkiraan jasa 1 bulan berjalan
            pinj = ambil_pinjaman_by_id(self.conn, pinj_id)
            jasa_bln = int(round(pinj["plafon"] * pinj["jasa_persen_per_bulan"] / 100))
            self.input_jasa.set_nilai(jasa_bln)
        else:
            self.input_pokok.setEnabled(True)
            self._pinjaman_berubah()

    def _hitung_total_bayar(self) -> None:
        p = self.input_pokok.ambil_nilai()
        j = self.input_jasa.ambil_nilai()
        d = self.input_denda.ambil_nilai()
        total = p + j + d
        self.label_total_bayar.setText(f"Total Bayar: {format_rupiah(total)}")

    def _simpan(self) -> None:
        pinj_id = self.combo_pinjaman.currentData()
        if not pinj_id:
            QMessageBox.warning(self, "Pilih Pinjaman", "Silakan pilih pinjaman terlebih dahulu.")
            return

        pokok = self.input_pokok.ambil_nilai()
        jasa = self.input_jasa.ambil_nilai()
        denda = self.input_denda.ambil_nilai()

        if pokok + jasa + denda <= 0:
            QMessageBox.warning(self, "Nominal Kosong", "Total pembayaran harus lebih dari Rp 0.")
            return

        tgl_bayar = self.input_tanggal.date().toString("yyyy-MM-dd")
        ket = self.input_keterangan.toPlainText().strip()

        angsuran_id = None if self.chk_pelunasan_dipercepat.isChecked() else (
            self.angsuran_aktif["id"] if self.angsuran_aktif else None
        )

        try:
            bayar_angsuran(
                self.conn,
                pinjaman_id=pinj_id,
                angsuran_id=angsuran_id,
                tanggal=tgl_bayar,
                bayar_pokok=pokok,
                bayar_jasa=jasa,
                denda=denda,
                keterangan=ket or None
            )
            QMessageBox.information(
                self, "Pembayaran Berhasil",
                f"Pembayaran angsuran sebesar {format_rupiah(pokok + jasa + denda)} berhasil disimpan."
            )
            self.accept()
        except ValueError as err:
            QMessageBox.warning(self, "Pemberitahuan", str(err))
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal menyimpan pembayaran: {err}")


class LayarAngsuran(QWidget):
    """Layar Pembayaran Angsuran: Riwayat pembayaran, status angsuran pinjaman, dan koreksi pembalik."""

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
        label_judul = QLabel("Pembayaran Angsuran Pinjaman", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(label_judul)

        header_layout.addStretch()

        self.btn_bayar = QPushButton("+ Input Pembayaran Angsuran", self)
        self.btn_bayar.setProperty("tipe", "utama")
        self.btn_bayar.clicked.connect(self._buka_dialog_bayar)
        header_layout.addWidget(self.btn_bayar)

        layout.addLayout(header_layout)

        # Filter Pencarian
        filter_layout = QHBoxLayout()
        self.input_cari = QLineEdit(self)
        self.input_cari.setPlaceholderText("Cari no. pinjaman, nama anggota, no. anggota, keterangan...")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.textChanged.connect(self.muat_data)

        self.btn_segar = QPushButton("Segarkan", self)
        self.btn_segar.setMinimumHeight(40)
        self.btn_segar.clicked.connect(self.muat_data)

        filter_layout.addWidget(self.input_cari, 5)
        filter_layout.addWidget(self.btn_segar, 1)
        layout.addLayout(filter_layout)

        # Tabel Riwayat Pembayaran
        self.tabel = QTableWidget(self)
        self.tabel.setFont(QFont("Segoe UI", 11))
        self.tabel.setColumnCount(8)
        self.tabel.setHorizontalHeaderLabels([
            "ID", "Tanggal", "No. Pinjaman", "Nama Anggota", "Angsuran", "Bayar Pokok", "Bayar Jasa", "Keterangan"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabel.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 50)   # ID
        self.tabel.setColumnWidth(1, 115)  # Tanggal
        self.tabel.setColumnWidth(2, 115)  # No. Pinjaman
        self.tabel.setColumnWidth(4, 90)   # Angsuran
        self.tabel.setColumnWidth(5, 135)  # Bayar Pokok
        self.tabel.setColumnWidth(6, 125)  # Bayar Jasa
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setDefaultSectionSize(36)

        layout.addWidget(self.tabel)

        # Tombol Aksi Bawah
        aksi_layout = QHBoxLayout()
        self.btn_cetak = QPushButton("Cetak Kuitansi Pembayaran (PDF)", self)
        self.btn_cetak.setProperty("tipe", "sukses")
        self.btn_cetak.clicked.connect(self._cetak_kuitansi)

        self.btn_balik = QPushButton("Batalkan Pembayaran / Salah Catat", self)
        self.btn_balik.setProperty("tipe", "bahaya")
        self.btn_balik.clicked.connect(self._buka_dialog_pembalik)

        aksi_layout.addWidget(self.btn_cetak)
        aksi_layout.addWidget(self.btn_balik)
        aksi_layout.addStretch()
        layout.addLayout(aksi_layout)

        self.daftar_bayar = []
        self.muat_data()

    def muat_data(self) -> None:
        k = self.input_cari.text().strip()
        self.daftar_bayar = ambil_riwayat_pembayaran_angsuran(self.conn, kata_kunci=k, limit=200)
        self.tabel.setRowCount(len(self.daftar_bayar))

        for baris, r in enumerate(self.daftar_bayar):
            self.tabel.setItem(baris, 0, QTableWidgetItem(str(r["id"])))
            self.tabel.setItem(baris, 1, QTableWidgetItem(format_tanggal_indo(r["tanggal"])))
            self.tabel.setItem(baris, 2, QTableWidgetItem(r["no_pinjaman"]))
            self.tabel.setItem(baris, 3, QTableWidgetItem(f"{r['nama_anggota']} ({r['no_anggota']})"))

            angs_teks = f"Ke-{r['angsuran_ke']}" if r["angsuran_ke"] else "Pelunasan Dipercepat"
            self.tabel.setItem(baris, 4, QTableWidgetItem(angs_teks))

            p_item = QTableWidgetItem(format_rupiah(r["bayar_pokok"]))
            p_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(baris, 5, p_item)

            j_item = QTableWidgetItem(format_rupiah(r["bayar_jasa"]))
            j_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(baris, 6, j_item)

            ket = r["keterangan"] or "-"
            if r["membalik_id"]:
                ket = f"[PEMBALIK #{r['membalik_id']}] {ket}"
            self.tabel.setItem(baris, 7, QTableWidgetItem(ket))

    def _cetak_kuitansi(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_bayar):
            QMessageBox.information(self, "Pilih Pembayaran", "Silakan klik baris pembayaran yang ingin dicetak kuitansinya.")
            return

        tx = self.daftar_bayar[baris]
        cur = self.conn.cursor()
        cur.execute("SELECT nilai FROM pengaturan WHERE kunci = 'nama_koperasi';")
        r_kop = cur.fetchone()
        nama_kop = r_kop[0] if r_kop else "Koperasi Simpan Pinjam"

        nama_file_def = f"Kuitansi_Angsuran_{tx['id']}_{tx['no_pinjaman']}.pdf"
        from PySide6.QtWidgets import QFileDialog
        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Simpan Kuitansi Angsuran PDF", nama_file_def, "PDF Files (*.pdf)"
        )
        if not path_simpan:
            return

        try:
            buat_kuitansi_angsuran_pdf(dict(tx), nama_kop, path_simpan)
            QMessageBox.information(self, "Berhasil", f"Kuitansi berhasil dicetak ke PDF:\n{path_simpan}")
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal mencetak kuitansi: {err}")

    def _buka_dialog_bayar(self) -> None:
        dlg = DialogInputAngsuran(self.conn, parent=self)
        if dlg.exec():
            self.muat_data()

    def _buka_dialog_pembalik(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_bayar):
            QMessageBox.information(self, "Pilih Pembayaran", "Silakan klik baris transaksi pembayaran yang ingin dikoreksi.")
            return

        tx = self.daftar_bayar[baris]
        
        # Dialog input alasan pembalik
        dlg = QDialog(self)
        dlg.setWindowTitle("Batalkan Pembayaran Angsuran (Salah Catat)")
        dlg.resize(480, 260)

        d_layout = QVBoxLayout(dlg)
        info_label = QLabel(
            f"<b>Perhatian:</b> Sesuai aturan akuntansi koperasi, pembayaran yang salah catat tidak dihapus permanen, "
            f"melainkan dibuatkan transaksi pembatalan otomatis untuk mengembalikan status cicilan pinjaman.<br><br>"
            f"<b>Rincian Pembayaran yang Dibatalkan:</b><br>"
            f"• No. Pembayaran: #{tx['id']}<br>"
            f"• Anggota: {tx['nama_anggota']} ({tx['no_anggota']})<br>"
            f"• Pinjaman: {tx['no_pinjaman']}<br>"
            f"• Nominal: Pokok {format_rupiah(tx['bayar_pokok'])}, Jasa {format_rupiah(tx['bayar_jasa'])}",
            dlg
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("background-color: #FEF3C7; padding: 10px; border-radius: 4px; color: #92400E;")
        d_layout.addWidget(info_label)

        form = QFormLayout()
        input_alasan = QLineEdit(dlg)
        input_alasan.setMinimumHeight(38)
        input_alasan.setPlaceholderText("Alasan pembatalan pembayaran...")
        form.addRow("Alasan Pembatalan *:", input_alasan)

        input_tgl = QDateEdit(dlg)
        input_tgl.setMinimumHeight(38)
        input_tgl.setCalendarPopup(True)
        input_tgl.setDate(QDate.currentDate())
        input_tgl.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Tanggal Pembatalan *:", input_tgl)
        d_layout.addLayout(form)

        b_layout = QHBoxLayout()
        btn_batal = QPushButton("Tutup / Kembali", dlg)
        btn_batal.setMinimumHeight(38)
        btn_batal.clicked.connect(dlg.reject)

        btn_proses = QPushButton("Proses Pembatalan", dlg)
        btn_proses.setProperty("tipe", "bahaya")
        btn_proses.setMinimumHeight(38)
        
        def do_balik():
            alasan = input_alasan.text().strip()
            if not alasan:
                QMessageBox.warning(dlg, "Alasan Wajib", "Masukkan alasan pembatalan pembayaran.")
                return
            tgl_iso = input_tgl.date().toString("yyyy-MM-dd")
            try:
                balik_pembayaran_angsuran(self.conn, tx["id"], alasan, tgl_iso)
                QMessageBox.information(dlg, "Berhasil", "Pembayaran berhasil dibatalkan dan status angsuran telah diperbarui.")
                dlg.accept()
                self.muat_data()
            except ValueError as err:
                QMessageBox.warning(dlg, "Gagal", str(err))
            except Exception as err:
                QMessageBox.critical(dlg, "Gagal", f"Terjadi kesalahan: {err}")

        btn_proses.clicked.connect(do_balik)
        b_layout.addStretch()
        b_layout.addWidget(btn_batal)
        b_layout.addWidget(btn_proses)
        d_layout.addLayout(b_layout)

        dlg.exec()

