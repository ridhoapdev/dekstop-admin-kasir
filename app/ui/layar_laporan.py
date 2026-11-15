"""
app/ui/layar_laporan.py — Layar Laporan Mingguan (SPEC.md 4.7).
- Pemilihan rentang minggu (default Senin - Minggu)
- Ringkasan arus kas (saldo kas awal, simpanan, angsuran pokok & jasa, pinjaman cair, saldo kas akhir)
- Tabel transaksi buku kas rinci
- Tombol Ekspor ke Excel (.xlsx) & Ekspor ke PDF
- Pencatatan log pembuatan laporan otomatis untuk mematikan pengingat di dashboard
"""
import sqlite3
from datetime import date, datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDateEdit,
    QFileDialog, QMessageBox, QGroupBox, QGridLayout, QCheckBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QDate

from app.db.repo_laporan import (
    tentukan_rentang_minggu, ambil_data_laporan_mingguan, catat_log_laporan_mingguan
)
from app.util.format import format_rupiah, format_tanggal_indo
from app.layanan.ekspor_excel import ekspor_tabel_ke_excel
from app.layanan.ekspor_pdf import ekspor_laporan_ke_pdf


class LayarLaporan(QWidget):
    """Layar Laporan Mingguan dan Ekspor."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.laporan_data = {}
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        header_layout = QHBoxLayout()
        label_judul = QLabel("Laporan Mingguan Koperasi", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(label_judul)

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

        # Baris Pemilihan Rentang Tanggal
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Periode Tanggal:"))

        self.input_tgl_awal = QDateEdit(self)
        self.input_tgl_awal.setCalendarPopup(True)
        self.input_tgl_awal.setDisplayFormat("dd/MM/yyyy")

        self.input_tgl_akhir = QDateEdit(self)
        self.input_tgl_akhir.setCalendarPopup(True)
        self.input_tgl_akhir.setDisplayFormat("dd/MM/yyyy")

        # Set default minggu berjalan (Senin - Minggu)
        awal_minggu, akhir_minggu = tentukan_rentang_minggu(date.today())
        self.input_tgl_awal.setDate(QDate(awal_minggu.year, awal_minggu.month, awal_minggu.day))
        self.input_tgl_akhir.setDate(QDate(akhir_minggu.year, akhir_minggu.month, akhir_minggu.day))

        filter_bar.addWidget(self.input_tgl_awal)
        filter_bar.addWidget(QLabel("s/d"))
        filter_bar.addWidget(self.input_tgl_akhir)

        btn_minggu_ini = QPushButton("Minggu Ini", self)
        btn_minggu_ini.clicked.connect(self._pilih_minggu_ini)

        btn_minggu_lalu = QPushButton("Minggu Lalu", self)
        btn_minggu_lalu.clicked.connect(self._pilih_minggu_lalu)

        btn_tampilkan = QPushButton("Tampilkan Laporan", self)
        btn_tampilkan.setProperty("tipe", "utama")
        btn_tampilkan.clicked.connect(self.muat_data)

        filter_bar.addWidget(btn_minggu_ini)
        filter_bar.addWidget(btn_minggu_lalu)
        filter_bar.addWidget(btn_tampilkan)
        filter_bar.addStretch()

        layout.addLayout(filter_bar)

        # Box Ringkasan Arus Kas
        box_ringkasan = QGroupBox("Ringkasan Arus Kas Periode (Bersih)", self)
        grid_r = QGridLayout(box_ringkasan)

        self.lbl_kas_awal = QLabel("Rp 0")
        self.lbl_simp_masuk = QLabel("Rp 0")
        self.lbl_simp_keluar = QLabel("Rp 0")
        self.lbl_angs_pokok = QLabel("Rp 0")
        self.lbl_angs_jasa = QLabel("Rp 0")
        self.lbl_pinj_cair = QLabel("Rp 0")
        self.lbl_admin = QLabel("Rp 0")
        self.lbl_koreksi = QLabel("Rp 0")
        self.lbl_kas_masuk = QLabel("Rp 0")
        self.lbl_kas_keluar = QLabel("Rp 0")
        self.lbl_kas_akhir = QLabel("Rp 0")
        self.lbl_kas_akhir.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_kas_akhir.setStyleSheet("color: #1E3A8A;")

        grid_r.addWidget(QLabel("Saldo Kas Awal:"), 0, 0)
        grid_r.addWidget(self.lbl_kas_awal, 0, 1)
        grid_r.addWidget(QLabel("Simpanan Setor (+):"), 0, 2)
        grid_r.addWidget(self.lbl_simp_masuk, 0, 3)
        grid_r.addWidget(QLabel("Simpanan Tarik (-):"), 0, 4)
        grid_r.addWidget(self.lbl_simp_keluar, 0, 5)

        grid_r.addWidget(QLabel("Angsuran Pokok (+):"), 1, 0)
        grid_r.addWidget(self.lbl_angs_pokok, 1, 1)
        grid_r.addWidget(QLabel("Angsuran Jasa (+):"), 1, 2)
        grid_r.addWidget(self.lbl_angs_jasa, 1, 3)
        grid_r.addWidget(QLabel("Pencairan Pinjaman (-):"), 1, 4)
        grid_r.addWidget(self.lbl_pinj_cair, 1, 5)

        grid_r.addWidget(QLabel("Biaya Admin (+):"), 2, 0)
        grid_r.addWidget(self.lbl_admin, 2, 1)
        grid_r.addWidget(QLabel("Koreksi / Pembatalan:"), 2, 2)
        grid_r.addWidget(self.lbl_koreksi, 2, 3)

        grid_r.addWidget(QLabel("<b>Total Kas Masuk:</b>"), 3, 0)
        grid_r.addWidget(self.lbl_kas_masuk, 3, 1)
        grid_r.addWidget(QLabel("<b>Total Kas Keluar:</b>"), 3, 2)
        grid_r.addWidget(self.lbl_kas_keluar, 3, 3)
        grid_r.addWidget(QLabel("<b>Saldo Kas Akhir:</b>"), 3, 4)
        grid_r.addWidget(self.lbl_kas_akhir, 3, 5)

        layout.addWidget(box_ringkasan)

        # Baris Opsi Tampilan & Tabel Transaksi Rinci
        baris_tabel_head = QHBoxLayout()
        baris_tabel_head.addWidget(QLabel("Daftar Transaksi Buku Kas Periode:"))
        baris_tabel_head.addStretch()
        self.chk_sembunyikan_dibatalkan = QCheckBox("Sembunyikan transaksi yang sudah dibatalkan", self)
        self.chk_sembunyikan_dibatalkan.setChecked(True)
        self.chk_sembunyikan_dibatalkan.toggled.connect(self.muat_data)
        baris_tabel_head.addWidget(self.chk_sembunyikan_dibatalkan)
        layout.addLayout(baris_tabel_head)

        self.tabel = QTableWidget(self)
        self.tabel.setFont(QFont("Segoe UI", 11))
        self.tabel.setColumnCount(7)
        self.tabel.setHorizontalHeaderLabels([
            "No", "Tanggal", "Keterangan Transaksi", "Masuk (Rp)", "Keluar (Rp)", "Sumber", "Status"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 50)   # No
        self.tabel.setColumnWidth(1, 115)  # Tanggal
        self.tabel.setColumnWidth(3, 135)  # Masuk (Rp)
        self.tabel.setColumnWidth(4, 135)  # Keluar (Rp)
        self.tabel.setColumnWidth(5, 120)  # Sumber
        self.tabel.setColumnWidth(6, 120)  # Status
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setDefaultSectionSize(36)
        layout.addWidget(self.tabel)

        self.muat_data()

    def _pilih_minggu_ini(self) -> None:
        awal, akhir = tentukan_rentang_minggu(date.today())
        self.input_tgl_awal.setDate(QDate(awal.year, awal.month, awal.day))
        self.input_tgl_akhir.setDate(QDate(akhir.year, akhir.month, akhir.day))
        self.muat_data()

    def _pilih_minggu_lalu(self) -> None:
        from datetime import timedelta
        awal, akhir = tentukan_rentang_minggu(date.today() - timedelta(days=7))
        self.input_tgl_awal.setDate(QDate(awal.year, awal.month, awal.day))
        self.input_tgl_akhir.setDate(QDate(akhir.year, akhir.month, akhir.day))
        self.muat_data()

    def muat_data(self) -> None:
        tgl_awal_iso = self.input_tgl_awal.date().toString("yyyy-MM-dd")
        tgl_akhir_iso = self.input_tgl_akhir.date().toString("yyyy-MM-dd")
        sembunyikan = self.chk_sembunyikan_dibatalkan.isChecked()

        # Ambil data sekaligus mencatat log laporan
        data = ambil_data_laporan_mingguan(
            self.conn, tgl_awal_iso, tgl_akhir_iso, catat_log=True, sembunyikan_dibatalkan=sembunyikan
        )
        self.laporan_data = data

        # Tampilkan ke ringkasan arus kas
        self.lbl_kas_awal.setText(format_rupiah(data["saldo_kas_awal"]))
        self.lbl_simp_masuk.setText(format_rupiah(data["total_simpanan_setor"]))
        self.lbl_simp_keluar.setText(format_rupiah(data["total_simpanan_tarik"]))
        self.lbl_angs_pokok.setText(format_rupiah(data["total_angsuran_pokok"]))
        self.lbl_angs_jasa.setText(format_rupiah(data["total_angsuran_jasa"]))
        self.lbl_pinj_cair.setText(format_rupiah(data["total_pinjaman_cair"]))
        self.lbl_admin.setText(format_rupiah(data.get("total_biaya_admin", 0)))

        # Info koreksi lintas jika ada
        jml_koreksi = data.get("jumlah_koreksi_lintas", 0)
        if jml_koreksi > 0:
            self.lbl_koreksi.setText(f"{jml_koreksi} transaksi")
            self.lbl_koreksi.setStyleSheet("color: #D97706; font-weight: bold;")
        else:
            self.lbl_koreksi.setText("-")
            self.lbl_koreksi.setStyleSheet("")

        self.lbl_kas_masuk.setText(format_rupiah(data["total_kas_masuk"]))
        self.lbl_kas_keluar.setText(format_rupiah(data["total_kas_keluar"]))
        self.lbl_kas_akhir.setText(format_rupiah(data["saldo_kas_akhir"]))

        # Tampilkan tabel transaksi
        tx_list = data["daftar_transaksi"]
        self.tabel.setRowCount(len(tx_list))

        for b, r in enumerate(tx_list):
            self.tabel.setItem(b, 0, QTableWidgetItem(str(b + 1)))
            self.tabel.setItem(b, 1, QTableWidgetItem(format_tanggal_indo(r["tanggal"])))
            
            ket_item = QTableWidgetItem(r["keterangan"])
            self.tabel.setItem(b, 2, ket_item)

            m_item = QTableWidgetItem(format_rupiah(r["masuk"]) if r["masuk"] > 0 else "-")
            m_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(b, 3, m_item)

            k_item = QTableWidgetItem(format_rupiah(r["keluar"]) if r["keluar"] > 0 else "-")
            k_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(b, 4, k_item)

            self.tabel.setItem(b, 5, QTableWidgetItem(r["sumber"].capitalize()))

            stat = r.get("status_klasifikasi", "NORMAL")
            stat_item = QTableWidgetItem(stat)
            if stat == "DIBATALKAN":
                stat_item.setForeground(Qt.GlobalColor.gray)
                ket_item.setForeground(Qt.GlobalColor.gray)
            elif stat == "KOREKSI":
                stat_item.setForeground(Qt.GlobalColor.darkYellow)
            else:
                stat_item.setForeground(Qt.GlobalColor.darkGreen)
            self.tabel.setItem(b, 6, stat_item)

    def _ekspor_excel(self) -> None:
        if not self.laporan_data:
            return

        tgl_awal = self.laporan_data["tanggal_awal"]
        tgl_akhir = self.laporan_data["tanggal_akhir"]
        nama_file_default = f"Laporan_Mingguan_{tgl_awal}_sd_{tgl_akhir}.xlsx"

        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Simpan Laporan Excel", nama_file_default, "Excel Files (*.xlsx)"
        )
        if not path_simpan:
            return

        kolom = ["No", "Tanggal", "Keterangan Transaksi", "Masuk (Rp)", "Keluar (Rp)", "Sumber"]
        baris_data = []
        for idx, r in enumerate(self.laporan_data["daftar_transaksi"], start=1):
            baris_data.append([
                idx, r["tanggal"], r["keterangan"], r["masuk"], r["keluar"], r["sumber"]
            ])

        baris_tot = [
            "TOTAL", "", "",
            self.laporan_data["total_kas_masuk"],
            self.laporan_data["total_kas_keluar"],
            f"Saldo Akhir: {format_rupiah(self.laporan_data['saldo_kas_akhir'])}"
        ]
        judul = f"LAPORAN MINGGUAN KOPERASI ({format_tanggal_indo(tgl_awal)} s/d {format_tanggal_indo(tgl_akhir)})"

        try:
            ekspor_tabel_ke_excel(judul, kolom, baris_data, path_simpan, baris_tot)
            QMessageBox.information(self, "Ekspor Berhasil", f"Laporan Excel berhasil disimpan ke:\n{path_simpan}")
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal mengekspor data: {err}")

    def _ekspor_pdf(self) -> None:
        if not self.laporan_data:
            return

        tgl_awal = self.laporan_data["tanggal_awal"]
        tgl_akhir = self.laporan_data["tanggal_akhir"]
        nama_file_default = f"Laporan_Mingguan_{tgl_awal}_sd_{tgl_akhir}.pdf"

        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Simpan Laporan PDF", nama_file_default, "PDF Files (*.pdf)"
        )
        if not path_simpan:
            return

        metrik = [
            ("Saldo Kas Awal", format_rupiah(self.laporan_data["saldo_kas_awal"])),
            ("Total Simpanan Setor", format_rupiah(self.laporan_data["total_simpanan_setor"])),
            ("Total Simpanan Tarik", format_rupiah(self.laporan_data["total_simpanan_tarik"])),
            ("Total Angsuran Pokok", format_rupiah(self.laporan_data["total_angsuran_pokok"])),
            ("Total Angsuran Jasa", format_rupiah(self.laporan_data["total_angsuran_jasa"])),
            ("Total Pencairan Pinjaman", format_rupiah(self.laporan_data["total_pinjaman_cair"])),
            ("Total Biaya Admin", format_rupiah(self.laporan_data.get("total_biaya_admin", 0))),
            ("Koreksi / Pembatalan", f"{self.laporan_data.get('jumlah_koreksi_lintas', 0)} transaksi"),
            ("Total Kas Masuk", format_rupiah(self.laporan_data["total_kas_masuk"])),
            ("Total Kas Keluar", format_rupiah(self.laporan_data["total_kas_keluar"])),
            ("Saldo Kas Akhir", format_rupiah(self.laporan_data["saldo_kas_akhir"]))
        ]

        kolom = ["No", "Tanggal", "Keterangan", "Masuk (Rp)", "Keluar (Rp)", "Sumber", "Status"]
        baris_tabel = []
        for idx, r in enumerate(self.laporan_data["daftar_transaksi"], start=1):
            baris_tabel.append([
                str(idx),
                format_tanggal_indo(r["tanggal"]),
                r["keterangan"][:35],
                format_rupiah(r["masuk"]) if r["masuk"] > 0 else "-",
                format_rupiah(r["keluar"]) if r["keluar"] > 0 else "-",
                r["sumber"],
                r.get("status_klasifikasi", "NORMAL")
            ])

        try:
            ekspor_laporan_ke_pdf(
                "LAPORAN MINGGUAN KOPERASI",
                f"{format_tanggal_indo(tgl_awal)} s/d {format_tanggal_indo(tgl_akhir)}",
                metrik,
                kolom,
                baris_tabel,
                path_simpan
            )
            QMessageBox.information(self, "Ekspor Berhasil", f"Laporan PDF berhasil disimpan ke:\n{path_simpan}")
        except Exception as err:
            QMessageBox.critical(self, "Gagal", f"Gagal mengekspor PDF: {err}")

