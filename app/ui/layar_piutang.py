"""
app/ui/layar_piutang.py — Layar Pengelolaan Piutang Pembeli dan Pembayaran Otomatis FIFO.
Fitur:
- Daftar pembeli beserta total utang, nota tertua, dan status jatuh tempo.
- Rincian nota kredit per pembeli (Nomor nota, tanggal, total, terbayar, sisa, status).
- Tombol Besar "Terima Pembayaran Piutang" (otomatis dialokasikan ke nota tertua).
- Riwayat alokasi pembayaran piutang dan tombol pembatalan pembalik pembayaran.
- Realtime update via bus_sinyal.
"""
import sqlite3
from datetime import date
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDialog, QFormLayout, QSplitter, QGroupBox
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt

from app.db.repo_piutang import (
    ambil_daftar_ringkasan_piutang_pembeli, ambil_daftar_nota_kredit_pembeli,
    bayar_piutang_pembeli, balik_pembayaran_piutang, hitung_total_piutang_semua_pembeli
)
from app.util.format import format_rupiah, format_tanggal_indo
from app.ui.komponen.input_rupiah import InputRupiah
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global
from app.layanan.bus_sinyal import langganan, lepas_langganan


class DialogTerimaBayarPiutang(QDialog):
    """Dialog Penerimaan Pembayaran Piutang Pembeli."""

    def __init__(self, conn: sqlite3.Connection, pembeli_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.conn = conn
        self.pembeli = pembeli_data
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle(f"Terima Pembayaran Piutang - {self.pembeli['nama_pembeli']}")
        self.setMinimumWidth(500)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        sisa_utang = self.pembeli["sisa_piutang"]
        info = QLabel(
            f"<b>Pembeli:</b> {self.pembeli['nama_pembeli']}<br>"
            f"<b>Total Sisa Piutang:</b> <span style='color: #DC2626; font-size: 14pt; font-weight: bold;'>{format_rupiah(sisa_utang)}</span><br>"
            "<small style='color: #4B5563;'>Pembayaran akan dialokasikan secara otomatis ke nota kredit tertua terlebih dahulu.</small>",
            self
        )
        layout.addWidget(info)

        form = QFormLayout()
        form.setSpacing(12)

        self.input_nominal = InputRupiah(self)
        self.input_nominal.set_nilai(sisa_utang)
        self.input_nominal.setMinimumHeight(42)
        form.addRow("Nominal Pembayaran (Rp) *:", self.input_nominal)

        self.input_keterangan = QLineEdit(self)
        self.input_keterangan.setPlaceholderText("Keterangan (misal: Cicilan piutang / Pelunasan)")
        self.input_keterangan.setMinimumHeight(40)
        form.addRow("Keterangan:", self.input_keterangan)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_batal = QPushButton("Batal", self)
        btn_batal.setMinimumHeight(42)
        btn_batal.clicked.connect(self.reject)

        btn_simpan = QPushButton("Simpan Pembayaran (Masuk Kas)", self)
        btn_simpan.setMinimumHeight(42)
        btn_simpan.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; padding: 0 16px;")
        btn_simpan.clicked.connect(self._simpan)

        btn_box.addStretch()
        btn_box.addWidget(btn_batal)
        btn_box.addWidget(btn_simpan)
        layout.addLayout(btn_box)

    def _simpan(self) -> None:
        nom = self.input_nominal.ambil_nilai()
        if nom <= 0:
            QMessageBox.warning(self, "Perhatian", "Nominal pembayaran harus lebih dari Rp 0.")
            return

        tgl_ini = date.today().isoformat()
        ket = self.input_keterangan.text().strip()

        try:
            bayar_id, alokasi = bayar_piutang_pembeli(
                self.conn, self.pembeli["pembeli_id"], tgl_ini, nom, ket
            )
            rincian_str = "\n".join(f"- Nota {a['no_nota']}: {format_rupiah(a['jumlah_dialokasikan'])}" for a in alokasi)
            QMessageBox.information(
                self, "Pembayaran Berhasil",
                f"Pembayaran sebesar {format_rupiah(nom)} berhasil disimpan!\n\nAlokasi ke Nota:\n{rincian_str}"
            )
            self.accept()
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Tidak dapat menyimpan pembayaran: {err}")


class LayarPiutang(QWidget):
    """Layar Utama Pengelolaan Piutang Pembeli."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.daftar_pembeli: List[Dict[str, Any]] = []
        self._inisialisasi_ui()
        langganan("piutang_berubah", self.muat_data)

    def closeEvent(self, event):
        lepas_langganan("piutang_berubah", self.muat_data)
        super().closeEvent(event)

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(12)

        # Top Bar & Total Piutang
        top_bar = QHBoxLayout()
        self.lbl_total_piutang = QLabel("TOTAL PIUTANG TOKO: Rp 0", self)
        self.lbl_total_piutang.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.lbl_total_piutang.setStyleSheet("color: #DC2626;")
        top_bar.addWidget(self.lbl_total_piutang)

        top_bar.addStretch()

        self.input_cari = QLineEdit(self)
        self.input_cari.setPlaceholderText("Cari nama pembeli / no hp...")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.textChanged.connect(self.muat_data)
        top_bar.addWidget(self.input_cari)

        layout.addLayout(top_bar)

        # Splitter: Kiri Daftar Pembeli Berutang, Kanan Rincian Nota Kredit
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Panel Kiri (Daftar Pembeli)
        wadah_kiri = QWidget(splitter)
        lay_kiri = QVBoxLayout(wadah_kiri)
        lay_kiri.setContentsMargins(0, 0, 0, 0)

        lbl_kiri = QLabel("Daftar Pembeli yang Memiliki Utang:", wadah_kiri)
        lbl_kiri.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lay_kiri.addWidget(lbl_kiri)

        self.tabel_pembeli = QTableWidget(wadah_kiri)
        self.tabel_pembeli.setColumnCount(4)
        self.tabel_pembeli.setHorizontalHeaderLabels(["ID", "Nama Pembeli", "Sisa Piutang", "Status"])
        self.tabel_pembeli.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel_pembeli.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabel_pembeli.setColumnWidth(0, 50)   # ID
        self.tabel_pembeli.setColumnWidth(2, 130)  # Sisa Piutang
        self.tabel_pembeli.setColumnWidth(3, 110)  # Status
        terapkan_style_tabel_global(
            self.tabel_pembeli,
            rata_kanan_kolom=[2],
            kolom_status=3,
            kolom_sembunyi=[0]
        )
        self.tabel_pembeli.itemSelectionChanged.connect(self._on_pembeli_terpilih)
        lay_kiri.addWidget(self.tabel_pembeli)

        btn_bayar = QPushButton("Terima Pembayaran Piutang", wadah_kiri)
        btn_bayar.setMinimumHeight(42)
        btn_bayar.setStyleSheet("background-color: #10B981; color: white; font-weight: bold;")
        btn_bayar.clicked.connect(self._buka_dialog_bayar)
        lay_kiri.addWidget(btn_bayar)

        # Panel Kanan (Rincian Nota Kredit)
        wadah_kanan = QWidget(splitter)
        lay_kanan = QVBoxLayout(wadah_kanan)
        lay_kanan.setContentsMargins(0, 0, 0, 0)

        self.lbl_judul_kanan = QLabel("Rincian Nota Kredit:", wadah_kanan)
        self.lbl_judul_kanan.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        lay_kanan.addWidget(self.lbl_judul_kanan)

        self.tabel_nota = QTableWidget(wadah_kanan)
        self.tabel_nota.setColumnCount(6)
        self.tabel_nota.setHorizontalHeaderLabels([
            "No. Nota", "Tanggal", "Jatuh Tempo", "Total Nota", "Terbayar", "Sisa Tagihan"
        ])
        self.tabel_nota.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel_nota.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabel_nota.setColumnWidth(1, 105)  # Tanggal
        self.tabel_nota.setColumnWidth(2, 105)  # Jatuh Tempo
        self.tabel_nota.setColumnWidth(3, 120)  # Total Nota
        self.tabel_nota.setColumnWidth(4, 110)  # Terbayar
        self.tabel_nota.setColumnWidth(5, 120)  # Sisa Tagihan
        terapkan_style_tabel_global(
            self.tabel_nota,
            rata_kanan_kolom=[3, 4, 5]
        )
        lay_kanan.addWidget(self.tabel_nota)

        splitter.addWidget(wadah_kiri)
        splitter.addWidget(wadah_kanan)
        splitter.setSizes([450, 500])

        layout.addWidget(splitter)
        self.muat_data()

    def muat_data(self) -> None:
        tot_semua = hitung_total_piutang_semua_pembeli(self.conn)
        self.lbl_total_piutang.setText(f"TOTAL PIUTANG TOKO: {format_rupiah(tot_semua)}")

        kata = self.input_cari.text().strip().lower()
        semua_p = ambil_daftar_ringkasan_piutang_pembeli(self.conn, hanya_yang_punya_utang=True)
        if kata:
            semua_p = [p for p in semua_p if kata in p["nama_pembeli"].lower() or kata in (p["no_hp"] or "")]

        self.daftar_pembeli = semua_p
        self.tabel_pembeli.setRowCount(len(self.daftar_pembeli))

        for idx, p in enumerate(self.daftar_pembeli):
            self.tabel_pembeli.setItem(idx, 0, QTableWidgetItem(str(p["pembeli_id"])))

            nama_str = p["nama_pembeli"]
            if p.get("no_anggota"):
                nama_str += f" ({p['no_anggota']})"
            self.tabel_pembeli.setItem(idx, 1, QTableWidgetItem(nama_str))

            sisa_item = QTableWidgetItem(format_rupiah(p["sisa_piutang"]))
            sisa_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel_pembeli.setItem(idx, 2, sisa_item)

            st_item = QTableWidgetItem("Telat (Jatuh Tempo)" if p["lewat_jatuh_tempo"] else "Aktif")
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if p["lewat_jatuh_tempo"]:
                st_item.setForeground(Qt.GlobalColor.darkRed)
            else:
                st_item.setForeground(Qt.GlobalColor.darkGreen)
            self.tabel_pembeli.setItem(idx, 3, st_item)

        if not self.daftar_pembeli:
            self.tabel_nota.setRowCount(0)
            self.lbl_judul_kanan.setText("Rincian Nota Kredit: Tidak ada utang aktif.")

    def _on_pembeli_terpilih(self) -> None:
        baris = self.tabel_pembeli.currentRow()
        if baris < 0 or baris >= len(self.daftar_pembeli):
            return

        p = self.daftar_pembeli[baris]
        self.lbl_judul_kanan.setText(f"Rincian Nota Kredit: {p['nama_pembeli']} ({format_rupiah(p['sisa_piutang'])})")

        daftar_nota = ambil_daftar_nota_kredit_pembeli(self.conn, p["pembeli_id"])
        self.tabel_nota.setRowCount(len(daftar_nota))

        for idx, n in enumerate(daftar_nota):
            self.tabel_nota.setItem(idx, 0, QTableWidgetItem(n["no_nota"]))
            self.tabel_nota.setItem(idx, 1, QTableWidgetItem(format_tanggal_indo(n["tanggal"])))
            self.tabel_nota.setItem(idx, 2, QTableWidgetItem(format_tanggal_indo(n["jatuh_tempo"])))

            tot_item = QTableWidgetItem(format_rupiah(n["total"]))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel_nota.setItem(idx, 3, tot_item)

            byr_item = QTableWidgetItem(format_rupiah(n["terbayar"]))
            byr_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel_nota.setItem(idx, 4, byr_item)

            sisa_item = QTableWidgetItem(format_rupiah(n["sisa"]))
            sisa_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if n["sisa"] > 0:
                sisa_item.setForeground(Qt.GlobalColor.darkRed)
            self.tabel_nota.setItem(idx, 5, sisa_item)

    def _buka_dialog_bayar(self) -> None:
        baris = self.tabel_pembeli.currentRow()
        if baris < 0 or baris >= len(self.daftar_pembeli):
            QMessageBox.information(self, "Pilih Pembeli", "Silakan klik pembeli yang ingin membayar utang.")
            return

        p = self.daftar_pembeli[baris]
        dlg = DialogTerimaBayarPiutang(self.conn, p, parent=self)
        if dlg.exec():
            self.muat_data()
