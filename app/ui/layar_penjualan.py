"""
app/ui/layar_penjualan.py — Layar Kasir Cepat Penjualan Toko & Riwayat Nota.
Fitur Utama:
- Pencarian barang cepat instan (kode, nama, kata kunci), Enter langsung menambah ke keranjang belanja.
- Edit kuantitas dan satuan langsung pada tabel belanja, menampilkan konversi ("2 dus = 40 pcs").
- Info stok tersisa real-time dan peringatan stok kurang.
- Pilihan metode bayar: Tombol Besar TUNAI dan KREDIT.
- Untuk pembayaran tunai: kolom Uang Diterima & Kembalian (live calculation).
- Penjualan kredit mewajibkan pembeli terdaftar (bukan Umum).
- Riwayat nota penjualan dan dialog pembatalan (pembalik) dengan pengembalian stok ke lot asal.
"""
import sqlite3
from datetime import date
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QComboBox, QSpinBox,
    QGroupBox, QSplitter
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt

from app.db.repo_penjualan import (
    simpan_penjualan, ambil_daftar_penjualan, batalkan_nota_penjualan,
    ambil_harga_jual_default_barang, buat_nomor_nota_baru
)
from app.db.repo_barang import cari_barang, ambil_satuan_barang, ambil_barang_by_id
from app.db.repo_pihak import ambil_daftar_pihak, ambil_atau_buat_pembeli_umum
from app.layanan.layanan_stok import ambil_stok_barang
from app.util.format import format_rupiah, format_tanggal_indo
from app.ui.komponen.input_rupiah import InputRupiah
from app.layanan.bus_sinyal import langganan, lepas_langganan


class DialogKasirCepat(QDialog):
    """Dialog Layar Kasir Cepat Penjualan."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.keranjang: List[Dict[str, Any]] = []
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle("Kasir Toko - Penjualan Baru")
        self.resize(950, 680)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header Info Pembeli & Tanggal
        top_box = QHBoxLayout()
        top_box.setSpacing(10)

        lbl_pem = QLabel("Pembeli:", self)
        lbl_pem.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        top_box.addWidget(lbl_pem)

        self.combo_pembeli = QComboBox(self)
        self.combo_pembeli.setMinimumHeight(40)
        self._muat_pembeli()
        top_box.addWidget(self.combo_pembeli, stretch=2)

        self.input_nama_nota = QLineEdit(self)
        self.input_nama_nota.setPlaceholderText("Nama pembeli di nota (opsional jika Umum)")
        self.input_nama_nota.setMinimumHeight(40)
        top_box.addWidget(self.input_nama_nota, stretch=2)

        lbl_tgl = QLabel(f"Tanggal: {format_tanggal_indo(date.today().isoformat())}", self)
        lbl_tgl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_tgl.setStyleSheet("color: #1E3A8A; padding: 6px 12px; background-color: #EFF6FF; border-radius: 6px;")
        top_box.addWidget(lbl_tgl)

        layout.addLayout(top_box)

        # Input Pencarian Barang Cepat (Barcode / Nama / Alias)
        box_cari = QHBoxLayout()
        self.combo_cari_barang = QComboBox(self)
        self.combo_cari_barang.setMinimumHeight(42)
        self.combo_cari_barang.setPlaceholderText("Pilih atau cari barang... (Ketik nama / kode lalu tekan Enter)")
        self._muat_barang_dropdown()
        self.combo_cari_barang.currentIndexChanged.connect(self._on_barang_dipilih)
        box_cari.addWidget(self.combo_cari_barang, stretch=4)

        self.spin_qty_input = QSpinBox(self)
        self.spin_qty_input.setRange(1, 10000)
        self.spin_qty_input.setValue(1)
        self.spin_qty_input.setMinimumHeight(42)
        self.spin_qty_input.valueChanged.connect(self._update_preview_label)
        box_cari.addWidget(self.spin_qty_input, stretch=1)

        self.combo_satuan_input = QComboBox(self)
        self.combo_satuan_input.setMinimumHeight(42)
        self.combo_satuan_input.currentIndexChanged.connect(self._update_preview_label)
        box_cari.addWidget(self.combo_satuan_input, stretch=1)

        btn_tambah_item = QPushButton("+ Tambah", self)
        btn_tambah_item.setMinimumHeight(42)
        btn_tambah_item.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 0 16px;")
        btn_tambah_item.clicked.connect(self._tambah_ke_keranjang)
        box_cari.addWidget(btn_tambah_item)

        layout.addLayout(box_cari)

        # Label Preview Konversi & Stok Tersedia
        self.lbl_info_barang = QLabel("Pilih barang untuk melihat info stok dan konversi.", self)
        self.lbl_info_barang.setStyleSheet("color: #1D4ED8; font-weight: bold;")
        layout.addWidget(self.lbl_info_barang)

        # Tabel Keranjang Belanja
        self.tabel = QTableWidget(self)
        self.tabel.setColumnCount(6)
        self.tabel.setHorizontalHeaderLabels([
            "Barang", "Jumlah", "Satuan", "Total Satuan Dasar", "Harga Jual", "Subtotal"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(1, 100)  # Jumlah
        self.tabel.setColumnWidth(2, 90)   # Satuan
        self.tabel.setColumnWidth(3, 140)  # Total Satuan Dasar
        self.tabel.setColumnWidth(4, 130)  # Harga Jual
        self.tabel.setColumnWidth(5, 140)  # Subtotal
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setDefaultSectionSize(40)
        layout.addWidget(self.tabel)

        # Panel Bawah: Total, Pembayaran Tunai & Kredit
        panel_bawah = QHBoxLayout()

        btn_hapus_baris = QPushButton("Hapus Baris", self)
        btn_hapus_baris.setMinimumHeight(38)
        btn_hapus_baris.clicked.connect(self._hapus_baris_keranjang)
        panel_bawah.addWidget(btn_hapus_baris)

        panel_bawah.addStretch()

        # Kotak Total & Bayar
        lay_total = QVBoxLayout()
        self.lbl_grand_total = QLabel("TOTAL: Rp 0", self)
        self.lbl_grand_total.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.lbl_grand_total.setStyleSheet("color: #047857;")
        lay_total.addWidget(self.lbl_grand_total)

        # Input Uang Tunai Diterima & Kembalian
        box_tunai = QHBoxLayout()
        box_tunai.addWidget(QLabel("Diterima (Rp):", self))
        self.input_diterima = InputRupiah(self)
        self.input_diterima.setMinimumHeight(38)
        self.input_diterima.textChanged.connect(self._hitung_kembalian)
        box_tunai.addWidget(self.input_diterima)

        self.lbl_kembalian = QLabel("Kembalian: Rp 0", self)
        self.lbl_kembalian.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_kembalian.setStyleSheet("color: #2563EB; margin-left: 10px;")
        box_tunai.addWidget(self.lbl_kembalian)
        lay_total.addLayout(box_tunai)

        panel_bawah.addLayout(lay_total)
        layout.addLayout(panel_bawah)

        # Tombol Eksekusi Besar (TUNAI & KREDIT)
        tombol_bar = QHBoxLayout()
        tombol_bar.setSpacing(14)

        btn_batal = QPushButton("Batal", self)
        btn_batal.setMinimumHeight(52)
        btn_batal.clicked.connect(self.reject)
        tombol_bar.addWidget(btn_batal, stretch=1)

        self.btn_kredit = QPushButton("BAYAR KREDIT (NGUTANG)", self)
        self.btn_kredit.setMinimumHeight(52)
        self.btn_kredit.setStyleSheet("background-color: #D97706; color: white; font-size: 13pt; font-weight: bold; border-radius: 6px;")
        self.btn_kredit.clicked.connect(lambda: self._eksekusi_penjualan("kredit"))
        tombol_bar.addWidget(self.btn_kredit, stretch=2)

        self.btn_tunai = QPushButton("BAYAR TUNAI", self)
        self.btn_tunai.setMinimumHeight(52)
        self.btn_tunai.setStyleSheet("background-color: #10B981; color: white; font-size: 14pt; font-weight: bold; border-radius: 6px;")
        self.btn_tunai.clicked.connect(lambda: self._eksekusi_penjualan("tunai"))
        tombol_bar.addWidget(self.btn_tunai, stretch=3)

        layout.addLayout(tombol_bar)

    def _muat_pembeli(self) -> None:
        self.combo_pembeli.clear()
        pembelis = ambil_daftar_pihak(self.conn, "pembeli", hanya_aktif=True)
        id_umum = ambil_atau_buat_pembeli_umum(self.conn)
        idx_to_select = 0
        for i, p in enumerate(pembelis):
            label = p["nama"]
            if p.get("no_anggota"):
                label += f" ({p['no_anggota']})"
            self.combo_pembeli.addItem(label, p["id"])
            if p["id"] == id_umum:
                idx_to_select = i
        self.combo_pembeli.setCurrentIndex(idx_to_select)

    def _muat_barang_dropdown(self) -> None:
        self.combo_cari_barang.clear()
        self.combo_cari_barang.addItem("-- Pilih Barang --", None)
        semua_b = cari_barang(self.conn, "", hanya_aktif=True, limit=500)
        for b in semua_b:
            label = f"{b['kode']} - {b['nama']}"
            if b["jenis_kepemilikan"] == "titipan":
                label += f" (Titipan: {b.get('nama_penitip') or 'Penitip'})"
            self.combo_cari_barang.addItem(label, b["id"])

    def _on_barang_dipilih(self) -> None:
        b_id = self.combo_cari_barang.currentData()
        self.combo_satuan_input.clear()
        if not b_id:
            self.lbl_info_barang.setText("Pilih barang untuk melihat info stok dan konversi.")
            return

        sats = ambil_satuan_barang(self.conn, b_id)
        for s in sats:
            self.combo_satuan_input.addItem(s["nama_satuan"], s["isi_dalam_satuan_dasar"])
        self._update_preview_label()

    def _update_preview_label(self) -> None:
        b_id = self.combo_cari_barang.currentData()
        if not b_id:
            return

        b = ambil_barang_by_id(self.conn, b_id)
        stok_ada = ambil_stok_barang(self.conn, b_id)
        jml = self.spin_qty_input.value()
        sat_nama = self.combo_satuan_input.currentText()
        isi = self.combo_satuan_input.currentData() or 1
        tot_dasar = jml * isi

        hrg_def = ambil_harga_jual_default_barang(self.conn, b_id)
        subtotal = tot_dasar * hrg_def

        stok_warna = "#059669" if stok_ada >= tot_dasar else "#DC2626"
        self.lbl_info_barang.setText(
            f"Konversi: <b>{jml} {sat_nama} = {tot_dasar} {b['satuan_dasar']}</b> | "
            f"Harga Jual: <b>{format_rupiah(hrg_def)}/{b['satuan_dasar']}</b> | "
            f"Subtotal: <b>{format_rupiah(subtotal)}</b> | "
            f"Stok Tersedia: <b style='color: {stok_warna};'>{stok_ada} {b['satuan_dasar']}</b>"
        )

    def _tambah_ke_keranjang(self) -> None:
        b_id = self.combo_cari_barang.currentData()
        if not b_id:
            QMessageBox.warning(self, "Perhatian", "Silakan pilih barang terlebih dahulu.")
            return

        b = ambil_barang_by_id(self.conn, b_id)
        stok_ada = ambil_stok_barang(self.conn, b_id)
        jml = self.spin_qty_input.value()
        sat_nama = self.combo_satuan_input.currentText()
        isi = self.combo_satuan_input.currentData() or 1
        tot_dasar = jml * isi

        if stok_ada < tot_dasar:
            tanya = QMessageBox.question(
                self, "Peringatan Stok Kurang",
                f"Stok barang '{b['nama']}' tersisa {stok_ada} {b['satuan_dasar']}, sedangkan input: {tot_dasar} {b['satuan_dasar']}.\n\nTetap tambahkan ke keranjang?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if tanya != QMessageBox.StandardButton.Yes:
                return

        hrg_def = ambil_harga_jual_default_barang(self.conn, b_id)

        item = {
            "barang_id": b_id,
            "nama_barang": b["nama"],
            "kode_barang": b["kode"],
            "satuan_dasar": b["satuan_dasar"],
            "jumlah_input": jml,
            "satuan_input": sat_nama,
            "isi_per_satuan": isi,
            "jumlah_dasar": tot_dasar,
            "harga_jual_satuan_dasar": hrg_def,
            "total_baris": tot_dasar * hrg_def
        }
        self.keranjang.append(item)
        self._refresh_tabel()

        # Reset input
        self.spin_qty_input.setValue(1)
        self.combo_cari_barang.setCurrentIndex(0)
        self.combo_cari_barang.setFocus()

    def _refresh_tabel(self) -> None:
        self.tabel.setRowCount(len(self.keranjang))
        total = 0
        for r_idx, it in enumerate(self.keranjang):
            total += it["total_baris"]
            self.tabel.setItem(r_idx, 0, QTableWidgetItem(f"{it['kode_barang']} - {it['nama_barang']}"))
            self.tabel.setItem(r_idx, 1, QTableWidgetItem(str(it["jumlah_input"])))
            self.tabel.setItem(r_idx, 2, QTableWidgetItem(it["satuan_input"]))
            self.tabel.setItem(r_idx, 3, QTableWidgetItem(f"{it['jumlah_dasar']} {it['satuan_dasar']}"))

            hrg_item = QTableWidgetItem(format_rupiah(it["harga_jual_satuan_dasar"]))
            hrg_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(r_idx, 4, hrg_item)

            tot_item = QTableWidgetItem(format_rupiah(it["total_baris"]))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(r_idx, 5, tot_item)

        self.lbl_grand_total.setText(f"TOTAL: {format_rupiah(total)}")
        self._hitung_kembalian()

    def _hitung_kembalian(self) -> None:
        total = sum(it["total_baris"] for it in self.keranjang)
        diterima = self.input_diterima.ambil_nilai()
        if diterima >= total and total > 0:
            kembali = diterima - total
            self.lbl_kembalian.setText(f"Kembalian: {format_rupiah(kembali)}")
            self.lbl_kembalian.setStyleSheet("color: #059669; font-weight: bold; margin-left: 10px;")
        else:
            self.lbl_kembalian.setText("Kembalian: Rp 0")
            self.lbl_kembalian.setStyleSheet("color: #6B7280; margin-left: 10px;")

    def _hapus_baris_keranjang(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.keranjang):
            return
        self.keranjang.pop(baris)
        self._refresh_tabel()

    def _eksekusi_penjualan(self, metode: str) -> None:
        if not self.keranjang:
            QMessageBox.warning(self, "Perhatian", "Keranjang belanja masih kosong.")
            return

        pembeli_id = self.combo_pembeli.currentData()
        nama_pembeli_str = self.combo_pembeli.currentText()
        nama_nota = self.input_nama_nota.text().strip()

        if metode == "kredit":
            if "Umum" in nama_pembeli_str:
                QMessageBox.warning(
                    self, "Penjualan Kredit Ditolak",
                    "Penjualan KREDIT (ngutang) wajib memilih pembeli terdaftar, bukan 'Umum'."
                )
                self.combo_pembeli.setFocus()
                return

        total_belanja = sum(it["total_baris"] for it in self.keranjang)
        diterima = self.input_diterima.ambil_nilai()

        if metode == "tunai" and diterima > 0 and diterima < total_belanja:
            tanya = QMessageBox.question(
                self, "Uang Kurang",
                f"Uang diterima ({format_rupiah(diterima)}) lebih kecil dari total belanja ({format_rupiah(total_belanja)}).\n\nTetap simpan transaksi tunai?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if tanya != QMessageBox.StandardButton.Yes:
                return

        try:
            pj_id, no_nota = simpan_penjualan(
                conn=self.conn,
                tanggal=date.today().isoformat(),
                pembeli_id=pembeli_id,
                metode_bayar=metode,
                items=self.keranjang,
                nama_pembeli_nota=nama_nota
            )
            pesan_sukses = f"Transaksi Penjualan Berhasil Disimpan!\n\nNomor Nota: {no_nota}\nMetode: {metode.upper()}\nTotal: {format_rupiah(total_belanja)}"
            if metode == "tunai" and diterima >= total_belanja:
                pesan_sukses += f"\nKembalian: {format_rupiah(diterima - total_belanja)}"
            QMessageBox.information(self, "Sukses", pesan_sukses)
            self.accept()
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Tidak dapat menyimpan penjualan: {err}")


class LayarPenjualan(QWidget):
    """Layar Utama Penjualan dan Riwayat Nota."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.daftar_penjualan: List[Dict[str, Any]] = []
        self._inisialisasi_ui()
        langganan("penjualan_berubah", self.muat_data)

    def closeEvent(self, event):
        lepas_langganan("penjualan_berubah", self.muat_data)
        super().closeEvent(event)

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(12)

        # Header dan Pencarian
        top_bar = QHBoxLayout()
        lbl_cari = QLabel("Cari Nota / Pembeli:", self)
        lbl_cari.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        top_bar.addWidget(lbl_cari)

        self.input_cari = QLineEdit(self)
        self.input_cari.setPlaceholderText("Ketik nomor nota atau nama pembeli...")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.textChanged.connect(self.muat_data)
        top_bar.addWidget(self.input_cari)

        btn_kasir = QPushButton("+ Kasir Penjualan Baru", self)
        btn_kasir.setMinimumHeight(40)
        btn_kasir.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; padding: 0 16px;")
        btn_kasir.clicked.connect(self._buka_kasir)
        top_bar.addWidget(btn_kasir)

        layout.addLayout(top_bar)

        # Tabel Riwayat Nota
        self.tabel = QTableWidget(self)
        self.tabel.setColumnCount(8)
        self.tabel.setHorizontalHeaderLabels([
            "ID", "Tanggal", "No. Nota", "Pembeli", "Metode Bayar",
            "Total", "Status Pembayaran", "Status Efektif"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 50)   # ID
        self.tabel.setColumnWidth(1, 115)  # Tanggal
        self.tabel.setColumnWidth(2, 130)  # No. Nota
        self.tabel.setColumnWidth(4, 120)  # Metode Bayar
        self.tabel.setColumnWidth(5, 140)  # Total
        self.tabel.setColumnWidth(6, 140)  # Status Pembayaran
        self.tabel.setColumnWidth(7, 110)  # Status Efektif
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setDefaultSectionSize(40)
        layout.addWidget(self.tabel)

        # Bar Tombol Bawah
        bot_bar = QHBoxLayout()
        btn_batal = QPushButton("Batalkan Nota (Pembalik)", self)
        btn_batal.setMinimumHeight(42)
        btn_batal.clicked.connect(self._batalkan_nota)
        bot_bar.addWidget(btn_batal)

        bot_bar.addStretch()
        layout.addLayout(bot_bar)

        self.muat_data()

    def muat_data(self) -> None:
        k = self.input_cari.text().strip()
        self.daftar_penjualan = ambil_daftar_penjualan(self.conn, kata_kunci=k, limit=150)
        self.tabel.setRowCount(len(self.daftar_penjualan))

        for idx, pj in enumerate(self.daftar_penjualan):
            self.tabel.setItem(idx, 0, QTableWidgetItem(str(pj["id"])))
            self.tabel.setItem(idx, 1, QTableWidgetItem(format_tanggal_indo(pj["tanggal"])))
            self.tabel.setItem(idx, 2, QTableWidgetItem(pj["no_nota"]))

            nama_pem = pj["nama_pembeli"]
            if pj.get("nama_pembeli_nota"):
                nama_pem += f" ({pj['nama_pembeli_nota']})"
            self.tabel.setItem(idx, 3, QTableWidgetItem(nama_pem))

            metode_str = pj["metode_bayar"].upper()
            self.tabel.setItem(idx, 4, QTableWidgetItem(metode_str))

            tot_item = QTableWidgetItem(format_rupiah(pj["total"]))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(idx, 5, tot_item)

            st_item = QTableWidgetItem(pj["status_bayar_info"])
            if "Lewat" in pj["status_bayar_info"]:
                st_item.setForeground(Qt.GlobalColor.darkRed)
            elif "Lunas" in pj["status_bayar_info"]:
                st_item.setForeground(Qt.GlobalColor.darkGreen)
            self.tabel.setItem(idx, 6, st_item)

            efek_str = pj.get("status_efektif", "NORMAL")
            efek_item = QTableWidgetItem(efek_str)
            efek_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if efek_str == "DIBATALKAN":
                efek_item.setForeground(Qt.GlobalColor.gray)
            elif efek_str == "PEMBALIK":
                efek_item.setForeground(Qt.GlobalColor.darkRed)
            self.tabel.setItem(idx, 7, efek_item)

    def _buka_kasir(self) -> None:
        dlg = DialogKasirCepat(self.conn, parent=self)
        if dlg.exec():
            self.muat_data()

    def _batalkan_nota(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_penjualan):
            QMessageBox.information(self, "Pilih Nota", "Silakan klik baris nota yang ingin dibatalkan.")
            return

        pj = self.daftar_penjualan[baris]
        if pj.get("status_efektif") != "NORMAL":
            QMessageBox.warning(self, "Perhatian", "Hanya nota dengan status NORMAL yang dapat dibatalkan.")
            return

        tanya = QMessageBox.question(
            self, "Konfirmasi Pembatalan Nota",
            f"Apakah Anda yakin ingin membatalkan Nota {pj['no_nota']}?\n\n"
            "Stok akan dikembalikan ke lot asal dan kas/piutang akan dibalik.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if tanya == QMessageBox.StandardButton.Yes:
            tgl_ini = date.today().isoformat()
            try:
                batalkan_nota_penjualan(self.conn, pj["id"], tgl_ini, "Pembatalan oleh kasir")
                QMessageBox.information(self, "Berhasil", f"Nota {pj['no_nota']} berhasil dibatalkan!")
                self.muat_data()
            except Exception as err:
                QMessageBox.critical(self, "Gagal Membatalkan", str(err))
