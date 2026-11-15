"""
app/ui/layar_laporan_bulanan.py — Layar Laporan Bulanan Koperasi.
Menampilkan ringkasan arus kas, mutasi simpanan per jenis, statistik pinjaman,
keanggotaan, tunggakan akhir bulan, perbandingan dengan bulan sebelumnya,
transaksi rinci, serta ekspor Excel dan PDF.
"""
import sqlite3
from datetime import date
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
    QFileDialog, QMessageBox, QGroupBox, QGridLayout, QCheckBox,
    QScrollArea
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QThread, Signal

from app.db.repo_laporan_periode import (
    ambil_daftar_tahun_tersedia, ambil_data_laporan_bulanan, NAMA_BULAN_INDO
)
from app.util.format import format_rupiah, format_tanggal_indo
from app.layanan.ekspor_laporan_periode import (
    ekspor_laporan_bulanan_excel, ekspor_laporan_bulanan_pdf
)


class WorkerMuatBulanan(QThread):
    selesai = Signal(dict)
    gagal = Signal(str)

    def __init__(self, db_path: str, tahun: int, bulan: int, sembunyikan_dibatalkan: bool):
        super().__init__()
        self.db_path = db_path
        self.tahun = tahun
        self.bulan = bulan
        self.sembunyikan_dibatalkan = sembunyikan_dibatalkan

    def run(self):
        try:
            from app.db.koneksi import buka_koneksi
            conn = buka_koneksi(self.db_path)
            try:
                res = ambil_data_laporan_bulanan(
                    conn, self.tahun, self.bulan, self.sembunyikan_dibatalkan
                )
                self.selesai.emit(res)
            finally:
                conn.close()
        except Exception as e:
            self.gagal.emit(str(e))


class LayarLaporanBulanan(QWidget):
    """Layar Laporan Keuangan Bulanan."""

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

        # Header: Judul & Tombol Ekspor
        header_layout = QHBoxLayout()
        self.label_judul = QLabel("Laporan Keuangan Bulanan", self)
        self.label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(self.label_judul)

        self.lbl_status_badge = QLabel("", self)
        self.lbl_status_badge.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        header_layout.addWidget(self.lbl_status_badge)

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

        # Filter Bar: Bulan, Tahun, Tombol Tampilkan
        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Pilih Periode Bulan:"))

        self.combo_bulan = QComboBox(self)
        for i in range(1, 13):
            self.combo_bulan.addItem(NAMA_BULAN_INDO[i], i)
        thn_skrg = date.today().year
        bln_skrg = date.today().month
        self.combo_bulan.setCurrentIndex(bln_skrg - 1)
        filter_bar.addWidget(self.combo_bulan)

        self.combo_tahun = QComboBox(self)
        daftar_thn = ambil_daftar_tahun_tersedia(self.conn)
        for t in daftar_thn:
            self.combo_tahun.addItem(str(t), t)
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

        # Warning / Rekonsiliasi Banner
        self.lbl_warning = QLabel(self)
        self.lbl_warning.setStyleSheet("background-color: #FEF3C7; color: #92400E; padding: 8px 12px; border-radius: 6px; font-weight: bold;")
        self.lbl_warning.hide()
        layout.addWidget(self.lbl_warning)

        # Area Scrollable untuk Konten Laporan
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        konten_widget = QWidget()
        konten_layout = QVBoxLayout(konten_widget)
        konten_layout.setContentsMargins(0, 0, 0, 0)
        konten_layout.setSpacing(12)

        # 1. Box Arus Kas
        box_kas = QGroupBox("1. Ringkasan Arus Kas Bersih", konten_widget)
        grid_k = QGridLayout(box_kas)
        self.lbl_kas_awal = QLabel("Rp 0")
        self.lbl_kas_masuk = QLabel("Rp 0")
        self.lbl_kas_keluar = QLabel("Rp 0")
        self.lbl_kas_akhir = QLabel("Rp 0")
        self.lbl_kas_akhir.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_kas_akhir.setStyleSheet("color: #1E3A8A;")

        self.lbl_koreksi = QLabel("0 Transaksi (Rp 0)")

        grid_k.addWidget(QLabel("Saldo Kas Awal:"), 0, 0)
        grid_k.addWidget(self.lbl_kas_awal, 0, 1)
        grid_k.addWidget(QLabel("Total Kas Masuk (+):"), 0, 2)
        grid_k.addWidget(self.lbl_kas_masuk, 0, 3)
        grid_k.addWidget(QLabel("Total Kas Keluar (-):"), 1, 0)
        grid_k.addWidget(self.lbl_kas_keluar, 1, 1)
        grid_k.addWidget(QLabel("<b>Saldo Kas Akhir:</b>"), 1, 2)
        grid_k.addWidget(self.lbl_kas_akhir, 1, 3)
        grid_k.addWidget(QLabel("Koreksi / Pembatalan:"), 2, 0)
        grid_k.addWidget(self.lbl_koreksi, 2, 1, 1, 3)
        konten_layout.addWidget(box_kas)

        # 2. Box Mutasi Simpanan
        box_simp = QGroupBox("2. Mutasi dan Saldo Simpanan Anggota", konten_widget)
        v_simp = QVBoxLayout(box_simp)
        self.tabel_simpanan = QTableWidget(box_simp)
        self.tabel_simpanan.setColumnCount(4)
        self.tabel_simpanan.setHorizontalHeaderLabels(["Jenis Simpanan", "Setoran Bulan Ini", "Penarikan Bulan Ini", "Saldo Akhir Bulan"])
        self.tabel_simpanan.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel_simpanan.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabel_simpanan.setColumnWidth(1, 140)
        self.tabel_simpanan.setColumnWidth(2, 140)
        self.tabel_simpanan.setColumnWidth(3, 160)
        self.tabel_simpanan.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel_simpanan.setAlternatingRowColors(True)
        self.tabel_simpanan.setFixedHeight(160)
        v_simp.addWidget(self.tabel_simpanan)
        konten_layout.addWidget(box_simp)

        # 3. Box Pinjaman & Keanggotaan
        box_pj_ag = QGroupBox("3. Pinjaman, Jasa, dan Keanggotaan", konten_widget)
        grid_pa = QGridLayout(box_pj_ag)
        self.lbl_pinj_cair = QLabel("0 Pinjaman (Rp 0)")
        self.lbl_angs_pokok = QLabel("Rp 0")
        self.lbl_jasa_admin = QLabel("Rp 0 / Rp 0")
        self.lbl_sisa_pokok = QLabel("Rp 0")
        self.lbl_pinj_aktif = QLabel("0 Pinjaman Berjalan")
        self.lbl_anggota_mutasi = QLabel("Baru: 0 | Keluar: 0")
        self.lbl_anggota_aktif = QLabel("0 Orang")
        self.lbl_anggota_aktif.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        grid_pa.addWidget(QLabel("Pinjaman Cair Bulan Ini:"), 0, 0)
        grid_pa.addWidget(self.lbl_pinj_cair, 0, 1)
        grid_pa.addWidget(QLabel("Angsuran Pokok Masuk:"), 0, 2)
        grid_pa.addWidget(self.lbl_angs_pokok, 0, 3)

        grid_pa.addWidget(QLabel("Jasa Diterima / Admin:"), 1, 0)
        grid_pa.addWidget(self.lbl_jasa_admin, 1, 1)
        grid_pa.addWidget(QLabel("Sisa Pokok Beredar:"), 1, 2)
        grid_pa.addWidget(self.lbl_sisa_pokok, 1, 3)

        grid_pa.addWidget(QLabel("Pinjaman Aktif:"), 2, 0)
        grid_pa.addWidget(self.lbl_pinj_aktif, 2, 1)
        grid_pa.addWidget(QLabel("Mutasi Anggota:"), 2, 2)
        grid_pa.addWidget(self.lbl_anggota_mutasi, 2, 3)

        grid_pa.addWidget(QLabel("<b>Total Anggota Aktif:</b>"), 3, 0)
        grid_pa.addWidget(self.lbl_anggota_aktif, 3, 1)
        konten_layout.addWidget(box_pj_ag)

        # 4. Box Perbandingan Bulan Lalu
        box_pb = QGroupBox("4. Perbandingan dengan Bulan Sebelumnya", konten_widget)
        v_pb = QVBoxLayout(box_pb)
        self.tabel_perbandingan = QTableWidget(box_pb)
        self.tabel_perbandingan.setColumnCount(5)
        self.tabel_perbandingan.setHorizontalHeaderLabels(["Indikator Keuangan", "Bulan Ini", "Bulan Lalu", "Selisih (Rp)", "Pertumbuhan (%)"])
        self.tabel_perbandingan.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel_perbandingan.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tabel_perbandingan.setColumnWidth(1, 140)
        self.tabel_perbandingan.setColumnWidth(2, 140)
        self.tabel_perbandingan.setColumnWidth(3, 140)
        self.tabel_perbandingan.setColumnWidth(4, 120)
        self.tabel_perbandingan.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel_perbandingan.setAlternatingRowColors(True)
        self.tabel_perbandingan.setFixedHeight(185)
        v_pb.addWidget(self.tabel_perbandingan)
        konten_layout.addWidget(box_pb)

        # 5. Box Tunggakan Akhir Bulan
        box_tg = QGroupBox("5. Daftar Anggota Menunggak pada Akhir Bulan", konten_widget)
        v_tg = QVBoxLayout(box_tg)
        self.lbl_info_tunggakan = QLabel("0 Anggota Menunggak — Total: Rp 0", box_tg)
        self.lbl_info_tunggakan.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_info_tunggakan.setStyleSheet("color: #DC2626;")
        v_tg.addWidget(self.lbl_info_tunggakan)

        self.tabel_tunggakan = QTableWidget(box_tg)
        self.tabel_tunggakan.setColumnCount(6)
        self.tabel_tunggakan.setHorizontalHeaderLabels(["No. Anggota", "Nama Anggota", "Unit", "No. Pinjaman", "Cicilan Telat", "Total Tunggakan"])
        self.tabel_tunggakan.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel_tunggakan.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabel_tunggakan.setColumnWidth(0, 110)
        self.tabel_tunggakan.setColumnWidth(2, 100)
        self.tabel_tunggakan.setColumnWidth(3, 115)
        self.tabel_tunggakan.setColumnWidth(4, 90)
        self.tabel_tunggakan.setColumnWidth(5, 140)
        self.tabel_tunggakan.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel_tunggakan.setAlternatingRowColors(True)
        self.tabel_tunggakan.setFixedHeight(160)
        v_tg.addWidget(self.tabel_tunggakan)
        konten_layout.addWidget(box_tg)

        # 6. Box Transaksi Kas Rinci
        box_tx = QGroupBox("6. Daftar Transaksi Kas Selama Bulan Ini", konten_widget)
        v_tx = QVBoxLayout(box_tx)
        baris_tx_top = QHBoxLayout()
        self.chk_sembunyikan_batal = QCheckBox("Sembunyikan transaksi yang sudah dibatalkan", box_tx)
        self.chk_sembunyikan_batal.setChecked(True)
        self.chk_sembunyikan_batal.toggled.connect(self.muat_data)
        baris_tx_top.addStretch()
        baris_tx_top.addWidget(self.chk_sembunyikan_batal)
        v_tx.addLayout(baris_tx_top)

        self.tabel_transaksi = QTableWidget(box_tx)
        self.tabel_transaksi.setColumnCount(7)
        self.tabel_transaksi.setHorizontalHeaderLabels(["No", "Tanggal", "Keterangan", "Masuk (Rp)", "Keluar (Rp)", "Sumber", "Status"])
        self.tabel_transaksi.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel_transaksi.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabel_transaksi.setColumnWidth(0, 45)
        self.tabel_transaksi.setColumnWidth(1, 105)
        self.tabel_transaksi.setColumnWidth(3, 130)
        self.tabel_transaksi.setColumnWidth(4, 130)
        self.tabel_transaksi.setColumnWidth(5, 110)
        self.tabel_transaksi.setColumnWidth(6, 110)
        self.tabel_transaksi.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel_transaksi.setAlternatingRowColors(True)
        self.tabel_transaksi.setFixedHeight(220)
        v_tx.addWidget(self.tabel_transaksi)
        konten_layout.addWidget(box_tx)

        scroll.setWidget(konten_widget)
        layout.addWidget(scroll, 1)

        self.muat_data()

    def muat_data(self) -> None:
        bulan = self.combo_bulan.currentData() or date.today().month
        tahun = self.combo_tahun.currentData() or date.today().year
        sembunyi = self.chk_sembunyikan_batal.isChecked()

        self.lbl_loading.setText("Memuat laporan bulanan...")
        self.btn_ekspor_excel.setEnabled(False)
        self.btn_ekspor_pdf.setEnabled(False)

        self.worker = WorkerMuatBulanan(self.db_path, tahun, bulan, sembunyi)
        self.worker.selesai.connect(self._on_data_termuat)
        self.worker.gagal.connect(self._on_gagal_muat)
        self.worker.start()

    def _on_data_termuat(self, data: dict) -> None:
        self.lbl_loading.setText("")
        self.btn_ekspor_excel.setEnabled(True)
        self.btn_ekspor_pdf.setEnabled(True)
        self.data_laporan = data

        # Status badge
        if data["sudah_closing"]:
            self.lbl_status_badge.setText(" [TUTUP BUKU / FINAL] ")
            self.lbl_status_badge.setStyleSheet("color: #059669; background-color: #ECFDF5; padding: 4px 8px; border-radius: 4px;")
        else:
            self.lbl_status_badge.setText(" [SEMENTARA (belum closing)] ")
            self.lbl_status_badge.setStyleSheet("color: #D97706; background-color: #FEF3C7; padding: 4px 8px; border-radius: 4px;")

        # Rekonsiliasi banner
        if not data["rekonsiliasi_cocok"]:
            self.lbl_warning.setText(data["pesan_rekonsiliasi"])
            self.lbl_warning.show()
        else:
            self.lbl_warning.hide()

        # 1. Arus Kas
        self.lbl_kas_awal.setText(format_rupiah(data["saldo_kas_awal"]))
        self.lbl_kas_masuk.setText(format_rupiah(data["total_kas_masuk"]))
        self.lbl_kas_keluar.setText(format_rupiah(data["total_kas_keluar"]))
        self.lbl_kas_akhir.setText(format_rupiah(data["saldo_kas_akhir"]))
        self.lbl_koreksi.setText(f"{data['koreksi']['jumlah']} Koreksi (Masuk: {format_rupiah(data['koreksi']['masuk'])} | Keluar: {format_rupiah(data['koreksi']['keluar'])})")

        # 2. Mutasi Simpanan
        simp = data["simpanan"]
        baris_simp = [
            ("Simpanan Pokok", simp["pokok"]["setor"], simp["pokok"]["tarik"], simp["pokok"]["saldo_akhir"]),
            ("Simpanan Wajib", simp["wajib"]["setor"], simp["wajib"]["tarik"], simp["wajib"]["saldo_akhir"]),
            ("Simpanan Sukarela", simp["sukarela"]["setor"], simp["sukarela"]["tarik"], simp["sukarela"]["saldo_akhir"]),
            ("Total Seluruh Simpanan", simp["total"]["setor"], simp["total"]["tarik"], simp["total"]["saldo_akhir"]),
        ]
        self.tabel_simpanan.setRowCount(len(baris_simp))
        for r_idx, (jns, st, tr, sk) in enumerate(baris_simp):
            it_jns = QTableWidgetItem(jns)
            it_st = QTableWidgetItem(format_rupiah(st))
            it_tr = QTableWidgetItem(format_rupiah(tr))
            it_sk = QTableWidgetItem(format_rupiah(sk))
            for it in (it_st, it_tr, it_sk):
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if r_idx == 3:
                f_bold = QFont("Segoe UI", 11, QFont.Weight.Bold)
                for it in (it_jns, it_st, it_tr, it_sk):
                    it.setFont(f_bold)
            self.tabel_simpanan.setItem(r_idx, 0, it_jns)
            self.tabel_simpanan.setItem(r_idx, 1, it_st)
            self.tabel_simpanan.setItem(r_idx, 2, it_tr)
            self.tabel_simpanan.setItem(r_idx, 3, it_sk)

        # 3. Pinjaman & Keanggotaan
        pj = data["pinjaman"]
        ag = data["anggota"]
        self.lbl_pinj_cair.setText(f"{pj['cair_jumlah']} Pinjaman ({format_rupiah(pj['cair_nominal'])})")
        self.lbl_angs_pokok.setText(format_rupiah(pj["angsuran_pokok"]))
        self.lbl_jasa_admin.setText(f"{format_rupiah(pj['jasa_diterima'])} / {format_rupiah(pj['biaya_admin'])}")
        self.lbl_sisa_pokok.setText(format_rupiah(pj["sisa_pokok_akhir"]))
        self.lbl_pinj_aktif.setText(f"{pj['pinjaman_aktif_jumlah']} Pinjaman Berjalan")
        self.lbl_anggota_mutasi.setText(f"Baru: {ag['baru']} | Keluar: {ag['keluar']}")
        self.lbl_anggota_aktif.setText(f"{ag['aktif_akhir']} Orang")

        # 4. Perbandingan Bulan Lalu
        pb = data["perbandingan"]
        baris_pb = [
            ("Total Kas Masuk", pb["kas_masuk"]["kini"], pb["kas_masuk"]["lalu"], pb["kas_masuk"]["selisih"], pb["kas_masuk"]["persen_str"]),
            ("Total Kas Keluar", pb["kas_keluar"]["kini"], pb["kas_keluar"]["lalu"], pb["kas_keluar"]["selisih"], pb["kas_keluar"]["persen_str"]),
            ("Setoran Simpanan Masuk", pb["simpanan"]["kini"], pb["simpanan"]["lalu"], pb["simpanan"]["selisih"], pb["simpanan"]["persen_str"]),
            ("Pencairan Pinjaman", pb["pinjaman_cair"]["kini"], pb["pinjaman_cair"]["lalu"], pb["pinjaman_cair"]["selisih"], pb["pinjaman_cair"]["persen_str"]),
            ("Jasa Pinjaman Diterima", pb["jasa_diterima"]["kini"], pb["jasa_diterima"]["lalu"], pb["jasa_diterima"]["selisih"], pb["jasa_diterima"]["persen_str"]),
        ]
        self.tabel_perbandingan.setRowCount(len(baris_pb))
        for r_idx, (ind, kini, lalu, slsh, pct) in enumerate(baris_pb):
            it_ind = QTableWidgetItem(ind)
            it_kini = QTableWidgetItem(format_rupiah(kini))
            it_lalu = QTableWidgetItem(format_rupiah(lalu))
            it_slsh = QTableWidgetItem(format_rupiah(slsh))
            it_pct = QTableWidgetItem(pct)
            for it in (it_kini, it_lalu, it_slsh, it_pct):
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel_perbandingan.setItem(r_idx, 0, it_ind)
            self.tabel_perbandingan.setItem(r_idx, 1, it_kini)
            self.tabel_perbandingan.setItem(r_idx, 2, it_lalu)
            self.tabel_perbandingan.setItem(r_idx, 3, it_slsh)
            self.tabel_perbandingan.setItem(r_idx, 4, it_pct)

        # 5. Tunggakan Akhir Bulan
        tg = data["tunggakan"]
        self.lbl_info_tunggakan.setText(f"{tg['jumlah_anggota']} Anggota Menunggak — Total Tunggakan: {format_rupiah(tg['total_nominal'])}")
        self.tabel_tunggakan.setRowCount(len(tg["daftar"]))
        for r_idx, item in enumerate(tg["daftar"]):
            it_no = QTableWidgetItem(item["no_anggota"])
            it_nm = QTableWidgetItem(item["nama_anggota"])
            it_un = QTableWidgetItem(item["unit"])
            it_pj = QTableWidgetItem(item["no_pinjaman"])
            it_cl = QTableWidgetItem(f"{item['jumlah_cicilan_telat']}x")
            it_tt = QTableWidgetItem(format_rupiah(item["total_tunggakan"]))
            it_cl.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_tt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel_tunggakan.setItem(r_idx, 0, it_no)
            self.tabel_tunggakan.setItem(r_idx, 1, it_nm)
            self.tabel_tunggakan.setItem(r_idx, 2, it_un)
            self.tabel_tunggakan.setItem(r_idx, 3, it_pj)
            self.tabel_tunggakan.setItem(r_idx, 4, it_cl)
            self.tabel_tunggakan.setItem(r_idx, 5, it_tt)

        # 6. Transaksi Kas Rinci
        txs = data["transaksi_rinci"]
        self.tabel_transaksi.setRowCount(len(txs))
        for r_idx, tx in enumerate(txs):
            it_no = QTableWidgetItem(str(r_idx + 1))
            it_tg = QTableWidgetItem(format_tanggal_indo(tx["tanggal"]))
            it_kt = QTableWidgetItem(tx["keterangan"])
            it_ms = QTableWidgetItem(format_rupiah(tx["masuk"]) if tx["masuk"] > 0 else "-")
            it_kl = QTableWidgetItem(format_rupiah(tx["keluar"]) if tx["keluar"] > 0 else "-")
            it_sb = QTableWidgetItem(tx["sumber"])
            it_st = QTableWidgetItem(tx["status_klasifikasi"])

            it_ms.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            it_kl.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            if tx["status_klasifikasi"] in ("DIBATALKAN", "KOREKSI"):
                for it in (it_no, it_tg, it_kt, it_ms, it_kl, it_sb, it_st):
                    it.setForeground(Qt.GlobalColor.gray)

            self.tabel_transaksi.setItem(r_idx, 0, it_no)
            self.tabel_transaksi.setItem(r_idx, 1, it_tg)
            self.tabel_transaksi.setItem(r_idx, 2, it_kt)
            self.tabel_transaksi.setItem(r_idx, 3, it_ms)
            self.tabel_transaksi.setItem(r_idx, 4, it_kl)
            self.tabel_transaksi.setItem(r_idx, 5, it_sb)
            self.tabel_transaksi.setItem(r_idx, 6, it_st)

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
        nama_file_def = f"Laporan_Bulanan_{self.data_laporan['periode']}.xlsx"
        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Ekspor Laporan Bulanan ke Excel", nama_file_def, "Excel Files (*.xlsx)"
        )
        if not path_simpan:
            return
        try:
            ekspor_laporan_bulanan_excel(self.data_laporan, nama_kop, path_simpan)
            QMessageBox.information(self, "Berhasil", f"Laporan bulanan tersimpan di:\n{path_simpan}")
        except Exception as e:
            QMessageBox.critical(self, "Gagal Ekspor", f"Terjadi kesalahan: {e}")

    def _ekspor_pdf(self) -> None:
        if not self.data_laporan:
            return
        nama_kop = self._ambil_nama_koperasi()
        nama_file_def = f"Laporan_Bulanan_{self.data_laporan['periode']}.pdf"
        path_simpan, _ = QFileDialog.getSaveFileName(
            self, "Ekspor Laporan Bulanan ke PDF", nama_file_def, "PDF Files (*.pdf)"
        )
        if not path_simpan:
            return
        try:
            ekspor_laporan_bulanan_pdf(self.data_laporan, nama_kop, path_simpan)
            QMessageBox.information(self, "Berhasil", f"Laporan bulanan PDF tersimpan di:\n{path_simpan}")
        except Exception as e:
            QMessageBox.critical(self, "Gagal Ekspor", f"Terjadi kesalahan: {e}")

