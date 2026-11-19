"""
app/ui/layar_closing.py — Layar Closing Bulanan & Kunci Periode (SPEC.md 4.8).
- Pemeriksaan pra-closing (draft belum disimpan, cicilan belum lunas, rekonsiliasi kas)
- Ringkasan snapshot closing untuk konfirmasi
- Backup otomatis sebelum closing
- Penguncian periode otomatis
- Dialog otorisasi PIN untuk membuka kembali closing (reopen)
"""
import sqlite3
from datetime import date
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QMessageBox, QDialog, QFormLayout, QLineEdit, QTextEdit,
    QGroupBox, QGridLayout
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from app.db.repo_closing import (
    jalankan_pemeriksaan_pra_closing, hitung_ringkasan_closing,
    eksekusi_closing_bulanan, buka_kembali_closing, ambil_daftar_riwayat_closing
)
from app.util.format import format_rupiah, format_tanggal_indo
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global


class LayarClosing(QWidget):
    """Layar Closing Akhir Bulan."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        header_layout = QHBoxLayout()
        label_judul = QLabel("Closing Akhir Bulan dan Kunci Periode", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(label_judul)

        header_layout.addStretch()

        self.btn_proses_closing = QPushButton("Jalankan Closing Bulan Ini", self)
        self.btn_proses_closing.setMinimumHeight(42)
        self.btn_proses_closing.setStyleSheet("background-color: #7C3AED; color: white; font-weight: bold; padding: 0 16px; border-radius: 4px;")
        self.btn_proses_closing.clicked.connect(self._mulai_proses_closing)
        header_layout.addWidget(self.btn_proses_closing)

        layout.addLayout(header_layout)

        # Bagian Keterangan
        info_label = QLabel(
            "<b>Mengenai Closing Bulanan:</b><br>"
            "Proses closing akan melakukan backup otomatis, menyimpan snapshot saldo seluruh anggota dan posisi kas, "
            "serta <b>mengunci</b> seluruh transaksi periode tersebut agar tidak dapat diubah tanpa otorisasi PIN.",
            self
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("background-color: #F3E8FF; color: #581C87; padding: 10px; border-radius: 6px; border: 1px solid #D8B4FE;")
        layout.addWidget(info_label)

        # Tabel Riwayat Periode Closing
        layout.addWidget(QLabel("Riwayat Periode Yang Sudah Di-Closing:"))
        self.tabel_riwayat = QTableWidget(self)
        self.tabel_riwayat.setFont(QFont("Segoe UI", 11))
        self.tabel_riwayat.setColumnCount(8)
        self.tabel_riwayat.setHorizontalHeaderLabels([
            "Periode", "Tgl Closing", "Kas Awal", "Kas Masuk", "Kas Keluar", "Kas Akhir", "Total Simpanan", "Status"
        ])
        self.tabel_riwayat.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        terapkan_style_tabel_global(
            self.tabel_riwayat,
            rata_kanan_kolom=[2, 3, 4, 5, 6],
            kolom_status=7
        )
        layout.addWidget(self.tabel_riwayat)

        # Tombol Bawah: Buka Kembali Closing
        aksi_bottom = QHBoxLayout()
        self.btn_buka_closing = QPushButton("Buka Kembali Closing Terpilih (Perlu PIN)", self)
        self.btn_buka_closing.setMinimumHeight(40)
        self.btn_buka_closing.setStyleSheet("color: #DC2626;")
        self.btn_buka_closing.clicked.connect(self._buka_kembali_closing_dialog)
        aksi_bottom.addWidget(self.btn_buka_closing)
        aksi_bottom.addStretch()
        layout.addLayout(aksi_bottom)

        self.muat_riwayat()

    def muat_riwayat(self) -> None:
        riwayat = ambil_daftar_riwayat_closing(self.conn)
        self.tabel_riwayat.setRowCount(len(riwayat))

        for b, r in enumerate(riwayat):
            self.tabel_riwayat.setItem(b, 0, QTableWidgetItem(r["periode"]))
            self.tabel_riwayat.setItem(b, 1, QTableWidgetItem(format_tanggal_indo(r["tanggal_closing"])))
            
            for col_idx, col_name in enumerate(["saldo_kas_awal", "total_kas_masuk", "total_kas_keluar", "saldo_kas_akhir", "total_simpanan"], start=2):
                item = QTableWidgetItem(format_rupiah(r[col_name]))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabel_riwayat.setItem(b, col_idx, item)

            stat_item = QTableWidgetItem("Terkunci" if r["status"] == "tertutup" else "Dibuka Kembali")
            if r["status"] == "tertutup":
                stat_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                stat_item.setForeground(Qt.GlobalColor.darkRed)
            self.tabel_riwayat.setItem(b, 7, stat_item)

    def _mulai_proses_closing(self) -> None:
        # Default periode: bulan berjalan
        tgl_hari_ini = date.today()
        periode_default = f"{tgl_hari_ini.year:04d}-{tgl_hari_ini.month:02d}"

        # Buka dialog konfirmasi pra-closing
        dlg = DialogPemeriksaanClosing(self.conn, periode=periode_default, parent=self)
        if dlg.exec():
            self.muat_riwayat()

    def _buka_kembali_closing_dialog(self) -> None:
        baris = self.tabel_riwayat.currentRow()
        if baris < 0:
            QMessageBox.information(self, "Pilih Periode", "Silakan klik baris periode yang ingin dibuka kembali.")
            return

        periode = self.tabel_riwayat.item(baris, 0).text()
        status = self.tabel_riwayat.item(baris, 7).text()
        if status != "Terkunci":
            QMessageBox.information(self, "Informasi", f"Periode {periode} saat ini tidak berstatus terkunci.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Buka Kunci Closing Periode {periode}")
        dlg.resize(450, 260)
        dlg.setFont(QFont("Segoe UI", 12))

        d_layout = QVBoxLayout(dlg)
        warning_lbl = QLabel(
            f"<b>Peringatan:</b> Membuka kembali periode {periode} akan membatalkan status terkunci dan memungkinkan "
            f"transaksi baru dimasukkan pada periode tersebut.<br>"
            f"Tindakan ini memerlukan PIN otorisasi dan akan dicatat ke log aktivitas.",
            dlg
        )
        warning_lbl.setWordWrap(True)
        warning_lbl.setStyleSheet("background-color: #FEE2E2; color: #991B1B; padding: 10px; border-radius: 4px;")
        d_layout.addWidget(warning_lbl)

        form = QFormLayout()
        input_pin = QLineEdit(dlg)
        input_pin.setEchoMode(QLineEdit.EchoMode.Password)
        input_pin.setPlaceholderText("PIN default: 1234")
        form.addRow("PIN Keamanan *:", input_pin)

        input_alasan = QLineEdit(dlg)
        input_alasan.setPlaceholderText("Alasan membuka kembali closing...")
        form.addRow("Alasan *:", input_alasan)
        d_layout.addLayout(form)

        btn_layout = QHBoxLayout()
        btn_batal = QPushButton("Batal", dlg)
        btn_batal.clicked.connect(dlg.reject)

        btn_buka = QPushButton("Buka Kunci Periode", dlg)
        btn_buka.setStyleSheet("background-color: #DC2626; color: white; font-weight: bold;")
        
        def do_buka():
            pin = input_pin.text().strip()
            alasan = input_alasan.text().strip()
            if not pin or not alasan:
                QMessageBox.warning(dlg, "Lengkapi Data", "PIN dan alasan wajib diisi.")
                return
            try:
                buka_kembali_closing(self.conn, periode, pin, alasan)
                QMessageBox.information(dlg, "Berhasil", f"Periode {periode} berhasil dibuka kembali.")
                dlg.accept()
                self.muat_riwayat()
            except ValueError as err:
                QMessageBox.warning(dlg, "Gagal", str(err))

        btn_buka.clicked.connect(do_buka)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_batal)
        btn_layout.addWidget(btn_buka)
        d_layout.addLayout(btn_layout)

        dlg.exec()


class DialogPemeriksaanClosing(QDialog):
    """Dialog Pemeriksaan Pra-Closing dan Konfirmasi Snapshot."""

    def __init__(self, conn: sqlite3.Connection, periode: str, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.periode = periode
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle(f"Pemeriksaan Closing Periode {self.periode}")
        self.resize(750, 600)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)

        # 1. Jalankan pra-closing
        self.pra = jalankan_pemeriksaan_pra_closing(self.conn, self.periode)
        self.ringkasan = hitung_ringkasan_closing(self.conn, self.periode)

        # Info Status Pra-Closing
        status_box = QGroupBox("Hasil Pemeriksaan Pra-Closing", self)
        s_layout = QVBoxLayout(status_box)

        if self.pra["sudah_closing"]:
            s_layout.addWidget(QLabel("<font color='red'>Periode ini sudah pernah di-closing dan berstatus terkunci.</font>"))
        else:
            s_layout.addWidget(QLabel("Status Periode: <b>Belum di-closing</b> (Siap diproses)."))

        if self.pra["daftar_draft"]:
            s_layout.addWidget(QLabel(f"Draft formulir belum disimpan: {', '.join(self.pra['daftar_draft'])}"))
        else:
            s_layout.addWidget(QLabel("Draft Formulir: <b>Semua bersih</b> (Tidak ada input tertinggal)."))

        if self.pra["angsuran_terlewat"]:
            s_layout.addWidget(QLabel(f"Perhatian: Ada <b>{len(self.pra['angsuran_terlewat'])} angsuran</b> yang jatuh tempo bulan ini namun belum lunas."))
        else:
            s_layout.addWidget(QLabel("Status Angsuran: Seluruh cicilan jatuh tempo periode ini telah tertangani."))

        layout.addWidget(status_box)

        # Ringkasan Angka Closing
        box_angka = QGroupBox("Ringkasan Angka Finansial Yang Akan Ditutup", self)
        grid_a = QGridLayout(box_angka)

        grid_a.addWidget(QLabel("Saldo Kas Awal Periode:"), 0, 0)
        grid_a.addWidget(QLabel(format_rupiah(self.ringkasan["saldo_kas_awal"])), 0, 1)
        grid_a.addWidget(QLabel("Total Pemasukan Kas:"), 1, 0)
        grid_a.addWidget(QLabel(format_rupiah(self.ringkasan["total_kas_masuk"])), 1, 1)
        grid_a.addWidget(QLabel("Total Pengeluaran Kas:"), 2, 0)
        grid_a.addWidget(QLabel(format_rupiah(self.ringkasan["total_kas_keluar"])), 2, 1)
        grid_a.addWidget(QLabel("<b>Saldo Kas Akhir:</b>"), 3, 0)
        grid_a.addWidget(QLabel(f"<b>{format_rupiah(self.ringkasan['saldo_kas_akhir'])}</b>"), 3, 1)

        grid_a.addWidget(QLabel("Total Seluruh Simpanan:"), 0, 2)
        grid_a.addWidget(QLabel(format_rupiah(self.ringkasan["total_simpanan"])), 0, 3)
        grid_a.addWidget(QLabel("Total Sisa Pokok Pinjaman:"), 1, 2)
        grid_a.addWidget(QLabel(format_rupiah(self.ringkasan["total_sisa_pokok_pinjaman"])), 1, 3)
        grid_a.addWidget(QLabel("Total Jasa Diterima:"), 2, 2)
        grid_a.addWidget(QLabel(format_rupiah(self.ringkasan["total_jasa_diterima"])), 2, 3)
        grid_a.addWidget(QLabel("Snapshot Anggota:"), 3, 2)
        grid_a.addWidget(QLabel(f"{len(self.ringkasan['snapshot_anggota'])} Anggota"), 3, 3)

        layout.addWidget(box_angka)

        # Catatan Closing
        self.input_catatan = QLineEdit(self)
        self.input_catatan.setPlaceholderText("Catatan penutupan buku closing (opsional)...")
        layout.addWidget(QLabel("Catatan Tambahan:"))
        layout.addWidget(self.input_catatan)

        # Tombol Aksi
        btn_layout = QHBoxLayout()
        self.btn_batal = QPushButton("Batal", self)
        self.btn_batal.clicked.connect(self.reject)

        self.btn_konfirmasi_closing = QPushButton("Konfirmasi dan Kunci Periode", self)
        self.btn_konfirmasi_closing.setMinimumHeight(42)
        self.btn_konfirmasi_closing.setStyleSheet("background-color: #7C3AED; color: white; font-weight: bold; padding: 0 16px;")
        self.btn_konfirmasi_closing.clicked.connect(self._eksekusi)

        if self.pra["sudah_closing"]:
            self.btn_konfirmasi_closing.setEnabled(False)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_batal)
        btn_layout.addWidget(self.btn_konfirmasi_closing)
        layout.addLayout(btn_layout)

    def _eksekusi(self) -> None:
        tanya = QMessageBox.question(
            self,
            "Konfirmasi Penutupan Buku",
            f"Apakah Anda yakin ingin melakukan closing untuk periode {self.periode}?\n\n"
            f"1. Database akan di-backup otomatis.\n"
            f"2. Snapshot saldo simpanan dan pinjaman akan disimpan permanen.\n"
            f"3. Seluruh transaksi periode {self.periode} akan dikunci.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if tanya != QMessageBox.StandardButton.Yes:
            return

        catatan = self.input_catatan.text().strip()
        try:
            eksekusi_closing_bulanan(self.conn, self.periode, catatan=catatan or None, backup_dulu=True)
            QMessageBox.information(
                self, "Closing Selesai",
                f"Closing periode {self.periode} berhasil dieksekusi dan seluruh data transaksi telah terkunci dengan aman."
            )
            self.accept()
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Terjadi kesalahan saat closing: {err}")

