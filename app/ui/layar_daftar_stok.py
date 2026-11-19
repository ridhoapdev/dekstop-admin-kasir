"""
app/ui/layar_daftar_stok.py — Layar Pemantauan Daftar Stok FIFO Real-time.
Kolom: Kode, Nama, Kategori, Stok Dasar, Setara Satuan Besar (misal: 3 dus 5 pcs),
Stok Minimum, Status (Aman / Menipis / Habis / Minus).
Realtime update via bus_sinyal saat ada transaksi pembelian/mutasi stok.
Dialog Rekonsiliasi Stok instan.
"""
import sqlite3
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QTextEdit
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt

from app.db.repo_barang import cari_barang, ambil_satuan_barang
from app.layanan.layanan_stok import rekonsiliasi_stok_barang, cek_izinkan_stok_minus, atur_izinkan_stok_minus
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global
from app.layanan.bus_sinyal import langganan, lepas_langganan


class LayarDaftarStok(QWidget):
    """Layar Daftar Stok Barang Real-time."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.daftar_stok: List[Dict[str, Any]] = []
        self._inisialisasi_ui()
        langganan("stok_berubah", self.muat_data)

    def closeEvent(self, event):
        lepas_langganan("stok_berubah", self.muat_data)
        super().closeEvent(event)

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(12)

        # Header dan Filter
        top_bar = QHBoxLayout()
        lbl_cari = QLabel("Cari Stok:", self)
        lbl_cari.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        top_bar.addWidget(lbl_cari)

        self.input_cari = QLineEdit(self)
        self.input_cari.setPlaceholderText("Ketik nama produk atau kode barang...")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.textChanged.connect(self.muat_data)
        top_bar.addWidget(self.input_cari)

        btn_rekon = QPushButton("Periksa Rekonsiliasi Stok", self)
        btn_rekon.setMinimumHeight(40)
        btn_rekon.setStyleSheet("background-color: #0284C7; color: white; font-weight: bold; padding: 0 16px;")
        btn_rekon.clicked.connect(self._jalankan_rekonsiliasi)
        top_bar.addWidget(btn_rekon)

        btn_opsi_minus = QPushButton("Pengaturan Stok Minus", self)
        btn_opsi_minus.setMinimumHeight(40)
        btn_opsi_minus.clicked.connect(self._toggle_pengaturan_minus)
        top_bar.addWidget(btn_opsi_minus)

        layout.addLayout(top_bar)

        # Tabel Stok
        self.tabel = QTableWidget(self)
        self.tabel.setColumnCount(7)
        self.tabel.setHorizontalHeaderLabels([
            "Kode", "Nama Barang", "Kategori", "Stok Satuan Dasar",
            "Setara Satuan Besar", "Stok Minimum", "Status Stok"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabel.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 110)  # Kode
        self.tabel.setColumnWidth(2, 120)  # Kategori
        self.tabel.setColumnWidth(3, 140)  # Stok Satuan Dasar
        self.tabel.setColumnWidth(5, 110)  # Stok Minimum
        self.tabel.setColumnWidth(6, 120)  # Status Stok
        terapkan_style_tabel_global(
            self.tabel,
            rata_kanan_kolom=[3, 5],
            kolom_status=6
        )
        layout.addWidget(self.tabel)

        self.muat_data()

    def muat_data(self) -> None:
        kata_kunci = self.input_cari.text().strip()
        self.daftar_stok = cari_barang(self.conn, kata_kunci, hanya_aktif=True, limit=200)
        self.tabel.setRowCount(len(self.daftar_stok))

        for idx, b in enumerate(self.daftar_stok):
            stok_saat_ini = b["stok_saat_ini"]
            sat_dasar = b["satuan_dasar"]
            stok_min = b["stok_minimum"]

            self.tabel.setItem(idx, 0, QTableWidgetItem(b["kode"]))
            self.tabel.setItem(idx, 1, QTableWidgetItem(b["nama"]))
            self.tabel.setItem(idx, 2, QTableWidgetItem(b["kategori"] or "-"))

            # Stok Satuan Dasar
            stok_dasar_str = f"{stok_saat_ini:,} {sat_dasar}".replace(",", ".")
            item_dasar = QTableWidgetItem(stok_dasar_str)
            item_dasar.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(idx, 3, item_dasar)

            # Hitung setara satuan besar
            setara_str = self._hitung_setara_satuan_besar(b["id"], stok_saat_ini, sat_dasar)
            self.tabel.setItem(idx, 4, QTableWidgetItem(setara_str))

            # Stok Minimum
            stok_min_str = f"{stok_min:,} {sat_dasar}".replace(",", ".")
            item_min = QTableWidgetItem(stok_min_str)
            item_min.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(idx, 5, item_min)

            # Status Stok
            status_item = QTableWidgetItem()
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if stok_saat_ini < 0:
                status_item.setText("MINUS (HUTANG STOK)")
                status_item.setForeground(Qt.GlobalColor.white)
                status_item.setBackground(QColor("#DC2626"))
            elif stok_saat_ini == 0:
                status_item.setText("Habis")
                status_item.setForeground(Qt.GlobalColor.darkRed)
            elif stok_saat_ini <= stok_min:
                status_item.setText("Menipis")
                status_item.setForeground(QColor("#D97706"))
            else:
                status_item.setText("Aman")
                status_item.setForeground(QColor("#059669"))

            self.tabel.setItem(idx, 6, status_item)

    def _hitung_setara_satuan_besar(self, barang_id: int, qty_dasar: int, sat_dasar: str) -> str:
        """Contoh: jika 1 dus = 20 pcs, 65 pcs -> '3 dus 5 pcs'."""
        if qty_dasar <= 0:
            return f"0 {sat_dasar}"

        satuan_list = ambil_satuan_barang(self.conn, barang_id)
        # Ambil satuan non-dasar (isi > 1) urut dari isi terbesar
        satuan_besar = [s for s in satuan_list if s["isi_dalam_satuan_dasar"] > 1]
        satuan_besar.sort(key=lambda s: s["isi_dalam_satuan_dasar"], reverse=True)

        if not satuan_besar:
            return f"{qty_dasar:,} {sat_dasar}".replace(",", ".")

        bagian = []
        sisa = qty_dasar
        for sb in satuan_besar:
            isi = sb["isi_dalam_satuan_dasar"]
            jml = sisa // isi
            if jml > 0:
                bagian.append(f"{jml} {sb['nama_satuan']}")
                sisa = sisa % isi

        if sisa > 0:
            bagian.append(f"{sisa} {sat_dasar}")

        return " ".join(bagian) if bagian else f"{qty_dasar} {sat_dasar}"

    def _jalankan_rekonsiliasi(self) -> None:
        """Pemeriksaan integritas stok_saat_ini == sum mutasi == sum sisa lot."""
        selisih = rekonsiliasi_stok_barang(self.conn)
        if not selisih:
            QMessageBox.information(
                self, "Rekonsiliasi Sukses",
                "Semua data stok 100% cocok!\n\n"
                "- Stok Saat Ini == Total Mutasi Stok\n"
                "- Stok Saat Ini == Total Sisa Lot FIFO"
            )
        else:
            rincian = "\n".join(
                f"- {s['kode']} ({s['nama']}): Stok={s['stok_saat_ini']}, Mutasi={s['total_mutasi']}, Lot={s['total_sisa_lot']}"
                for s in selisih[:5]
            )
            QMessageBox.warning(
                self, "Peringatan Selisih Stok",
                f"Ditemukan selisih pada {len(selisih)} barang:\n{rincian}\n\nSilakan periksa catatan mutasi dan lot terkait."
            )

    def _toggle_pengaturan_minus(self) -> None:
        status_sekarang = cek_izinkan_stok_minus(self.conn)
        pesan_status = "DIIZINKAN" if status_sekarang else "DIBLOKIR (Direkomendasikan)"
        tanya = QMessageBox.question(
            self, "Pengaturan Stok Minus",
            f"Status izinkan stok minus saat ini: {pesan_status}\n\n"
            "Apakah Anda ingin mengubah pengaturan ini?\n"
            "(Jika diblokir, penjualan yang melebihi sisa stok akan ditolak sistem).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if tanya == QMessageBox.StandardButton.Yes:
            atur_izinkan_stok_minus(self.conn, not status_sekarang)
            status_baru = "DIIZINKAN" if not status_sekarang else "DIBLOKIR"
            QMessageBox.information(self, "Berhasil", f"Pengaturan stok minus telah diubah menjadi: {status_baru}")
            self.muat_data()
