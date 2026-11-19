"""
app/ui/layar_opname_toko.py — Layar Stock Opname Unit Toko:
1. Pembuatan Sesi Opname (Draft)
2. Input Cepat Keyboard Stok Fisik per Barang dengan Kalkulasi Selisih & Nilai
3. Auto-save Draft
4. Finalisasi Opname (konfirmasi dampak, selisih kurang -> rugi FIFO, selisih lebih -> lot baru)
5. Riwayat Sesi Opname & Laporan Selisih
"""
import sqlite3
from typing import Optional, Callable, Dict, Any, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDateEdit,
    QLineEdit, QMessageBox, QDialog, QSplitter, QFrame
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, QDate

from app.db.repo_opname_toko import (
    buat_sesi_opname, simpan_baris_opname_draft, ambil_daftar_opname_barang, finalisasi_sesi_opname
)
from app.db.repo_barang import ambil_daftar_barang
from app.util.format import format_rupiah, format_tanggal_indo
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global


class LayarOpnameToko(QWidget):
    """Layar Stock Opname Bulanan / Berkala."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.sesi_aktif_id: Optional[int] = None
        self._inisialisasi_ui()

    def _inisialisasi_ui(self):
        self.setFont(QFont("Segoe UI", 11))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 15)
        layout.setSpacing(12)

        # Header
        top_bar = QHBoxLayout()
        lbl_judul = QLabel("Stock Opname Unit Toko", self)
        lbl_judul.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        lbl_judul.setStyleSheet("color: #1E3A8A;")
        top_bar.addWidget(lbl_judul)

        top_bar.addStretch()

        self.btn_buat_sesi = QPushButton("+ Buat Sesi Opname Baru", self)
        self.btn_buat_sesi.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_buat_sesi.clicked.connect(self._buat_sesi_baru)
        top_bar.addWidget(self.btn_buat_sesi)

        self.btn_finalkan = QPushButton("Finalisasi Opname", self)
        self.btn_finalkan.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; padding: 6px 14px;")
        self.btn_finalkan.clicked.connect(self._finalkan_opname)
        top_bar.addWidget(self.btn_finalkan)

        layout.addLayout(top_bar)

        # Info Sesi
        self.lbl_info_sesi = QLabel("Belum ada sesi opname aktif. Silakan buat sesi baru atau pilih sesi draft di bawah.", self)
        self.lbl_info_sesi.setStyleSheet("color: #475569; font-weight: bold;")
        layout.addWidget(self.lbl_info_sesi)

        # Splitter: Daftar Sesi vs Tabel Input Opname Barang
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Panel Kiri: Daftar Sesi Opname
        wadah_kiri = QWidget()
        lay_kiri = QVBoxLayout(wadah_kiri)
        lay_kiri.addWidget(QLabel("Daftar Sesi Stock Opname:", self))

        self.tbl_sesi = QTableWidget(self)
        self.tbl_sesi.setColumnCount(4)
        self.tbl_sesi.setHorizontalHeaderLabels(["Kode", "Tanggal", "Status", "Periode"])
        self.tbl_sesi.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_sesi.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_sesi.setColumnWidth(1, 105)  # Tanggal
        self.tbl_sesi.setColumnWidth(2, 90)   # Status
        self.tbl_sesi.setColumnWidth(3, 90)   # Periode
        terapkan_style_tabel_global(
            self.tbl_sesi,
            kolom_status=2
        )
        self.tbl_sesi.itemClicked.connect(self._pilih_sesi)
        lay_kiri.addWidget(self.tbl_sesi)
        splitter.addWidget(wadah_kiri)

        # Panel Kanan: Tabel Input Fisik Barang
        wadah_kanan = QWidget()
        lay_kanan = QVBoxLayout(wadah_kanan)
        lay_kanan.addWidget(QLabel("Rincian Fisik Barang (Ketik stok fisik lalu simpan):", self))

        self.tbl_barang = QTableWidget(self)
        self.tbl_barang.setColumnCount(7)
        self.tbl_barang.setHorizontalHeaderLabels([
            "Kode", "Nama Barang", "Satuan", "Stok Sistem", "Stok Fisik (Input)", "Selisih Qty", "Estimasi Selisih Nilai"
        ])
        self.tbl_barang.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_barang.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl_barang.setColumnWidth(0, 100)  # Kode
        self.tbl_barang.setColumnWidth(2, 90)   # Satuan
        self.tbl_barang.setColumnWidth(3, 110)  # Stok Sistem
        self.tbl_barang.setColumnWidth(4, 130)  # Stok Fisik
        self.tbl_barang.setColumnWidth(5, 100)  # Selisih Qty
        self.tbl_barang.setColumnWidth(6, 150)  # Estimasi Selisih Nilai
        terapkan_style_tabel_global(
            self.tbl_barang,
            rata_kanan_kolom=[3, 4, 5, 6]
        )
        self.tbl_barang.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked
            | QTableWidget.EditTrigger.SelectedClicked
            | QTableWidget.EditTrigger.EditKeyPressed
        )
        self.tbl_barang.cellChanged.connect(self._on_cell_changed)
        lay_kanan.addWidget(self.tbl_barang)
        splitter.addWidget(wadah_kanan)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

        self.muat_daftar_sesi()

    def muat_daftar_sesi(self):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM opname_sesi ORDER BY tanggal DESC, id DESC;")
        rows = cur.fetchall()
        self.tbl_sesi.setRowCount(len(rows))
        for idx, r in enumerate(rows):
            self.tbl_sesi.setItem(idx, 0, QTableWidgetItem(r["kode_opname"]))
            self.tbl_sesi.setItem(idx, 1, QTableWidgetItem(format_tanggal_indo(r["tanggal"])))
            
            c_st = QTableWidgetItem(r["status"].upper())
            if r["status"] == "draft":
                c_st.setForeground(QColor("#D97706"))
            else:
                c_st.setForeground(QColor("#059669"))
            self.tbl_sesi.setItem(idx, 2, c_st)
            self.tbl_sesi.setItem(idx, 3, QTableWidgetItem(r["periode"]))
            self.tbl_sesi.item(idx, 0).setData(Qt.ItemDataRole.UserRole, r["id"])

    def _pilih_sesi(self, item):
        row = item.row()
        item_kode = self.tbl_sesi.item(row, 0)
        sesi_id = item_kode.data(Qt.ItemDataRole.UserRole)
        self.sesi_aktif_id = sesi_id

        cur = self.conn.cursor()
        cur.execute("SELECT * FROM opname_sesi WHERE id = ?;", (sesi_id,))
        sesi = cur.fetchone()
        if sesi:
            st = sesi["status"].upper()
            self.lbl_info_sesi.setText(
                f"Sesi Aktif: {sesi['kode_opname']} | Tanggal: {format_tanggal_indo(sesi['tanggal'])} | Status: {st}"
            )
            self.btn_finalkan.setEnabled(sesi["status"] == "draft")
            self.muat_barang_opname(sesi_id, sesi["status"])

    def muat_barang_opname(self, sesi_id: int, status_sesi: str):
        self.tbl_barang.blockSignals(True)
        rincian = ambil_daftar_opname_barang(self.conn, sesi_id)

        # Jika sesi baru dibuat dan belum ada baris opname_barang, inisialisasi dari daftar master barang
        if not rincian and status_sesi == "draft":
            semua_brg = ambil_daftar_barang(self.conn)
            draft_init = []
            for b in semua_brg:
                draft_init.append({
                    "barang_id": b["id"],
                    "stok_fisik": b["stok_saat_ini"],
                    "catatan": ""
                })
            simpan_baris_opname_draft(self.conn, sesi_id, draft_init)
            rincian = ambil_daftar_opname_barang(self.conn, sesi_id)

        self.tbl_barang.setRowCount(len(rincian))
        for idx, r in enumerate(rincian):
            self.tbl_barang.setItem(idx, 0, QTableWidgetItem(r["kode"]))
            self.tbl_barang.setItem(idx, 1, QTableWidgetItem(r["nama"]))
            self.tbl_barang.setItem(idx, 2, QTableWidgetItem(r["satuan_dasar"]))
            
            c_sis = QTableWidgetItem(str(r["stok_sistem"]))
            c_sis.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            c_sis.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.tbl_barang.setItem(idx, 3, c_sis)

            c_fis = QTableWidgetItem(str(r["stok_fisik"]))
            c_fis.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if status_sesi != "draft":
                c_fis.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.tbl_barang.setItem(idx, 4, c_fis)

            selisih_qty = r["selisih_qty"]
            c_sls = QTableWidgetItem(f"{selisih_qty:+d}" if selisih_qty != 0 else "0")
            c_sls.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            c_sls.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            if selisih_qty < 0:
                c_sls.setForeground(QColor("#DC2626"))
            elif selisih_qty > 0:
                c_sls.setForeground(QColor("#059669"))
            self.tbl_barang.setItem(idx, 5, c_sls)

            c_nil = QTableWidgetItem(format_rupiah(r["selisih_nilai"]))
            c_nil.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            c_nil.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.tbl_barang.setItem(idx, 6, c_nil)

            self.tbl_barang.item(idx, 0).setData(Qt.ItemDataRole.UserRole, r["barang_id"])

        self.tbl_barang.blockSignals(False)

    def _on_cell_changed(self, row: int, col: int):
        if col != 4 or not self.sesi_aktif_id:
            return
        try:
            val_text = self.tbl_barang.item(row, 4).text().strip()
            fisik_baru = int(val_text)
            b_id = self.tbl_barang.item(row, 0).data(Qt.ItemDataRole.UserRole)
            simpan_baris_opname_draft(self.conn, self.sesi_aktif_id, [{
                "barang_id": b_id,
                "stok_fisik": fisik_baru
            }])
            # Segarkan baris
            cur = self.conn.cursor()
            cur.execute("SELECT status FROM opname_sesi WHERE id = ?;", (self.sesi_aktif_id,))
            st = cur.fetchone()["status"]
            self.muat_barang_opname(self.sesi_aktif_id, st)
        except Exception:
            pass

    def _buat_sesi_baru(self):
        tgl_hari_ini = QDate.currentDate().toString("yyyy-MM-dd")
        try:
            sesi_id, kode = buat_sesi_opname(self.conn, tgl_hari_ini, "Stock Opname Rutin")
            self.muat_daftar_sesi()
            self.sesi_aktif_id = sesi_id
            self.lbl_info_sesi.setText(f"Sesi Aktif: {kode} | Status: DRAFT")
            self.muat_barang_opname(sesi_id, "draft")
            QMessageBox.information(self, "Berhasil", f"Sesi stock opname {kode} berhasil dibuat.")
        except Exception as e:
            QMessageBox.warning(self, "Perhatian", f"Gagal membuat sesi opname: {e}")

    def _finalkan_opname(self):
        if not self.sesi_aktif_id:
            return
        konfirmasi = QMessageBox.question(
            self,
            "Konfirmasi Finalisasi Opname",
            "Apakah Anda yakin ingin memfinalkan sesi stock opname ini?\n"
            "- Selisih kurang akan dipotong dari lot FIFO terlama sebagai kerugian persediaan.\n"
            "- Selisih lebih akan dicatat sebagai lot penyesuaian baru.\n"
            "Sesi yang sudah difinalkan akan terkunci permanen.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if konfirmasi != QMessageBox.StandardButton.Yes:
            return

        try:
            res = finalisasi_sesi_opname(self.conn, self.sesi_aktif_id)
            QMessageBox.information(
                self,
                "Opname Berhasil Difinalkan",
                f"Sesi {res['kode_opname']} telah berhasil difinalkan.\n"
                f"Selisih Kurang: {res['total_kurang_qty']} unit (Rp {res['total_kurang_nilai']:,})\n"
                f"Selisih Lebih: {res['total_lebih_qty']} unit (Rp {res['total_lebih_nilai']:,})".replace(",", ".")
            )
            self.muat_daftar_sesi()
            self._pilih_sesi(self.tbl_sesi.item(0, 0))
        except Exception as e:
            QMessageBox.warning(self, "Gagal Finalisasi", f"Tidak dapat memfinalkan opname: {e}")
