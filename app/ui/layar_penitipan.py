"""
app/ui/layar_penitipan.py — Layar Penitipan Harian dan Setoran Sore Penitip.
Fitur:
- Tab 1: Penerimaan Penitipan Baru (Pagi Hari) dengan input harga titip & harga jual fleksibel per barang.
- Tab 2: Setoran Sore Hari:
  * Memilih penitip.
  * Tampil daftar barang dititip, terjual, sisa, harga titip, dan total yang harus dibayar.
  * Pilihan sisa barang dikembalikan (retur) atau ditinggal.
  * Satu Tombol "Bayar dan Ambil Sisa": memotong kas toko, mencatat retur stok, dan mengunci baris tuntas.
  * Peringatan ramah jika kas toko tidak cukup (kas boleh minus dengan konfirmasi).
"""
import sqlite3
from datetime import date
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QComboBox, QSpinBox,
    QTabWidget, QGroupBox, QRadioButton, QButtonGroup
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt

from app.db.repo_penitipan import (
    catat_penitipan_harian, ambil_daftar_titipan_aktif_penitip,
    selesaikan_setoran_penitip, hitung_total_hutang_penitip_terkini
)
from app.db.repo_pihak import ambil_daftar_pihak
from app.db.repo_barang import cari_barang, ambil_satuan_barang, ambil_barang_by_id
from app.db.repo_kas_toko import hitung_saldo_kas_toko
from app.util.format import format_rupiah, format_tanggal_indo
from app.ui.komponen.input_rupiah import InputRupiah
from app.layanan.bus_sinyal import langganan, lepas_langganan


class DialogInputPenitipanPagi(QDialog):
    """Dialog Input Penerimaan Barang Titipan Baru (Pagi Hari)."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.items_titip: List[Dict[str, Any]] = []
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle("Input Penerimaan Titipan Baru (Pagi)")
        self.resize(800, 560)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header Info Penitip
        top_box = QHBoxLayout()
        top_box.addWidget(QLabel("Penitip Barang *:", self))
        self.combo_penitip = QComboBox(self)
        self.combo_penitip.setMinimumHeight(40)
        self._muat_penitip()
        self.combo_penitip.currentIndexChanged.connect(self._on_penitip_changed)
        top_box.addWidget(self.combo_penitip, stretch=2)

        lbl_tgl = QLabel(f"Tanggal: {format_tanggal_indo(date.today().isoformat())}", self)
        lbl_tgl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lbl_tgl.setStyleSheet("color: #1E3A8A; padding: 6px 12px; background-color: #EFF6FF; border-radius: 6px;")
        top_box.addWidget(lbl_tgl)
        layout.addLayout(top_box)

        # Form Tambah Baris Barang Titipan
        grp_input = QGroupBox("Tambah Barang Titipan", self)
        lay_in = QVBoxLayout(grp_input)

        row1 = QHBoxLayout()
        self.combo_barang = QComboBox(self)
        self.combo_barang.setMinimumHeight(40)
        self.combo_barang.currentIndexChanged.connect(self._on_barang_changed)
        row1.addWidget(self.combo_barang, stretch=3)

        self.spin_jumlah = QSpinBox(self)
        self.spin_jumlah.setRange(1, 10000)
        self.spin_jumlah.setValue(10)
        self.spin_jumlah.setMinimumHeight(40)
        row1.addWidget(self.spin_jumlah, stretch=1)

        self.combo_satuan = QComboBox(self)
        self.combo_satuan.setMinimumHeight(40)
        row1.addWidget(self.combo_satuan, stretch=1)
        lay_in.addLayout(row1)

        row2 = QHBoxLayout()
        self.input_harga_titip = InputRupiah(self)
        self.input_harga_titip.setPlaceholderText("Harga Titip (Modal)")
        self.input_harga_titip.setMinimumHeight(40)
        row2.addWidget(QLabel("Harga Titip (Rp):", self))
        row2.addWidget(self.input_harga_titip, stretch=2)

        self.input_harga_jual = InputRupiah(self)
        self.input_harga_jual.setPlaceholderText("Harga Jual Konsumen")
        self.input_harga_jual.setMinimumHeight(40)
        row2.addWidget(QLabel("Harga Jual (Rp):", self))
        row2.addWidget(self.input_harga_jual, stretch=2)

        btn_tambah = QPushButton("+ Tambah", self)
        btn_tambah.setMinimumHeight(40)
        btn_tambah.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 0 16px;")
        btn_tambah.clicked.connect(self._tambah_ke_tabel)
        row2.addWidget(btn_tambah)
        lay_in.addLayout(row2)

        layout.addWidget(grp_input)

        # Tabel Baris Titipan
        self.tabel = QTableWidget(self)
        self.tabel.setColumnCount(5)
        self.tabel.setHorizontalHeaderLabels([
            "Barang", "Jumlah Titip", "Satuan", "Harga Titip (Dasar)", "Harga Jual (Dasar)"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(1, 110)  # Jumlah Titip
        self.tabel.setColumnWidth(2, 90)   # Satuan
        self.tabel.setColumnWidth(3, 140)  # Harga Titip
        self.tabel.setColumnWidth(4, 140)  # Harga Jual
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.tabel)

        # Tombol Bawah
        bot_bar = QHBoxLayout()
        btn_hapus = QPushButton("Hapus Baris", self)
        btn_hapus.clicked.connect(self._hapus_baris)
        bot_bar.addWidget(btn_hapus)

        bot_bar.addStretch()

        btn_batal = QPushButton("Batal", self)
        btn_batal.setMinimumHeight(42)
        btn_batal.clicked.connect(self.reject)
        bot_bar.addWidget(btn_batal)

        btn_simpan = QPushButton("Simpan Penerimaan Titipan", self)
        btn_simpan.setMinimumHeight(42)
        btn_simpan.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; padding: 0 16px;")
        btn_simpan.clicked.connect(self._simpan)
        bot_bar.addWidget(btn_simpan)

        layout.addLayout(bot_bar)
        self._on_penitip_changed()

    def _muat_penitip(self) -> None:
        self.combo_penitip.clear()
        penitips = ambil_daftar_pihak(self.conn, "penitip", hanya_aktif=True)
        for p in penitips:
            self.combo_penitip.addItem(p["nama"], p["id"])

    def _on_penitip_changed(self) -> None:
        p_id = self.combo_penitip.currentData()
        self.combo_barang.clear()
        if not p_id:
            return

        # Hanya tampilkan barang titipan yang terikat ke penitip ini
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, kode, nama FROM barang WHERE jenis_kepemilikan = 'titipan' AND penitip_id = ? AND aktif = 1;",
            (p_id,)
        )
        for r in cur.fetchall():
            self.combo_barang.addItem(f"{r['kode']} - {r['nama']}", r["id"])

    def _on_barang_changed(self) -> None:
        b_id = self.combo_barang.currentData()
        self.combo_satuan.clear()
        if not b_id:
            return

        sats = ambil_satuan_barang(self.conn, b_id)
        for s in sats:
            self.combo_satuan.addItem(s["nama_satuan"], s["isi_dalam_satuan_dasar"])

    def _tambah_ke_tabel(self) -> None:
        b_id = self.combo_barang.currentData()
        if not b_id:
            QMessageBox.warning(self, "Perhatian", "Silakan pilih barang titipan.")
            return

        b = ambil_barang_by_id(self.conn, b_id)
        jml = self.spin_jumlah.value()
        sat_nama = self.combo_satuan.currentText()
        isi = self.combo_satuan.currentData() or 1
        hrg_titip = self.input_harga_titip.ambil_nilai()
        hrg_jual = self.input_harga_jual.ambil_nilai()

        if hrg_titip < 0 or hrg_jual < 0:
            QMessageBox.warning(self, "Perhatian", "Harga titip dan harga jual tidak boleh negatif.")
            return

        item = {
            "barang_id": b_id,
            "nama_barang": b["nama"],
            "kode_barang": b["kode"],
            "jumlah_input": jml,
            "satuan_input": sat_nama,
            "isi_per_satuan": isi,
            "harga_titip_satuan_dasar": hrg_titip,
            "harga_jual_satuan_dasar": hrg_jual
        }
        self.items_titip.append(item)
        self._refresh_tabel()

    def _refresh_tabel(self) -> None:
        self.tabel.setRowCount(len(self.items_titip))
        for r_idx, it in enumerate(self.items_titip):
            self.tabel.setItem(r_idx, 0, QTableWidgetItem(f"{it['kode_barang']} - {it['nama_barang']}"))
            self.tabel.setItem(r_idx, 1, QTableWidgetItem(str(it["jumlah_input"])))
            self.tabel.setItem(r_idx, 2, QTableWidgetItem(it["satuan_input"]))

            ht_item = QTableWidgetItem(format_rupiah(it["harga_titip_satuan_dasar"]))
            ht_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(r_idx, 3, ht_item)

            hj_item = QTableWidgetItem(format_rupiah(it["harga_jual_satuan_dasar"]))
            hj_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(r_idx, 4, hj_item)

    def _hapus_baris(self) -> None:
        b = self.tabel.currentRow()
        if b < 0 or b >= len(self.items_titip):
            return
        self.items_titip.pop(b)
        self._refresh_tabel()

    def _simpan(self) -> None:
        p_id = self.combo_penitip.currentData()
        if not p_id or not self.items_titip:
            QMessageBox.warning(self, "Perhatian", "Pilih penitip dan masukkan minimal 1 barang titipan.")
            return

        try:
            catat_penitipan_harian(
                self.conn, p_id, date.today().isoformat(), self.items_titip
            )
            QMessageBox.information(self, "Berhasil", "Penitipan barang harian berhasil dicatat ke stok!")
            self.accept()
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Tidak dapat menyimpan penitipan: {err}")


class LayarPenitipan(QWidget):
    """Layar Pengelolaan Penitipan dan Setoran Sore Hari."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.daftar_baris_titip: List[Dict[str, Any]] = []
        self._inisialisasi_ui()
        langganan("penitipan_berubah", self.muat_data)
        langganan("stok_berubah", self.muat_data)

    def closeEvent(self, event):
        lepas_langganan("penitipan_berubah", self.muat_data)
        lepas_langganan("stok_berubah", self.muat_data)
        super().closeEvent(event)

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(12)

        # Header Info & Tombol Input Pagi
        top_bar = QHBoxLayout()
        lbl_penitip = QLabel("Pilih Penitip:", self)
        lbl_penitip.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        top_bar.addWidget(lbl_penitip)

        self.combo_penitip_aktif = QComboBox(self)
        self.combo_penitip_aktif.setMinimumHeight(40)
        self._muat_penitip_filter()
        self.combo_penitip_aktif.currentIndexChanged.connect(self.muat_data)
        top_bar.addWidget(self.combo_penitip_aktif, stretch=2)

        top_bar.addStretch()

        btn_input_pagi = QPushButton("+ Input Penitipan Pagi", self)
        btn_input_pagi.setMinimumHeight(40)
        btn_input_pagi.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 0 16px;")
        btn_input_pagi.clicked.connect(self._buka_input_pagi)
        top_bar.addWidget(btn_input_pagi)

        layout.addLayout(top_bar)

        # Tabel Barang Titipan Aktif Sore Hari
        self.tabel = QTableWidget(self)
        self.tabel.setColumnCount(7)
        self.tabel.setHorizontalHeaderLabels([
            "Tanggal", "Barang Titipan", "Dititip", "Terjual (Laku)",
            "Sisa Stok", "Harga Titip", "Total Bayar"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 115)  # Tanggal
        self.tabel.setColumnWidth(2, 95)   # Dititip
        self.tabel.setColumnWidth(3, 115)  # Terjual
        self.tabel.setColumnWidth(4, 95)   # Sisa Stok
        self.tabel.setColumnWidth(5, 120)  # Harga Titip
        self.tabel.setColumnWidth(6, 130)  # Total Bayar
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.verticalHeader().setDefaultSectionSize(40)
        layout.addWidget(self.tabel)

        # Panel Setoran Sore Hari
        grp_setoran = QGroupBox("Penyelesaian Setoran Sore Hari", self)
        lay_setor = QVBoxLayout(grp_setoran)
        lay_setor.setSpacing(10)

        # Opsi Sisa Barang: Retur vs Ditinggal
        box_opsi = QHBoxLayout()
        box_opsi.addWidget(QLabel("Perlakuan Sisa Barang:", self))

        self.radio_retur = QRadioButton("Kembalikan Semua Sisa Barang ke Penitip (Retur Stok)", self)
        self.radio_retur.setChecked(True)
        box_opsi.addWidget(self.radio_retur)

        self.radio_tinggal = QRadioButton("Sisa Barang Tetap Ditinggal di Toko (Dijual Besok)", self)
        box_opsi.addWidget(self.radio_tinggal)
        box_opsi.addStretch()
        lay_setor.addLayout(box_opsi)

        # Total Bayar & Tombol Eksekusi
        bar_aksi = QHBoxLayout()
        self.lbl_total_harus_bayar = QLabel("Total Laku yang Harus Dibayar: Rp 0", self)
        self.lbl_total_harus_bayar.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_total_harus_bayar.setStyleSheet("color: #DC2626;")
        bar_aksi.addWidget(self.lbl_total_harus_bayar)

        bar_aksi.addStretch()

        self.btn_bayar_dan_ambil = QPushButton("Bayar dan Ambil Sisa", self)
        self.btn_bayar_dan_ambil.setMinimumHeight(48)
        self.btn_bayar_dan_ambil.setStyleSheet("background-color: #10B981; color: white; font-size: 13pt; font-weight: bold; padding: 0 20px; border-radius: 6px;")
        self.btn_bayar_dan_ambil.clicked.connect(self._eksekusi_setoran)
        bar_aksi.addWidget(self.btn_bayar_dan_ambil)

        lay_setor.addLayout(bar_aksi)
        layout.addWidget(grp_setoran)

        self.muat_data()

    def _muat_penitip_filter(self) -> None:
        self.combo_penitip_aktif.clear()
        penitips = ambil_daftar_pihak(self.conn, "penitip", hanya_aktif=True)
        for p in penitips:
            self.combo_penitip_aktif.addItem(p["nama"], p["id"])

    def muat_data(self) -> None:
        p_id = self.combo_penitip_aktif.currentData()
        if not p_id:
            self.tabel.setRowCount(0)
            self.lbl_total_harus_bayar.setText("Total Laku yang Harus Dibayar: Rp 0")
            return

        self.daftar_baris_titip = ambil_daftar_titipan_aktif_penitip(self.conn, p_id)
        self.tabel.setRowCount(len(self.daftar_baris_titip))

        total_bayar_semua = 0

        for idx, row in enumerate(self.daftar_baris_titip):
            total_bayar_semua += row["subtotal_bayar"]

            self.tabel.setItem(idx, 0, QTableWidgetItem(format_tanggal_indo(row["tanggal"])))
            self.tabel.setItem(idx, 1, QTableWidgetItem(f"{row['kode_barang']} - {row['nama_barang']}"))

            # Dititip
            item_awal = QTableWidgetItem(f"{row['qty_awal']} {row['satuan_dasar']}")
            item_awal.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabel.setItem(idx, 2, item_awal)

            # Terjual
            item_laku = QTableWidgetItem(f"{row['qty_terjual']} {row['satuan_dasar']}")
            item_laku.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if row["qty_terjual"] > 0:
                item_laku.setForeground(Qt.GlobalColor.darkGreen)
            self.tabel.setItem(idx, 3, item_laku)

            # Sisa
            item_sisa = QTableWidgetItem(f"{row['qty_sisa']} {row['satuan_dasar']}")
            item_sisa.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tabel.setItem(idx, 4, item_sisa)

            # Harga Titip
            ht_item = QTableWidgetItem(format_rupiah(row["harga_titip_satuan_dasar"]))
            ht_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(idx, 5, ht_item)

            # Subtotal Bayar
            tot_item = QTableWidgetItem(format_rupiah(row["subtotal_bayar"]))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(idx, 6, tot_item)

        self.lbl_total_harus_bayar.setText(f"Total Laku yang Harus Dibayar: {format_rupiah(total_bayar_semua)}")

    def _buka_input_pagi(self) -> None:
        dlg = DialogInputPenitipanPagi(self.conn, parent=self)
        if dlg.exec():
            self._muat_penitip_filter()
            self.muat_data()

    def _eksekusi_setoran(self) -> None:
        p_id = self.combo_penitip_aktif.currentData()
        if not p_id or not self.daftar_baris_titip:
            QMessageBox.information(self, "Informasi", "Tidak ada barang titipan aktif yang harus diselesaikan.")
            return

        total_bayar = sum(r["subtotal_bayar"] for r in self.daftar_baris_titip)
        saldo_kas = hitung_saldo_kas_toko(self.conn)

        # Peringatan jika kas toko tidak cukup
        if total_bayar > saldo_kas:
            tanya_kas = QMessageBox.question(
                self, "Kas Toko Kurang",
                f"Saldo kas toko saat ini ({format_rupiah(saldo_kas)}) tidak mencukupi untuk membayar penitip ({format_rupiah(total_bayar)}).\n\n"
                "Sistem memperbolehkan kas toko minus untuk kelancaran operasional toko.\n"
                "Apakah Anda ingin melanjutkan pembayaran?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if tanya_kas != QMessageBox.StandardButton.Yes:
                return

        aksi_sisa = "retur" if self.radio_retur.isChecked() else "tinggal"
        rincian = []
        for r in self.daftar_baris_titip:
            rincian.append({
                "penitipan_baris_id": r["penitipan_baris_id"],
                "lot_id": r["lot_id"],
                "qty_terjual": r["qty_terjual"],
                "harga_titip": r["harga_titip_satuan_dasar"],
                "sisa_aksi": aksi_sisa
            })

        tanya = QMessageBox.question(
            self, "Konfirmasi Setoran Penitip",
            f"Selesaikan setoran sore untuk {self.combo_penitip_aktif.currentText()}?\n\n"
            f"- Total Dibayar: {format_rupiah(total_bayar)}\n"
            f"- Sisa Barang: {'Dikembalikan (Retur)' if aksi_sisa == 'retur' else 'Tetap Ditinggal di Toko'}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if tanya == QMessageBox.StandardButton.Yes:
            try:
                selesaikan_setoran_penitip(
                    self.conn, p_id, date.today().isoformat(), rincian, nominal_bayar=total_bayar
                )
                QMessageBox.information(self, "Sukses", "Setoran sore penitip berhasil diselesaikan!")
                self.muat_data()
            except Exception as err:
                QMessageBox.critical(self, "Gagal", f"Gagal memproses setoran: {err}")
