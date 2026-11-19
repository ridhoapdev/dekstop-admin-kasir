"""
app/ui/layar_kartu_anggota.py — Layar Kartu Anggota (SPEC.md 4.6 B).
Menampilkan profil data diri, saldo simpanan, pinjaman aktif & tunggakan, serta riwayat seluruh transaksi.
"""
import sqlite3
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QGroupBox, QGridLayout, QFileDialog, QMessageBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from app.db.repo_kartu_anggota import ambil_data_kartu_anggota
from app.util.format import format_rupiah, format_tanggal_indo
from app.layanan.ekspor_excel import ekspor_tabel_ke_excel
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global, NumericTableWidgetItem


class LayarKartuAnggota(QWidget):
    """Layar Kartu Anggota Lengkap."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.anggota_id_aktif = None
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header Atas
        header_layout = QHBoxLayout()
        self.label_judul = QLabel("Kartu Anggota", self)
        self.label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(self.label_judul)

        header_layout.addStretch()

        self.btn_ekspor = QPushButton("Ekspor Riwayat ke Excel", self)
        self.btn_ekspor.setProperty("tipe", "sukses")
        self.btn_ekspor.clicked.connect(self._ekspor_excel)
        header_layout.addWidget(self.btn_ekspor)

        layout.addLayout(header_layout)

        # Bagian 1: Data Diri & Saldo Simpanan (Grid Berdampingan)
        top_grid = QHBoxLayout()

        # Box Profil Data Diri
        box_profil = QGroupBox("Profil Anggota", self)
        box_profil_layout = QGridLayout(box_profil)
        self.lbl_no_anggota = QLabel("-")
        self.lbl_nama = QLabel("-")
        self.lbl_nik = QLabel("-")
        self.lbl_unit = QLabel("-")
        self.lbl_hp = QLabel("-")
        self.lbl_status = QLabel("-")

        box_profil_layout.addWidget(QLabel("No. Anggota:"), 0, 0)
        box_profil_layout.addWidget(self.lbl_no_anggota, 0, 1)
        box_profil_layout.addWidget(QLabel("Nama Lengkap:"), 1, 0)
        box_profil_layout.addWidget(self.lbl_nama, 1, 1)
        box_profil_layout.addWidget(QLabel("NIK Karyawan:"), 2, 0)
        box_profil_layout.addWidget(self.lbl_nik, 2, 1)
        box_profil_layout.addWidget(QLabel("Unit / Bagian:"), 3, 0)
        box_profil_layout.addWidget(self.lbl_unit, 3, 1)
        box_profil_layout.addWidget(QLabel("No. HP / WA:"), 4, 0)
        box_profil_layout.addWidget(self.lbl_hp, 4, 1)
        box_profil_layout.addWidget(QLabel("Status Anggota:"), 5, 0)
        box_profil_layout.addWidget(self.lbl_status, 5, 1)
        top_grid.addWidget(box_profil, 1)

        # Box Saldo Simpanan & Pinjaman Aktif
        box_keuangan = QGroupBox("Posisi Keuangan Saat Ini", self)
        box_keuangan_layout = QGridLayout(box_keuangan)
        self.lbl_simpanan_pokok = QLabel("Rp 0")
        self.lbl_simpanan_wajib = QLabel("Rp 0")
        self.lbl_simpanan_sukarela = QLabel("Rp 0")
        self.lbl_total_simpanan = QLabel("Rp 0")
        self.lbl_total_simpanan.setStyleSheet("font-weight: bold; color: #16A34A;")
        
        self.lbl_pinjaman_aktif = QLabel("Tidak ada pinjaman aktif")
        self.lbl_tunggakan = QLabel("Rp 0")
        self.lbl_utang_toko = QLabel("Rp 0")

        box_keuangan_layout.addWidget(QLabel("Simpanan Pokok:"), 0, 0)
        box_keuangan_layout.addWidget(self.lbl_simpanan_pokok, 0, 1)
        box_keuangan_layout.addWidget(QLabel("Simpanan Wajib:"), 1, 0)
        box_keuangan_layout.addWidget(self.lbl_simpanan_wajib, 1, 1)
        box_keuangan_layout.addWidget(QLabel("Simpanan Sukarela:"), 2, 0)
        box_keuangan_layout.addWidget(self.lbl_simpanan_sukarela, 2, 1)
        box_keuangan_layout.addWidget(QLabel("Total Saldo Simpanan:"), 3, 0)
        box_keuangan_layout.addWidget(self.lbl_total_simpanan, 3, 1)
        box_keuangan_layout.addWidget(QLabel("Pinjaman Berjalan:"), 4, 0)
        box_keuangan_layout.addWidget(self.lbl_pinjaman_aktif, 4, 1)
        box_keuangan_layout.addWidget(QLabel("Total Tunggakan:"), 5, 0)
        box_keuangan_layout.addWidget(self.lbl_tunggakan, 5, 1)
        box_keuangan_layout.addWidget(QLabel("Utang Toko (Terpisah):"), 6, 0)
        box_keuangan_layout.addWidget(self.lbl_utang_toko, 6, 1)
        top_grid.addWidget(box_keuangan, 1)

        layout.addLayout(top_grid)

        # Bagian 2: Riwayat Seluruh Transaksi
        riwayat_header = QHBoxLayout()
        label_riwayat = QLabel("Riwayat Seluruh Transaksi Anggota", self)
        label_riwayat.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        riwayat_header.addWidget(label_riwayat)

        riwayat_header.addStretch()

        self.combo_filter_riwayat = QComboBox(self)
        self.combo_filter_riwayat.setMinimumHeight(36)
        self.combo_filter_riwayat.addItem("Semua Transaksi", "semua")
        self.combo_filter_riwayat.addItem("Hanya Simpanan", "simpanan")
        self.combo_filter_riwayat.addItem("Hanya Angsuran", "angsuran")
        self.combo_filter_riwayat.currentIndexChanged.connect(self._filter_riwayat_berubah)
        riwayat_header.addWidget(self.combo_filter_riwayat)

        layout.addLayout(riwayat_header)

        # Tabel Riwayat
        self.tabel_riwayat = QTableWidget(self)
        self.tabel_riwayat.setFont(QFont("Segoe UI", 11))
        self.tabel_riwayat.setColumnCount(6)
        self.tabel_riwayat.setHorizontalHeaderLabels([
            "Tanggal", "Kategori", "Rincian Transaksi", "Masuk (Rp)", "Keluar (Rp)", "Keterangan"
        ])
        self.tabel_riwayat.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel_riwayat.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabel_riwayat.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.tabel_riwayat.setColumnWidth(0, 115)  # Tanggal
        self.tabel_riwayat.setColumnWidth(1, 110)  # Kategori
        self.tabel_riwayat.setColumnWidth(3, 140)  # Masuk (Rp)
        self.tabel_riwayat.setColumnWidth(4, 140)  # Keluar (Rp)
        terapkan_style_tabel_global(
            self.tabel_riwayat,
            rata_kanan_kolom=[3, 4]
        )
        layout.addWidget(self.tabel_riwayat)

        self.data_kartu_saat_ini = None

    def muat_anggota(self, anggota_id: int) -> None:
        """Memuat seluruh informasi kartu anggota berdasarkan anggota_id."""
        self.anggota_id_aktif = anggota_id
        filter_mode = self.combo_filter_riwayat.currentData() or "semua"
        data = ambil_data_kartu_anggota(self.conn, anggota_id, filter_jenis_transaksi=filter_mode)
        if not data:
            return

        self.data_kartu_saat_ini = data
        ang = data["anggota"]
        self.label_judul.setText(f"Kartu Anggota - {ang['nama']} ({ang['no_anggota']})")

        # Tampilkan Data Diri
        self.lbl_no_anggota.setText(ang["no_anggota"])
        self.lbl_nama.setText(ang["nama"])
        self.lbl_nik.setText(ang["nik_karyawan"] or "-")
        self.lbl_unit.setText(ang["unit"] or "-")
        self.lbl_hp.setText(ang["no_hp"] or "-")
        self.lbl_status.setText(ang["status"].capitalize())

        # Tampilkan Saldo Simpanan
        saldo = data["saldo_simpanan"]
        self.lbl_simpanan_pokok.setText(format_rupiah(saldo["pokok"]))
        self.lbl_simpanan_wajib.setText(format_rupiah(saldo["wajib"]))
        self.lbl_simpanan_sukarela.setText(format_rupiah(saldo["sukarela"]))
        self.lbl_total_simpanan.setText(format_rupiah(saldo["total"]))

        # Tampilkan Pinjaman Aktif
        pinj_list = data["pinjaman_aktif"]
        if pinj_list:
            p = pinj_list[0]
            info_p = (
                f"{p['no_pinjaman']} (Sisa Pokok: {format_rupiah(p['sisa_pokok'])}) - "
                f"Angs. Ke-{p['angsuran_ke_berikutnya'] or '-'} "
                f"(Jatuh Tempo: {format_tanggal_indo(p['jatuh_tempo_berikutnya'])})"
            )
            self.lbl_pinjaman_aktif.setText(info_p)

            tot_tung = sum(item["total_tunggakan"] for item in pinj_list)
            self.lbl_tunggakan.setText(format_rupiah(tot_tung))
            if tot_tung > 0:
                self.lbl_tunggakan.setStyleSheet("font-weight: bold; color: #DC2626;")
            else:
                self.lbl_tunggakan.setStyleSheet("color: #16A34A;")
        else:
            self.lbl_pinjaman_aktif.setText("Tidak ada pinjaman aktif")
            self.lbl_tunggakan.setText("Rp 0")
            self.lbl_tunggakan.setStyleSheet("color: #16A34A;")

        # Tampilkan Utang Toko Terpisah (SPEC Modul 15 A)
        try:
            from app.db.repo_kartu_toko import ambil_ringkasan_piutang_anggota
            ringk_toko = ambil_ringkasan_piutang_anggota(self.conn, anggota_id)
            if ringk_toko and ringk_toko["total_utang_toko"] > 0:
                self.lbl_utang_toko.setText(
                    f"{format_rupiah(ringk_toko['total_utang_toko'])} ({ringk_toko['jumlah_nota_belum_lunas']} nota)"
                )
                self.lbl_utang_toko.setStyleSheet("font-weight: bold; color: #D97706;")
            else:
                self.lbl_utang_toko.setText("Rp 0 (Lunas / Tidak ada utang)")
                self.lbl_utang_toko.setStyleSheet("color: #16A34A;")
        except Exception:
            self.lbl_utang_toko.setText("-")

        # Tampilkan Riwayat Transaksi
        riwayat = data["riwayat_transaksi"]
        self.tabel_riwayat.setRowCount(len(riwayat))

        for baris, tx in enumerate(riwayat):
            self.tabel_riwayat.setItem(baris, 0, QTableWidgetItem(format_tanggal_indo(tx["tanggal"])))
            self.tabel_riwayat.setItem(baris, 1, QTableWidgetItem(tx["tipe"]))
            self.tabel_riwayat.setItem(baris, 2, QTableWidgetItem(tx["rincian"]))

            masuk_item = QTableWidgetItem(format_rupiah(tx["masuk"]) if tx["masuk"] > 0 else "-")
            masuk_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel_riwayat.setItem(baris, 3, masuk_item)

            keluar_item = QTableWidgetItem(format_rupiah(tx["keluar"]) if tx["keluar"] > 0 else "-")
            keluar_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel_riwayat.setItem(baris, 4, keluar_item)

            ket_item = QTableWidgetItem(f"[Koreksi] {tx['keterangan']}" if tx["is_pembalik"] else tx["keterangan"])
            self.tabel_riwayat.setItem(baris, 5, ket_item)

    def _filter_riwayat_berubah(self) -> None:
        if self.anggota_id_aktif:
            self.muat_anggota(self.anggota_id_aktif)

    def _ekspor_excel(self) -> None:
        if not self.data_kartu_saat_ini:
            return

        ang = self.data_kartu_saat_ini["anggota"]
        nama_file_default = f"Kartu_Anggota_{ang['no_anggota']}.xlsx"
        
        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Simpan Laporan Excel", nama_file_default, "Excel Files (*.xlsx)"
        )
        if not path_simpan:
            return

        kolom = ["Tanggal", "Kategori", "Rincian Transaksi", "Masuk (Rp)", "Keluar (Rp)", "Keterangan"]
        baris_data = []
        tot_m = 0
        tot_k = 0

        for tx in self.data_kartu_saat_ini["riwayat_transaksi"]:
            tot_m += tx["masuk"]
            tot_k += tx["keluar"]
            baris_data.append([
                tx["tanggal"],
                tx["tipe"],
                tx["rincian"],
                tx["masuk"],
                tx["keluar"],
                tx["keterangan"]
            ])

        baris_total = ["TOTAL", "", "", tot_m, tot_k, ""]
        judul = f"KARTU ANGGOTA: {ang['nama']} ({ang['no_anggota']}) - UNIT: {ang['unit'] or '-'}"

        try:
            ekspor_tabel_ke_excel(judul, kolom, baris_data, path_simpan, baris_total)
            QMessageBox.information(self, "Ekspor Berhasil", f"Kartu anggota berhasil disimpan ke:\n{path_simpan}")
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal mengekspor data: {err}")

