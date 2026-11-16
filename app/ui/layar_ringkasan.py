"""
app/ui/layar_ringkasan.py — Layar Ringkasan / Dashboard Halaman Awal (SPEC.md 4.1).
Prinsip antarmuka:
- Font besar (12-14 pt), tombol minimal tinggi 42-48 px
- Kotak besar: Simpanan Masuk Hari Ini, Angsuran Masuk Hari Ini, Pinjaman Cair Hari Ini, Posisi Kas Saat Ini
- Kotak peringatan: Angsuran jatuh tempo minggu ini & Anggota menunggak (+ tombol lihat)
- Baris Pengingat: Laporan mingguan belum dibuat, Closing bulan ini belum dilakukan
- Tombol Aksi Cepat Besar: Input Simpanan, Input Angsuran, Pinjaman Baru, Cari Anggota, Laporan, Closing
"""
import sqlite3
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QGroupBox, QDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from app.db.repo_ringkasan import ambil_ringkasan_dashboard
from app.layanan.backup import ambil_info_backup_terakhir
from app.util.format import format_rupiah, format_tanggal_indo


class LayarRingkasan(QWidget):
    """Layar Ringkasan Utama (Dashboard)."""

    def __init__(self, conn: sqlite3.Connection, callback_navigasi, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.navigasi = callback_navigasi
        self.data_dashboard = {}
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 15, 20, 20)
        layout.setSpacing(14)

        # 1. Header & Status Backup
        header_layout = QHBoxLayout()
        label_judul = QLabel("Ringkasan Koperasi Simpan Pinjam", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(label_judul)

        header_layout.addStretch()

        self.lbl_backup_info = QLabel("Backup terakhir: -", self)
        self.lbl_backup_info.setStyleSheet("color: #4B5563; font-size: 11pt;")
        header_layout.addWidget(self.lbl_backup_info)

        btn_segarkan = QPushButton("Segarkan", self)
        btn_segarkan.setMinimumHeight(38)
        btn_segarkan.setStyleSheet(
            "background-color: #EFF6FF; color: #1D4ED8; border: 1.5px solid #93C5FD; "
            "font-weight: bold; border-radius: 6px; padding: 0 16px;"
        )
        btn_segarkan.clicked.connect(self.muat_data)
        header_layout.addWidget(btn_segarkan)

        layout.addLayout(header_layout)

        # 2. Kotak Pengingat Penting (Banner Alert)
        self.box_pengingat = QWidget(self)
        self.layout_pengingat = QVBoxLayout(self.box_pengingat)
        self.layout_pengingat.setContentsMargins(0, 0, 0, 0)
        self.layout_pengingat.setSpacing(6)
        layout.addWidget(self.box_pengingat)

        # 3. Kotak Besar Metrik Keuangan Hari Ini (Grid)
        grid_metrik = QGridLayout()
        grid_metrik.setSpacing(12)

        self.card_simpanan = self._buat_kartu_metrik(
            "SIMPANAN MASUK HARI INI", "Rp 0", "#059669", "#ECFDF5"
        )
        self.card_angsuran = self._buat_kartu_metrik(
            "ANGSURAN MASUK HARI INI", "Rp 0", "#2563EB", "#EFF6FF"
        )
        self.card_pinjaman = self._buat_kartu_metrik(
            "PINJAMAN CAIR HARI INI", "Rp 0", "#D97706", "#FFFBEB"
        )
        self.card_admin = self._buat_kartu_metrik(
            "BIAYA ADMIN DITERIMA (+)", "Rp 0", "#0D9488", "#F0FDFA"
        )
        self.card_kas = self._buat_kartu_metrik(
            "POSISI KAS OPERASIONAL", "Rp 0", "#4B5563", "#F3F4F6"
        )

        grid_metrik.addWidget(self.card_simpanan["widget"], 0, 0)
        grid_metrik.addWidget(self.card_angsuran["widget"], 0, 1)
        grid_metrik.addWidget(self.card_pinjaman["widget"], 0, 2)
        grid_metrik.addWidget(self.card_admin["widget"], 1, 0)
        grid_metrik.addWidget(self.card_kas["widget"], 1, 1, 1, 2)

        layout.addLayout(grid_metrik)

        # 4. Baris Informasi Pengingat Jatuh Tempo & Menunggak
        baris_peringatan = QHBoxLayout()

        # Kotak Jatuh Tempo Minggu Ini
        box_tempo = QGroupBox("Jatuh Tempo Minggu Ini", self)
        layout_tempo = QHBoxLayout(box_tempo)
        self.lbl_tempo_info = QLabel("0 Angsuran", box_tempo)
        self.lbl_tempo_info.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        btn_lihat_tempo = QPushButton("Lihat Daftar", box_tempo)
        btn_lihat_tempo.setMinimumHeight(38)
        btn_lihat_tempo.setStyleSheet(
            "background-color: #EFF6FF; color: #1D4ED8; border: 1.5px solid #93C5FD; "
            "font-weight: bold; border-radius: 6px; padding: 0 16px;"
        )
        btn_lihat_tempo.clicked.connect(self._lihat_daftar_tempo)
        layout_tempo.addWidget(self.lbl_tempo_info)
        layout_tempo.addStretch()
        layout_tempo.addWidget(btn_lihat_tempo)
        baris_peringatan.addWidget(box_tempo, 1)

        # Kotak Anggota Menunggak
        box_tunggakan = QGroupBox("Anggota Menunggak", self)
        box_tunggakan.setStyleSheet("QGroupBox { color: #DC2626; font-weight: bold; }")
        layout_tunggakan = QHBoxLayout(box_tunggakan)
        self.lbl_menunggak_info = QLabel("0 Anggota", box_tunggakan)
        self.lbl_menunggak_info.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_menunggak_info.setStyleSheet("color: #DC2626;")
        btn_lihat_menunggak = QPushButton("Lihat Daftar", box_tunggakan)
        btn_lihat_menunggak.setMinimumHeight(38)
        btn_lihat_menunggak.setStyleSheet(
            "background-color: #FEE2E2; color: #991B1B; border: 1.5px solid #F87171; "
            "font-weight: bold; border-radius: 6px; padding: 0 16px;"
        )
        btn_lihat_menunggak.clicked.connect(self._lihat_daftar_menunggak)
        layout_tunggakan.addWidget(self.lbl_menunggak_info)
        layout_tunggakan.addStretch()
        layout_tunggakan.addWidget(btn_lihat_menunggak)
        baris_peringatan.addWidget(box_tunggakan, 1)

        layout.addLayout(baris_peringatan)

        # 5. Tombol Pintas Menu Utama
        label_aksi = QLabel("Pintas Menu Utama:", self)
        label_aksi.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(label_aksi)

        grid_aksi = QGridLayout()
        grid_aksi.setSpacing(12)

        self.btn_aksi_simpanan = self._buat_tombol_aksi("Halaman Simpanan", "#2563EB")
        self.btn_aksi_simpanan.clicked.connect(lambda: self.navigasi("ke_simpanan"))

        self.btn_aksi_pinjaman = self._buat_tombol_aksi("Halaman Pinjaman", "#D97706")
        self.btn_aksi_pinjaman.clicked.connect(lambda: self.navigasi("ke_pinjaman"))

        self.btn_aksi_angsuran = self._buat_tombol_aksi("Halaman Angsuran", "#059669")
        self.btn_aksi_angsuran.clicked.connect(lambda: self.navigasi("ke_angsuran"))

        self.btn_aksi_filter = self._buat_tombol_aksi("Filter Cepat Transaksi", "#4F46E5")
        self.btn_aksi_filter.clicked.connect(lambda: self.navigasi("ke_filter_cepat"))

        self.btn_aksi_laporan = self._buat_tombol_aksi("Laporan Mingguan", "#0D9488")
        self.btn_aksi_laporan.clicked.connect(lambda: self.navigasi("ke_laporan"))

        self.btn_aksi_bulanan = self._buat_tombol_aksi("Laporan Bulanan", "#0284C7")
        self.btn_aksi_bulanan.clicked.connect(lambda: self.navigasi("ke_laporan_bulanan"))

        self.btn_aksi_tahunan = self._buat_tombol_aksi("Laporan Tahunan", "#4338CA")
        self.btn_aksi_tahunan.clicked.connect(lambda: self.navigasi("ke_laporan_tahunan"))

        self.btn_aksi_closing = self._buat_tombol_aksi("Closing Akhir Bulan", "#7C3AED")
        self.btn_aksi_closing.clicked.connect(lambda: self.navigasi("ke_closing"))

        grid_aksi.addWidget(self.btn_aksi_simpanan, 0, 0)
        grid_aksi.addWidget(self.btn_aksi_pinjaman, 0, 1)
        grid_aksi.addWidget(self.btn_aksi_angsuran, 0, 2)
        grid_aksi.addWidget(self.btn_aksi_filter, 0, 3)
        grid_aksi.addWidget(self.btn_aksi_laporan, 1, 0)
        grid_aksi.addWidget(self.btn_aksi_bulanan, 1, 1)
        grid_aksi.addWidget(self.btn_aksi_tahunan, 1, 2)
        grid_aksi.addWidget(self.btn_aksi_closing, 1, 3)

        layout.addLayout(grid_aksi)

        self.muat_data()

    def _buat_kartu_metrik(self, judul: str, nilai_awal: str, warna_teks: str, bg_color: str) -> dict:
        box = QFrame(self)
        box.setObjectName("KartuMetrikKoperasi")
        box.setStyleSheet(
            f"QFrame#KartuMetrikKoperasi {{ "
            f"    background-color: {bg_color}; "
            f"    border-radius: 8px; "
            f"    border: none; "
            f"}} "
            f"QLabel {{ "
            f"    border: none; "
            f"    background: transparent; "
            f"}}"
        )
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(18, 14, 18, 14)
        box_layout.setSpacing(6)

        lbl_j = QLabel(judul, box)
        lbl_j.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        lbl_j.setStyleSheet("color: #6B7280; font-size: 10pt; font-weight: bold;")

        lbl_v = QLabel(nilai_awal, box)
        lbl_v.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        lbl_v.setStyleSheet(f"color: {warna_teks}; font-size: 18pt; font-weight: bold;")

        box_layout.addWidget(lbl_j)
        box_layout.addWidget(lbl_v)

        return {"widget": box, "nilai_label": lbl_v}

    def _buat_tombol_aksi(self, teks: str, bg_color: str) -> QPushButton:
        btn = QPushButton(teks, self)
        btn.setMinimumHeight(48)
        btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        btn.setStyleSheet(
            f"background-color: {bg_color}; color: white; border-radius: 6px; padding: 0 16px;"
        )
        return btn

    def muat_data(self) -> None:
        """Memuat ulang seluruh indikator dashboard."""
        dash = ambil_ringkasan_dashboard(self.conn)
        self.data_dashboard = dash

        # 1. Update Info Backup Terakhir
        info_b = ambil_info_backup_terakhir()
        self.lbl_backup_info.setText(f"Backup terakhir: {info_b}" if info_b else "Belum ada backup")

        # 2. Update Kotak Metrik
        self.card_simpanan["nilai_label"].setText(format_rupiah(dash["simpanan_masuk_hari_ini"]))
        self.card_angsuran["nilai_label"].setText(format_rupiah(dash["angsuran_masuk_hari_ini"]))
        self.card_pinjaman["nilai_label"].setText(format_rupiah(dash["pinjaman_cair_hari_ini"]))
        self.card_admin["nilai_label"].setText(format_rupiah(dash.get("biaya_admin_hari_ini", 0)))
        self.card_kas["nilai_label"].setText(format_rupiah(dash["posisi_kas"]))

        # 3. Update Peringatan Tempo & Menunggak
        self.lbl_tempo_info.setText(f"{dash['jumlah_jatuh_tempo_minggu_ini']} Angsuran")
        self.lbl_menunggak_info.setText(f"{dash['jumlah_anggota_menunggak']} Anggota")

        # 4. Update Banner Pengingat
        # Hapus widget pengingat sebelumnya
        while self.layout_pengingat.count():
            item = self.layout_pengingat.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if dash["pengingat_laporan_mingguan"]:
            banner_laporan = QLabel(
                "<b>Pengingat:</b> Laporan mingguan belum dibuat dalam 7 hari terakhir. Silakan buat laporan mingguan.",
                self.box_pengingat
            )
            banner_laporan.setStyleSheet(
                "background-color: #FEF3C7; color: #92400E; padding: 8px 12px; border-radius: 4px; border: 1px solid #FCD34D;"
            )
            self.layout_pengingat.addWidget(banner_laporan)

        if dash["pengingat_closing"]:
            banner_closing = QLabel(
                f"<b>Perhatian:</b> Closing untuk periode {dash['periode_lalu_butuh_closing']} belum dilakukan. Pastikan closing dilakukan agar data keuangan terkunci rapi.",
                self.box_pengingat
            )
            banner_closing.setStyleSheet(
                "background-color: #FEE2E2; color: #991B1B; padding: 8px 12px; border-radius: 4px; border: 1px solid #FCA5A5;"
            )
            self.layout_pengingat.addWidget(banner_closing)

        # Pengingat Toko: Closing Toko & Opname Toko (SPEC Modul 15 E)
        try:
            from datetime import date
            import calendar
            thn, bln = date.today().year, date.today().month
            bln_lalu = bln - 1 if bln > 1 else 12
            thn_lalu = thn if bln > 1 else thn - 1
            periode_lalu = f"{thn_lalu:04d}-{bln_lalu:02d}"
            nama_bln_lalu = f"{calendar.month_name[bln_lalu]} {thn_lalu}"

            cur = self.conn.cursor()
            cur.execute("SELECT 1 FROM closing_toko WHERE periode = ? AND status = 'closed';", (periode_lalu,))
            if not cur.fetchone():
                banner_cl_toko = QLabel(
                    f"<b>Perhatian Unit Toko:</b> Closing toko periode {nama_bln_lalu} belum dilakukan.",
                    self.box_pengingat
                )
                banner_cl_toko.setStyleSheet(
                    "background-color: #FEE2E2; color: #991B1B; padding: 8px 12px; border-radius: 4px; border: 1px solid #FCA5A5;"
                )
                self.layout_pengingat.addWidget(banner_cl_toko)

            periode_ini = f"{thn:04d}-{bln:02d}"
            cur.execute("SELECT 1 FROM opname_sesi WHERE periode = ? AND status = 'final';", (periode_ini,))
            if not cur.fetchone():
                banner_opname = QLabel(
                    f"<b>Pengingat Unit Toko:</b> Stock opname toko bulan ini belum dilakukan atau belum difinalkan.",
                    self.box_pengingat
                )
                banner_opname.setStyleSheet(
                    "background-color: #FEF3C7; color: #92400E; padding: 8px 12px; border-radius: 4px; border: 1px solid #FCD34D;"
                )
                self.layout_pengingat.addWidget(banner_opname)
        except Exception:
            pass

    def _lihat_daftar_tempo(self) -> None:
        daftar = self.data_dashboard.get("daftar_tempo_minggu_ini", [])
        dlg = QDialog(self)
        dlg.setWindowTitle("Daftar Angsuran Jatuh Tempo Minggu Ini")
        dlg.resize(850, 460)
        dlg.setMinimumSize(750, 380)

        d_layout = QVBoxLayout(dlg)
        d_layout.setContentsMargins(18, 18, 18, 18)
        d_layout.setSpacing(12)

        tabel = QTableWidget(dlg)
        tabel.setColumnCount(5)
        tabel.setHorizontalHeaderLabels([
            "Jatuh Tempo", "No. Pinjaman", "Nama dan No. Anggota", "Angsuran", "Sisa Tagihan"
        ])
        tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tabel.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        tabel.setColumnWidth(0, 130)
        tabel.setColumnWidth(1, 130)
        tabel.setColumnWidth(3, 110)
        tabel.setColumnWidth(4, 150)
        tabel.setRowCount(len(daftar))
        tabel.verticalHeader().setDefaultSectionSize(40)

        for b, r in enumerate(daftar):
            tabel.setItem(b, 0, QTableWidgetItem(format_tanggal_indo(r["jatuh_tempo"])))
            tabel.setItem(b, 1, QTableWidgetItem(r["no_pinjaman"]))
            tabel.setItem(b, 2, QTableWidgetItem(f"{r['nama_anggota']} ({r['no_anggota']})"))
            tabel.setItem(b, 3, QTableWidgetItem(f"Ke-{r['angsuran_ke']}"))
            
            sisa_item = QTableWidgetItem(format_rupiah(r["sisa_tagihan"]))
            sisa_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tabel.setItem(b, 4, sisa_item)

        d_layout.addWidget(tabel)
        
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_tutup = QPushButton("Tutup", dlg)
        btn_tutup.setMinimumHeight(40)
        btn_tutup.clicked.connect(dlg.accept)
        btn_box.addWidget(btn_tutup)
        d_layout.addLayout(btn_box)
        dlg.exec()

    def _lihat_daftar_menunggak(self) -> None:
        daftar = self.data_dashboard.get("daftar_anggota_menunggak", [])
        dlg = QDialog(self)
        dlg.setWindowTitle("Daftar Anggota Menunggak")
        dlg.resize(850, 460)
        dlg.setMinimumSize(750, 380)

        d_layout = QVBoxLayout(dlg)
        d_layout.setContentsMargins(18, 18, 18, 18)
        d_layout.setSpacing(12)

        tabel = QTableWidget(dlg)
        tabel.setColumnCount(4)
        tabel.setHorizontalHeaderLabels([
            "Nama dan No. Anggota", "No. Telepon / WA", "Cicilan Telat", "Total Tunggakan (Rp)"
        ])
        tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tabel.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tabel.setColumnWidth(1, 160)
        tabel.setColumnWidth(2, 130)
        tabel.setColumnWidth(3, 170)
        tabel.setRowCount(len(daftar))
        tabel.verticalHeader().setDefaultSectionSize(40)

        for b, r in enumerate(daftar):
            tabel.setItem(b, 0, QTableWidgetItem(f"{r['nama_anggota']} ({r['no_anggota']})"))
            tabel.setItem(b, 1, QTableWidgetItem(r["no_hp"] or "-"))
            tabel.setItem(b, 2, QTableWidgetItem(f"{r['jumlah_cicilan_telat']} bulan"))

            tot_item = QTableWidgetItem(format_rupiah(r["total_tunggakan"]))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tot_item.setForeground(Qt.GlobalColor.darkRed)
            tabel.setItem(b, 3, tot_item)

        d_layout.addWidget(tabel)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_tutup = QPushButton("Tutup", dlg)
        btn_tutup.setMinimumHeight(40)
        btn_tutup.clicked.connect(dlg.accept)
        btn_box.addWidget(btn_tutup)
        d_layout.addLayout(btn_box)
        dlg.exec()

