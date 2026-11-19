"""
app/ui/layar_impor.py — Layar Impor Data Excel (SPEC.md 4.9).
- Unduh Template Excel (.xlsx) resmi
- Pilih file Excel / CSV dari komputer
- Menjalankan validasi ketat dan menampilkan pratinjau data valid & baris error
- Eksekusi impor aman dengan backup otomatis sebelum penulisan
"""
import sqlite3
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QGroupBox, QTabWidget, QTextEdit
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from app.layanan.impor_excel import (
    buat_template_impor_excel, validasi_file_impor, eksekusi_impor_data
)
from app.util.format import format_rupiah, format_tanggal_indo
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global


class LayarImpor(QWidget):
    """Layar Impor Data dari Excel."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.hasil_validasi = None
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        header_layout = QHBoxLayout()
        label_judul = QLabel("Impor Data Lama dari Excel", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(label_judul)

        header_layout.addStretch()

        self.btn_unduh_template = QPushButton("Unduh Template Excel", self)
        self.btn_unduh_template.setMinimumHeight(40)
        self.btn_unduh_template.setStyleSheet("background-color: #0D9488; color: white; font-weight: bold; padding: 0 14px;")
        self.btn_unduh_template.clicked.connect(self._unduh_template)
        header_layout.addWidget(self.btn_unduh_template)

        layout.addLayout(header_layout)

        # Baris Pilih File
        file_box = QGroupBox("Langkah 1: Pilih File Excel Data Lama", self)
        file_layout = QHBoxLayout(file_box)
        
        self.lbl_path_file = QLabel("Belum ada file yang dipilih.")
        self.lbl_path_file.setStyleSheet("color: #4B5563; font-style: italic;")

        self.btn_pilih_file = QPushButton("Pilih File Excel (.xlsx)", file_box)
        self.btn_pilih_file.setMinimumHeight(40)
        self.btn_pilih_file.clicked.connect(self._pilih_file)

        file_layout.addWidget(self.lbl_path_file, 1)
        file_layout.addWidget(self.btn_pilih_file)
        layout.addWidget(file_box)

        # Tab Pratinjau Data & Laporan Validasi
        self.tabs = QTabWidget(self)

        # Tab 1: Anggota
        self.tabel_anggota = QTableWidget()
        self.tabel_anggota.setColumnCount(5)
        self.tabel_anggota.setHorizontalHeaderLabels(["No Anggota", "Nama Lengkap", "NIK", "Unit", "Tgl Masuk"])
        self.tabel_anggota.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        terapkan_style_tabel_global(self.tabel_anggota)
        self.tabs.addTab(self.tabel_anggota, "Pratinjau Anggota (0)")

        # Tab 2: Simpanan
        self.tabel_simpanan = QTableWidget()
        self.tabel_simpanan.setColumnCount(5)
        self.tabel_simpanan.setHorizontalHeaderLabels(["No Anggota", "Saldo Pokok", "Saldo Wajib", "Saldo Sukarela", "Tgl Saldo"])
        self.tabel_simpanan.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        terapkan_style_tabel_global(self.tabel_simpanan, rata_kanan_kolom=[1, 2, 3])
        self.tabs.addTab(self.tabel_simpanan, "Pratinjau Simpanan (0)")

        # Tab 3: Pinjaman
        self.tabel_pinjaman = QTableWidget()
        self.tabel_pinjaman.setColumnCount(6)
        self.tabel_pinjaman.setHorizontalHeaderLabels(["No Pinjaman", "No Anggota", "Plafon", "Tenor", "Jasa/Bln", "Sisa Pokok"])
        self.tabel_pinjaman.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        terapkan_style_tabel_global(self.tabel_pinjaman, rata_kanan_kolom=[2, 4, 5])
        self.tabs.addTab(self.tabel_pinjaman, "Pratinjau Pinjaman (0)")

        # Tab 4: Laporan Error / Validasi
        self.txt_error = QTextEdit()
        self.txt_error.setReadOnly(True)
        self.txt_error.setStyleSheet("color: #DC2626; background-color: #FEF2F2; font-family: Consolas, monospace;")
        self.tabs.addTab(self.txt_error, "Laporan Masalah (0)")

        layout.addWidget(self.tabs)

        # Tombol Eksekusi Bawah
        bottom_layout = QHBoxLayout()
        self.lbl_status_validasi = QLabel("Silakan pilih file untuk memulai validasi.", self)
        self.lbl_status_validasi.setStyleSheet("font-weight: bold; color: #1E3A8A;")

        self.btn_eksekusi = QPushButton("Simpan dan Impor Data ke Database", self)
        self.btn_eksekusi.setMinimumHeight(44)
        self.btn_eksekusi.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 0 18px;")
        self.btn_eksekusi.setEnabled(False)
        self.btn_eksekusi.clicked.connect(self._eksekusi_impor)

        bottom_layout.addWidget(self.lbl_status_validasi, 1)
        bottom_layout.addWidget(self.btn_eksekusi)
        layout.addLayout(bottom_layout)

    def _unduh_template(self) -> None:
        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Simpan Template Impor", "Template_Impor_Koperasi.xlsx", "Excel Files (*.xlsx)"
        )
        if not path_simpan:
            return
        try:
            buat_template_impor_excel(path_simpan)
            QMessageBox.information(
                self, "Template Berhasil Diunduh",
                f"Template Excel telah tersimpan di:\n{path_simpan}\n\nSilakan isi sesuai kolom yang tersedia."
            )
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal membuat template: {err}")

    def _pilih_file(self) -> None:
        path_file, _ = QFileDialog.getOpenFileName(
            self, "Pilih File Excel Impor", "", "Excel Files (*.xlsx)"
        )
        if not path_file:
            return

        self.lbl_path_file.setText(path_file)
        self._jalankan_validasi(path_file)

    def _jalankan_validasi(self, path_file: str) -> None:
        try:
            val = validasi_file_impor(self.conn, path_file)
            self.hasil_validasi = val

            # Update Tab Anggota
            anggota_list = val["anggota"]
            self.tabel_anggota.setRowCount(len(anggota_list))
            self.tabs.setTabText(0, f"Pratinjau Anggota ({len(anggota_list)})")
            for b, r in enumerate(anggota_list):
                self.tabel_anggota.setItem(b, 0, QTableWidgetItem(r["no_anggota"]))
                self.tabel_anggota.setItem(b, 1, QTableWidgetItem(r["nama"]))
                self.tabel_anggota.setItem(b, 2, QTableWidgetItem(r["nik_karyawan"] or "-"))
                self.tabel_anggota.setItem(b, 3, QTableWidgetItem(r["unit"] or "-"))
                self.tabel_anggota.setItem(b, 4, QTableWidgetItem(format_tanggal_indo(r["tanggal_masuk"])))

            # Update Tab Simpanan
            simpanan_list = val["simpanan"]
            self.tabel_simpanan.setRowCount(len(simpanan_list))
            self.tabs.setTabText(1, f"Pratinjau Simpanan ({len(simpanan_list)})")
            for b, r in enumerate(simpanan_list):
                self.tabel_simpanan.setItem(b, 0, QTableWidgetItem(r["no_anggota"]))
                self.tabel_simpanan.setItem(b, 1, QTableWidgetItem(format_rupiah(r["saldo_pokok"])))
                self.tabel_simpanan.setItem(b, 2, QTableWidgetItem(format_rupiah(r["saldo_wajib"])))
                self.tabel_simpanan.setItem(b, 3, QTableWidgetItem(format_rupiah(r["saldo_sukarela"])))
                self.tabel_simpanan.setItem(b, 4, QTableWidgetItem(format_tanggal_indo(r["tanggal_saldo"])))

            # Update Tab Pinjaman
            pinjaman_list = val["pinjaman"]
            self.tabel_pinjaman.setRowCount(len(pinjaman_list))
            self.tabs.setTabText(2, f"Pratinjau Pinjaman ({len(pinjaman_list)})")
            for b, r in enumerate(pinjaman_list):
                self.tabel_pinjaman.setItem(b, 0, QTableWidgetItem(r["no_pinjaman"]))
                self.tabel_pinjaman.setItem(b, 1, QTableWidgetItem(r["no_anggota"]))
                self.tabel_pinjaman.setItem(b, 2, QTableWidgetItem(format_rupiah(r["plafon"])))
                self.tabel_pinjaman.setItem(b, 3, QTableWidgetItem(f"{r['tenor']} bln"))
                self.tabel_pinjaman.setItem(b, 4, QTableWidgetItem(f"{r['jasa_persen']}%"))
                self.tabel_pinjaman.setItem(b, 5, QTableWidgetItem(format_rupiah(r["sisa_pokok"])))

            # Update Tab Masalah
            errors = val["daftar_error"]
            self.tabs.setTabText(3, f"Laporan Masalah ({len(errors)})")
            if errors:
                self.txt_error.setPlainText("\n".join(errors))
                self.lbl_status_validasi.setText(f"Ditemukan {len(errors)} masalah pada berkas. Harap perbaiki sebelum impor.")
                self.lbl_status_validasi.setStyleSheet("color: #DC2626; font-weight: bold;")
                self.btn_eksekusi.setEnabled(False)
                self.tabs.setCurrentIndex(3)
            else:
                self.txt_error.setPlainText("Semua baris data valid! Berkas siap diimpor ke database.")
                total_baris = len(anggota_list) + len(simpanan_list) + len(pinjaman_list)
                self.lbl_status_validasi.setText(f"Validasi Sukses: {total_baris} data siap dimasukkan.")
                self.lbl_status_validasi.setStyleSheet("color: #16A34A; font-weight: bold;")
                self.btn_eksekusi.setEnabled(total_baris > 0)
                self.tabs.setCurrentIndex(0)

        except Exception as err:
            QMessageBox.critical(self, "Gagal Membaca File", f"Terjadi kesalahan saat memproses file Excel: {err}")

    def _eksekusi_impor(self) -> None:
        if not self.hasil_validasi or not self.hasil_validasi.get("siap_impor"):
            return

        konfirmasi = QMessageBox.question(
            self, "Konfirmasi Impor",
            "Mulai proses impor data?\n\n"
            "Aplikasi akan membuat backup otomatis database terlebih dahulu sebelum menyimpan data baru.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if konfirmasi != QMessageBox.StandardButton.Yes:
            return

        try:
            hasil = eksekusi_impor_data(self.conn, self.hasil_validasi, backup_dulu=True)
            QMessageBox.information(
                self, "Impor Berhasil",
                f"Data berhasil diimpor ke database:\n"
                f"• {hasil['anggota']} Anggota Baru\n"
                f"• {hasil['simpanan']} Saldo Simpanan Awal\n"
                f"• {hasil['pinjaman']} Pinjaman Berjalan"
            )
            self.btn_eksekusi.setEnabled(False)
            self.lbl_status_validasi.setText("Impor selesai diproses.")
        except Exception as err:
            QMessageBox.critical(self, "Gagal Impor", f"Terjadi kesalahan saat menyimpan data impor: {err}")

