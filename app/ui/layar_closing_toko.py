"""
app/ui/layar_closing_toko.py — Layar Closing Bulanan Unit Toko:
1. Pemeriksaan Pra-Closing Toko (Opname draft, setoran penitip, rekonsiliasi stok, piutang, kas)
2. Ringkasan Keuangan Closing Toko
3. Eksekusi Closing Toko & Kunci Periode Transaksi Toko
4. Pembukaan Kembali Closing Toko dengan PIN Keamanan
"""
import sqlite3
from datetime import date
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QMessageBox, QInputDialog, QFrame, QGridLayout
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt

from app.db.repo_closing_toko import (
    periksa_pra_closing_toko, eksekusi_closing_toko, buka_kembali_closing_toko
)
from app.util.format import format_rupiah, format_tanggal_indo


class LayarClosingToko(QWidget):
    """Layar Closing Bulanan Unit Toko."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._inisialisasi_ui()

    def _inisialisasi_ui(self):
        self.setFont(QFont("Segoe UI", 11))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(12)

        # Header
        top_bar = QHBoxLayout()
        lbl_judul = QLabel("Closing Akhir Bulan Unit Toko Retail", self)
        lbl_judul.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        lbl_judul.setStyleSheet("color: #1E3A8A;")
        top_bar.addWidget(lbl_judul)

        top_bar.addStretch()

        layout.addLayout(top_bar)

        # Pemilih Periode Closing
        bar_periode = QHBoxLayout()
        bar_periode.addWidget(QLabel("Pilih Periode Bulan:", self))

        self.cmb_periode = QComboBox(self)
        tgl_ini = date.today()
        # Isi pilihan bulan terakhir
        for i in range(6):
            thn = tgl_ini.year
            bln = tgl_ini.month - i
            if bln <= 0:
                bln += 12
                thn -= 1
            self.cmb_periode.addItem(f"{thn:04d}-{bln:02d}")
        self.cmb_periode.currentIndexChanged.connect(self._periksa_periode)
        bar_periode.addWidget(self.cmb_periode)

        btn_cek = QPushButton("Periksa Kelayakan Closing", self)
        btn_cek.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 6px 14px;")
        btn_cek.clicked.connect(self._periksa_periode)
        bar_periode.addWidget(btn_cek)

        bar_periode.addStretch()

        self.btn_reopen = QPushButton("Buka Kembali Periode (Reopen)", self)
        self.btn_reopen.setStyleSheet("background-color: #D97706; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_reopen.clicked.connect(self._buka_reopen)
        bar_periode.addWidget(self.btn_reopen)

        layout.addLayout(bar_periode)

        # Panel Hasil Pemeriksaan Pra-Closing
        self.panel_hasil = QFrame(self)
        self.panel_hasil.setStyleSheet("background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 8px; padding: 12px;")
        self.lay_hasil = QVBoxLayout(self.panel_hasil)

        self.lbl_status_pra = QLabel("Status Pra-Closing: Belum diperiksa", self)
        self.lbl_status_pra.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lay_hasil.addWidget(self.lbl_status_pra)

        self.lbl_rincian_masalah = QLabel("", self)
        self.lbl_rincian_masalah.setWordWrap(True)
        self.lay_hasil.addWidget(self.lbl_rincian_masalah)

        layout.addWidget(self.panel_hasil)

        # Panel Ringkasan Finansial Closing
        self.panel_ringkasan = QFrame(self)
        self.panel_ringkasan.setStyleSheet("background-color: white; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px;")
        grid_r = QGridLayout(self.panel_ringkasan)

        self.lbl_c_penjualan = QLabel("Penjualan: Rp 0", self)
        grid_r.addWidget(self.lbl_c_penjualan, 0, 0)

        self.lbl_c_hpp = QLabel("HPP: Rp 0", self)
        grid_r.addWidget(self.lbl_c_hpp, 0, 1)

        self.lbl_c_laba = QLabel("Laba Kotor: Rp 0", self)
        self.lbl_c_laba.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_c_laba.setStyleSheet("color: #059669;")
        grid_r.addWidget(self.lbl_c_laba, 0, 2)

        self.lbl_c_kas = QLabel("Kas Toko Akhir: Rp 0", self)
        grid_r.addWidget(self.lbl_c_kas, 1, 0)

        self.lbl_c_piutang = QLabel("Piutang Akhir: Rp 0", self)
        grid_r.addWidget(self.lbl_c_piutang, 1, 1)

        self.lbl_c_persediaan = QLabel("Nilai Persediaan Akhir: Rp 0", self)
        grid_r.addWidget(self.lbl_c_persediaan, 1, 2)

        layout.addWidget(self.panel_ringkasan)

        # Tombol Eksekusi Closing
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_eksekusi = QPushButton("EKSEKUSI CLOSING TOKO BULAN INI", self)
        self.btn_eksekusi.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; font-size: 13pt; padding: 10px 24px; border-radius: 6px;")
        self.btn_eksekusi.setEnabled(False)
        self.btn_eksekusi.clicked.connect(self._eksekusi_closing)
        btn_box.addWidget(self.btn_eksekusi)

        layout.addLayout(btn_box)
        layout.addStretch()

        self._periksa_periode()

    def _periksa_periode(self):
        periode = self.cmb_periode.currentText().strip()
        res = periksa_pra_closing_toko(self.conn, periode)

        ringk = res["ringkasan"]
        self.lbl_c_penjualan.setText(f"Penjualan: {format_rupiah(ringk['total_penjualan'])}")
        self.lbl_c_hpp.setText(f"HPP: {format_rupiah(ringk['total_hpp'])}")
        self.lbl_c_laba.setText(f"Laba Kotor: {format_rupiah(ringk['laba_kotor'])}")
        self.lbl_c_kas.setText(f"Kas Toko Akhir: {format_rupiah(ringk['kas_toko_akhir'])}")
        self.lbl_c_piutang.setText(f"Piutang Akhir: {format_rupiah(ringk['total_piutang'])}")
        self.lbl_c_persediaan.setText(f"Nilai Persediaan: {format_rupiah(ringk['nilai_persediaan'])}")

        if res["bisa_closing"]:
            self.lbl_status_pra.setText(f"Status Pra-Closing: SIAP CLOSING (Semua rekonsiliasi cocok)")
            self.lbl_status_pra.setStyleSheet("color: #059669; font-weight: bold;")
            self.lbl_rincian_masalah.setText("Tidak ditemukan masalah. Semua mutasi, sisa lot, kas toko, dan piutang telah terekonsiliasi sempurna.")
            self.btn_eksekusi.setEnabled(True)
        else:
            self.lbl_status_pra.setText(f"Status Pra-Closing: BELUM BISA CLOSING (Terdapat kendala)")
            self.lbl_status_pra.setStyleSheet("color: #DC2626; font-weight: bold;")
            self.lbl_rincian_masalah.setText("- " + "\n- ".join(res["masalah"]))
            self.btn_eksekusi.setEnabled(False)

    def _eksekusi_closing(self):
        periode = self.cmb_periode.currentText().strip()
        konfirmasi = QMessageBox.question(
            self,
            "Konfirmasi Closing Toko",
            f"Apakah Anda yakin ingin menyelesaikan Closing Toko untuk periode {periode}?\n"
            "- Sistem akan membuat cadangan otomatis database.\n"
            "- Snapshot stok barang dan finansial toko akan dikunci permanen.\n"
            "- Seluruh transaksi pada periode {periode} tidak dapat diubah kembali.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if konfirmasi != QMessageBox.StandardButton.Yes:
            return

        try:
            cid = eksekusi_closing_toko(self.conn, periode, "Closing bulanan toko disetujui admin")
            QMessageBox.information(
                self,
                "Closing Berhasil",
                f"Closing Toko periode {periode} telah berhasil disimpan dan transaksi telah dikunci."
            )
            self._periksa_periode()
        except Exception as e:
            QMessageBox.warning(self, "Gagal Closing", f"Terjadi kesalahan saat closing: {e}")

    def _buka_reopen(self):
        periode = self.cmb_periode.currentText().strip()
        pin, ok = QInputDialog.getText(self, "Otorisasi PIN Keamanan", "Masukkan PIN Keamanan untuk membuka kembali periode closing:", QLineEdit.EchoMode.Password)
        if not ok or not pin:
            return

        alasan, ok2 = QInputDialog.getText(self, "Alasan Reopen", "Masukkan alasan pembukaan kembali closing toko:")
        if not ok2 or not alasan:
            return

        try:
            buka_kembali_closing_toko(self.conn, periode, pin, alasan)
            QMessageBox.information(self, "Berhasil", f"Periode closing {periode} telah dibuka kembali.")
            self._periksa_periode()
        except Exception as e:
            QMessageBox.warning(self, "Otorisasi Gagal", f"Tidak dapat membuka kembali closing: {e}")
