"""
app/ui/layar_laporan_tahunan.py — Layar Laporan Tahunan Koperasi.
Menampilkan rekapitulasi keuangan 12 bulan (kas masuk, kas keluar, saldo akhir,
simpanan masuk, pinjaman cair, jasa diterima, sisa pokok), baris total setahun,
posisi neraca & keanggotaan akhir tahun, grafik batang responsif, serta ekspor Excel dan PDF.
"""
import sqlite3
from datetime import date
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QFileDialog, QMessageBox, QGroupBox, QGridLayout, QScrollArea
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QThread, Signal

from app.db.repo_laporan_periode import (
    ambil_daftar_tahun_tersedia, ambil_data_laporan_tahunan
)
from app.util.format import format_rupiah
from app.layanan.ekspor_laporan_periode import (
    ekspor_laporan_tahunan_excel, ekspor_laporan_tahunan_pdf
)
from app.ui.komponen.tabel_helper import terapkan_style_tabel_global
from app.ui.komponen.grafik_batang_qt import WidgetGrafikBatangTahunan


class WorkerMuatTahunan(QThread):
    selesai = Signal(dict)
    gagal = Signal(str)

    def __init__(self, db_path: str, tahun: int):
        super().__init__()
        self.db_path = db_path
        self.tahun = tahun

    def run(self):
        try:
            from app.db.koneksi import buka_koneksi
            conn = buka_koneksi(self.db_path)
            try:
                res = ambil_data_laporan_tahunan(conn, self.tahun)
                self.selesai.emit(res)
            finally:
                conn.close()
        except Exception as e:
            self.gagal.emit(str(e))


class LayarLaporanTahunan(QWidget):
    """Layar Laporan Keuangan Tahunan (12 Bulan)."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        from app.config import DB_PATH
        self.db_path = DB_PATH
        self.data_laporan = {}
        self.worker = None
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 11))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        # Header: Judul & Ekspor
        header_layout = QHBoxLayout()
        self.label_judul = QLabel("Laporan Keuangan Tahunan", self)
        self.label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(self.label_judul)

        header_layout.addStretch()

        self.btn_ekspor_excel = QPushButton("Ekspor Excel (.xlsx)", self)
        self.btn_ekspor_excel.setProperty("tipe", "sukses")
        self.btn_ekspor_excel.clicked.connect(self._ekspor_excel)

        self.btn_ekspor_pdf = QPushButton("Ekspor PDF", self)
        self.btn_ekspor_pdf.setProperty("tipe", "bahaya")
        self.btn_ekspor_pdf.clicked.connect(self._ekspor_pdf)

        header_layout.addWidget(self.btn_ekspor_excel)
        header_layout.addWidget(self.btn_ekspor_pdf)
        layout.addLayout(header_layout)

        # Filter Bar: Tahun Buku
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Tahun Buku:"))

        self.combo_tahun = QComboBox(self)
        daftar_thn = ambil_daftar_tahun_tersedia(self.conn)
        for t in daftar_thn:
            self.combo_tahun.addItem(f"Tahun {t}", t)
        filter_bar.addWidget(self.combo_tahun)

        btn_tampilkan = QPushButton("Tampilkan Laporan", self)
        btn_tampilkan.setProperty("tipe", "utama")
        btn_tampilkan.clicked.connect(self.muat_data)
        filter_bar.addWidget(btn_tampilkan)

        self.lbl_loading = QLabel("", self)
        self.lbl_loading.setStyleSheet("color: #2563EB; font-weight: bold;")
        filter_bar.addWidget(self.lbl_loading)

        filter_bar.addStretch()
        layout.addLayout(filter_bar)

        # Banner Peringatan Bulan Belum Closing
        self.lbl_warning_closing = QLabel(self)
        self.lbl_warning_closing.setStyleSheet("background-color: #FEF3C7; color: #92400E; padding: 8px 12px; border-radius: 6px; font-weight: bold;")
        self.lbl_warning_closing.hide()
        layout.addWidget(self.lbl_warning_closing)

        # Scroll Area
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        konten_widget = QWidget()
        konten_layout = QVBoxLayout(konten_widget)
        konten_layout.setContentsMargins(0, 0, 0, 0)
        konten_layout.setSpacing(12)

        # 1. Grafik Batang Ringan
        self.grafik_widget = WidgetGrafikBatangTahunan(konten_widget)
        konten_layout.addWidget(self.grafik_widget)

        # 2. Tabel Rekapitulasi 12 Bulan
        box_12 = QGroupBox("Tabel Rekapitulasi Keuangan 12 Bulan", konten_widget)
        v_12 = QVBoxLayout(box_12)

        self.tabel_12 = QTableWidget(box_12)
        self.tabel_12.setColumnCount(9)
        self.tabel_12.setHorizontalHeaderLabels([
            "Bulan", "Status", "Kas Masuk (Rp)", "Kas Keluar (Rp)", "Kas Akhir (Rp)",
            "Simpanan Masuk (Rp)", "Pinjaman Cair (Rp)", "Jasa Diterima (Rp)", "Sisa Pokok (Rp)"
        ])
        self.tabel_12.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel_12.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabel_12.setColumnWidth(1, 90)
        self.tabel_12.setColumnWidth(2, 125)
        self.tabel_12.setColumnWidth(3, 125)
        self.tabel_12.setColumnWidth(4, 130)
        self.tabel_12.setColumnWidth(5, 130)
        self.tabel_12.setColumnWidth(6, 130)
        self.tabel_12.setColumnWidth(7, 125)
        self.tabel_12.setColumnWidth(8, 135)
        terapkan_style_tabel_global(
            self.tabel_12,
            rata_kanan_kolom=[2, 3, 4, 5, 6, 7, 8],
            kolom_status=1
        )
        self.tabel_12.setFixedHeight(380)
        v_12.addWidget(self.tabel_12)
        konten_layout.addWidget(box_12)

        # 3. Box Posisi Akhir Tahun
        box_neraca = QGroupBox("Posisi Keuangan dan Keanggotaan Akhir Tahun", konten_widget)
        grid_n = QGridLayout(box_neraca)

        self.lbl_tot_simp_pokok = QLabel("Rp 0")
        self.lbl_tot_simp_wajib = QLabel("Rp 0")
        self.lbl_tot_simp_sukarela = QLabel("Rp 0")
        self.lbl_tot_seluruh_simp = QLabel("Rp 0")
        self.lbl_tot_seluruh_simp.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_tot_seluruh_simp.setStyleSheet("color: #059669;")

        self.lbl_pinj_beredar = QLabel("Rp 0")
        self.lbl_pinj_beredar.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_pinj_beredar.setStyleSheet("color: #D97706;")

        self.lbl_tot_tunggakan = QLabel("Rp 0")
        self.lbl_tot_tunggakan.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_tot_tunggakan.setStyleSheet("color: #DC2626;")

        self.lbl_kas_akhir_tahun = QLabel("Rp 0")
        self.lbl_kas_akhir_tahun.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_kas_akhir_tahun.setStyleSheet("color: #1E3A8A;")

        self.lbl_ag_baru = QLabel("0 Orang")
        self.lbl_ag_keluar = QLabel("0 Orang")
        self.lbl_ag_aktif = QLabel("0 Orang")
        self.lbl_ag_aktif.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        grid_n.addWidget(QLabel("Saldo Simpanan Pokok:"), 0, 0)
        grid_n.addWidget(self.lbl_tot_simp_pokok, 0, 1)
        grid_n.addWidget(QLabel("Pinjaman Beredar (Sisa Pokok):"), 0, 2)
        grid_n.addWidget(self.lbl_pinj_beredar, 0, 3)

        grid_n.addWidget(QLabel("Saldo Simpanan Wajib:"), 1, 0)
        grid_n.addWidget(self.lbl_tot_simp_wajib, 1, 1)
        grid_n.addWidget(QLabel("Total Tunggakan Akhir Tahun:"), 1, 2)
        grid_n.addWidget(self.lbl_tot_tunggakan, 1, 3)

        grid_n.addWidget(QLabel("Saldo Simpanan Sukarela:"), 2, 0)
        grid_n.addWidget(self.lbl_tot_simp_sukarela, 2, 1)
        grid_n.addWidget(QLabel("Anggota Baru / Keluar:"), 2, 2)
        self.lbl_ag_mutasi = QLabel("Baru: 0 | Keluar: 0")
        grid_n.addWidget(self.lbl_ag_mutasi, 2, 3)

        grid_n.addWidget(QLabel("<b>Total Seluruh Simpanan:</b>"), 3, 0)
        grid_n.addWidget(self.lbl_tot_seluruh_simp, 3, 1)
        grid_n.addWidget(QLabel("<b>Total Anggota Aktif Akhir:</b>"), 3, 2)
        grid_n.addWidget(self.lbl_ag_aktif, 3, 3)

        grid_n.addWidget(QLabel("<b>Saldo Kas Operasional Akhir:</b>"), 4, 0)
        grid_n.addWidget(self.lbl_kas_akhir_tahun, 4, 1)

        konten_layout.addWidget(box_neraca)

        scroll.setWidget(konten_widget)
        layout.addWidget(scroll, 1)

        self.muat_data()

    def muat_data(self) -> None:
        tahun = self.combo_tahun.currentData() or date.today().year
        self.lbl_loading.setText("Memuat laporan tahunan...")
        self.btn_ekspor_excel.setEnabled(False)
        self.btn_ekspor_pdf.setEnabled(False)

        self.worker = WorkerMuatTahunan(self.db_path, tahun)
        self.worker.selesai.connect(self._on_data_termuat)
        self.worker.gagal.connect(self._on_gagal_muat)
        self.worker.start()

    def _on_data_termuat(self, data: dict) -> None:
        self.lbl_loading.setText("")
        self.btn_ekspor_excel.setEnabled(True)
        self.btn_ekspor_pdf.setEnabled(True)
        self.data_laporan = data

        # Peringatan bulan belum closing
        if data["bulan_belum_closing"]:
            teks_blm = ", ".join(data["bulan_belum_closing"])
            self.lbl_warning_closing.setText(
                f"Pemberitahuan: Ada {len(data['bulan_belum_closing'])} bulan yang belum di-closing (data sementara): {teks_blm}."
            )
            self.lbl_warning_closing.show()
        else:
            self.lbl_warning_closing.hide()

        # Update Grafik
        self.grafik_widget.set_data(data["tabel_12_bulan"])

        # Update Tabel 12 Bulan + Baris Total (total 13 baris)
        rows_data = list(data["tabel_12_bulan"])
        self.tabel_12.setRowCount(len(rows_data) + 1)

        for r_idx, b in enumerate(rows_data):
            it_bln = QTableWidgetItem(b["nama_bulan"])
            it_st = QTableWidgetItem(b["status_label"])
            it_km = QTableWidgetItem(format_rupiah(b["kas_masuk"]))
            it_kk = QTableWidgetItem(format_rupiah(b["kas_keluar"]))
            it_ka = QTableWidgetItem(format_rupiah(b["saldo_kas_akhir"]))
            it_sm = QTableWidgetItem(format_rupiah(b["simpanan_masuk"]))
            it_pc = QTableWidgetItem(format_rupiah(b["pinjaman_cair"]))
            it_jd = QTableWidgetItem(format_rupiah(b["jasa_diterima"]))
            it_sp = QTableWidgetItem(format_rupiah(b["sisa_pokok"]))

            for it in (it_km, it_kk, it_ka, it_sm, it_pc, it_jd, it_sp):
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.tabel_12.setItem(r_idx, 0, it_bln)
            self.tabel_12.setItem(r_idx, 1, it_st)
            self.tabel_12.setItem(r_idx, 2, it_km)
            self.tabel_12.setItem(r_idx, 3, it_kk)
            self.tabel_12.setItem(r_idx, 4, it_ka)
            self.tabel_12.setItem(r_idx, 5, it_sm)
            self.tabel_12.setItem(r_idx, 6, it_pc)
            self.tabel_12.setItem(r_idx, 7, it_jd)
            self.tabel_12.setItem(r_idx, 8, it_sp)

        # Baris Total Setahun
        tot_idx = len(rows_data)
        it_tbln = QTableWidgetItem("TOTAL SETAHUN")
        it_tst = QTableWidgetItem("-")
        it_tkm = QTableWidgetItem(format_rupiah(data["total_kas_masuk"]))
        it_tkk = QTableWidgetItem(format_rupiah(data["total_kas_keluar"]))
        it_tka = QTableWidgetItem(format_rupiah(data["saldo_kas_akhir"]))
        it_tsm = QTableWidgetItem(format_rupiah(data["total_simpanan_masuk"]))
        it_tpc = QTableWidgetItem(format_rupiah(data["total_pinjaman_cair"]))
        it_tjd = QTableWidgetItem(format_rupiah(data["total_jasa_diterima"]))
        it_tsp = QTableWidgetItem(format_rupiah(data["sisa_pokok_akhir"]))

        f_bold = QFont("Segoe UI", 11, QFont.Weight.Bold)
        for it in (it_tbln, it_tst, it_tkm, it_tkk, it_tka, it_tsm, it_tpc, it_tjd, it_tsp):
            it.setFont(f_bold)
            it.setBackground(Qt.GlobalColor.lightGray)

        for it in (it_tkm, it_tkk, it_tka, it_tsm, it_tpc, it_tjd, it_tsp):
            it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.tabel_12.setItem(tot_idx, 0, it_tbln)
        self.tabel_12.setItem(tot_idx, 1, it_tst)
        self.tabel_12.setItem(tot_idx, 2, it_tkm)
        self.tabel_12.setItem(tot_idx, 3, it_tkk)
        self.tabel_12.setItem(tot_idx, 4, it_tka)
        self.tabel_12.setItem(tot_idx, 5, it_tsm)
        self.tabel_12.setItem(tot_idx, 6, it_tpc)
        self.tabel_12.setItem(tot_idx, 7, it_tjd)
        self.tabel_12.setItem(tot_idx, 8, it_tsp)

        # Update Posisi Akhir Tahun
        simp = data["posisi_simpanan"]
        self.lbl_tot_simp_pokok.setText(format_rupiah(simp["pokok"]["saldo_akhir"]))
        self.lbl_tot_simp_wajib.setText(format_rupiah(simp["wajib"]["saldo_akhir"]))
        self.lbl_tot_simp_sukarela.setText(format_rupiah(simp["sukarela"]["saldo_akhir"]))
        self.lbl_tot_seluruh_simp.setText(format_rupiah(simp["total"]["saldo_akhir"]))

        self.lbl_pinj_beredar.setText(format_rupiah(data["sisa_pokok_akhir"]))
        self.lbl_tot_tunggakan.setText(format_rupiah(data["total_tunggakan_akhir"]))
        self.lbl_kas_akhir_tahun.setText(format_rupiah(data["saldo_kas_akhir"]))

        self.lbl_ag_mutasi.setText(f"Baru: {data['anggota_baru']} | Keluar: {data['anggota_keluar']}")
        self.lbl_ag_aktif.setText(f"{data['anggota_aktif_akhir']} Orang")

    def _on_gagal_muat(self, err_msg: str) -> None:
        self.lbl_loading.setText("")
        self.btn_ekspor_excel.setEnabled(True)
        self.btn_ekspor_pdf.setEnabled(True)
        QMessageBox.critical(self, "Gagal Memuat Data", f"Terjadi kesalahan saat memuat laporan:\n{err_msg}")

    def _ambil_nama_koperasi(self) -> str:
        cur = self.conn.cursor()
        cur.execute("SELECT nilai FROM pengaturan WHERE kunci = 'nama_koperasi';")
        r = cur.fetchone()
        return r[0] if r else "Koperasi Simpan Pinjam"

    def _ekspor_excel(self) -> None:
        if not self.data_laporan:
            return
        nama_kop = self._ambil_nama_koperasi()
        nama_file_def = f"Laporan_Tahunan_{self.data_laporan['tahun']}.xlsx"
        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Ekspor Laporan Tahunan ke Excel", nama_file_def, "Excel Files (*.xlsx)"
        )
        if not path_simpan:
            return
        try:
            ekspor_laporan_tahunan_excel(self.data_laporan, nama_kop, path_simpan)
            QMessageBox.information(self, "Berhasil", f"Laporan tahunan tersimpan di:\n{path_simpan}")
        except Exception as e:
            QMessageBox.critical(self, "Gagal Ekspor", f"Terjadi kesalahan: {e}")

    def _ekspor_pdf(self) -> None:
        if not self.data_laporan:
            return
        nama_kop = self._ambil_nama_koperasi()
        nama_file_def = f"Laporan_Tahunan_{self.data_laporan['tahun']}.pdf"
        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Ekspor Laporan Tahunan ke PDF", nama_file_def, "PDF Files (*.pdf)"
        )
        if not path_simpan:
            return
        try:
            ekspor_laporan_tahunan_pdf(self.data_laporan, nama_kop, path_simpan)
            QMessageBox.information(self, "Berhasil", f"Laporan tahunan PDF tersimpan di:\n{path_simpan}")
        except Exception as e:
            QMessageBox.critical(self, "Gagal Ekspor", f"Terjadi kesalahan: {e}")

