"""
app/ui/layar_pinjaman.py — Tampilan antarmuka Modul Pinjaman.
- Pembuatan pinjaman baru dengan pemilihan anggota & produk
- Pratinjau jadwal angsuran real-time sebelum disimpan
- Verifikasi pembulatan di cicilan terakhir
- Daftar riwayat pinjaman & dialog rincian jadwal cicilan
"""
import sqlite3
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QDialog, QFormLayout, QTextEdit,
    QDateEdit, QSpinBox, QDoubleSpinBox, QSplitter
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt, QDate

from app.db.repo_anggota import ambil_daftar_anggota
from app.db.repo_pinjaman import (
    ambil_semua_produk_pinjaman, ambil_produk_by_id,
    buat_nomor_pinjaman_berikutnya, buat_pinjaman_baru, ajukan_pinjaman,
    setujui_dan_cairkan_pinjaman, tolak_pengajuan_pinjaman,
    ambil_daftar_pinjaman, ambil_jadwal_angsuran_pinjaman
)
from app.logika.angsuran_flat import hitung_jadwal_angsuran_flat
from app.util.format import format_rupiah, format_tanggal_indo
from app.ui.komponen.input_rupiah import InputRupiah


class DialogPinjamanBaru(QDialog):
    """Dialog Input Pinjaman Baru + Pratinjau Jadwal Angsuran."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle("Formulir Pinjaman Baru (Bunga Flat)")
        self.resize(850, 650)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)

        # Bagian atas: Form input
        form_widget = QWidget(self)
        form_layout = QFormLayout(form_widget)
        form_layout.setSpacing(10)

        # 1. No Pinjaman
        self.input_no_pinjaman = QLineEdit(self)
        self.input_no_pinjaman.setMinimumHeight(38)
        self.input_no_pinjaman.setText(buat_nomor_pinjaman_berikutnya(self.conn))
        form_layout.addRow("No. Pinjaman *:", self.input_no_pinjaman)

        # 2. Pilihan Anggota
        self.combo_anggota = QComboBox(self)
        self.combo_anggota.setMinimumHeight(38)
        self._muat_pilihan_anggota()
        form_layout.addRow("Pilih Anggota *:", self.combo_anggota)

        # 3. Pilihan Produk
        self.combo_produk = QComboBox(self)
        self.combo_produk.setMinimumHeight(38)
        self._muat_pilihan_produk()
        self.combo_produk.currentIndexChanged.connect(self._produk_berubah)
        form_layout.addRow("Produk Pinjaman *:", self.combo_produk)

        # 4. Plafon
        self.input_plafon = InputRupiah(self, placeholder="Contoh: 10.000.000")
        self.input_plafon.setMinimumHeight(38)
        self.input_plafon.textChanged.connect(self._hitung_pratinjau)
        form_layout.addRow("Plafon Pinjaman (Rp) *:", self.input_plafon)

        # 5. Tenor (Bulan) & Persen Jasa
        param_layout = QHBoxLayout()
        self.spin_tenor = QSpinBox(self)
        self.spin_tenor.setMinimumHeight(38)
        self.spin_tenor.setRange(1, 120)
        self.spin_tenor.setValue(10)
        self.spin_tenor.valueChanged.connect(self._hitung_pratinjau)

        self.spin_jasa = QDoubleSpinBox(self)
        self.spin_jasa.setMinimumHeight(38)
        self.spin_jasa.setRange(0.0, 100.0)
        self.spin_jasa.setSingleStep(0.1)
        self.spin_jasa.setValue(1.5)
        self.spin_jasa.setSuffix(" % / bln")
        self.spin_jasa.valueChanged.connect(self._hitung_pratinjau)

        param_layout.addWidget(QLabel("Tenor (bulan):"))
        param_layout.addWidget(self.spin_tenor)
        param_layout.addWidget(QLabel("Jasa (flat):"))
        param_layout.addWidget(self.spin_jasa)
        form_layout.addRow("Parameter Tenor dan Jasa:", param_layout)

        # 6. Biaya Admin & Tanggal Cair
        admin_layout = QHBoxLayout()
        self.input_admin = InputRupiah(self, placeholder="0")
        self.input_admin.setMinimumHeight(38)
        self.input_admin.set_nilai(0)

        self.input_tgl_cair = QDateEdit(self)
        self.input_tgl_cair.setMinimumHeight(38)
        self.input_tgl_cair.setCalendarPopup(True)
        self.input_tgl_cair.setDate(QDate.currentDate())
        self.input_tgl_cair.setDisplayFormat("dd/MM/yyyy")
        self.input_tgl_cair.dateChanged.connect(self._hitung_pratinjau)

        admin_layout.addWidget(QLabel("Biaya Admin (Rp):"))
        admin_layout.addWidget(self.input_admin)
        admin_layout.addWidget(QLabel("Tanggal Pencairan:"))
        admin_layout.addWidget(self.input_tgl_cair)
        form_layout.addRow("Admin dan Tanggal:", admin_layout)

        # 7. Keperluan
        self.input_keperluan = QLineEdit(self)
        self.input_keperluan.setMinimumHeight(38)
        self.input_keperluan.setPlaceholderText("Keperluan pinjaman (opsional)...")
        form_layout.addRow("Keperluan:", self.input_keperluan)

        layout.addWidget(form_widget)

        # Bagian Bawah: Pratinjau Jadwal Angsuran
        label_pratinjau = QLabel("Pratinjau Jadwal Angsuran Bulanan:", self)
        label_pratinjau.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(label_pratinjau)

        self.tabel_jadwal = QTableWidget(self)
        self.tabel_jadwal.setFont(QFont("Segoe UI", 11))
        self.tabel_jadwal.setColumnCount(5)
        self.tabel_jadwal.setHorizontalHeaderLabels([
            "Angsuran Ke", "Jatuh Tempo", "Pokok (Rp)", "Jasa (Rp)", "Total Tagihan (Rp)"
        ])
        self.tabel_jadwal.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabel_jadwal.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel_jadwal.setAlternatingRowColors(True)
        layout.addWidget(self.tabel_jadwal)

        # Ringkasan total
        self.label_total_info = QLabel("Total Pokok: Rp 0 | Total Jasa: Rp 0 | Total Pengembalian: Rp 0", self)
        self.label_total_info.setStyleSheet("color: #1E40AF; font-weight: bold; margin: 4px 0;")
        layout.addWidget(self.label_total_info)

        # Tombol Aksi
        btn_layout = QHBoxLayout()
        self.btn_ajukan = QPushButton("Simpan Pengajuan (Menunggu Persetujuan)", self)
        self.btn_ajukan.setMinimumHeight(42)
        self.btn_ajukan.setStyleSheet("background-color: #D97706; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_ajukan.clicked.connect(lambda: self._simpan(langsung_cair=False))

        self.btn_simpan = QPushButton("Langsung Cairkan Pinjaman", self)
        self.btn_simpan.setMinimumHeight(42)
        self.btn_simpan.setStyleSheet("background-color: #2563EB; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_simpan.clicked.connect(lambda: self._simpan(langsung_cair=True))

        self.btn_batal = QPushButton("Batal", self)
        self.btn_batal.setMinimumHeight(42)
        self.btn_batal.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_batal)
        btn_layout.addWidget(self.btn_ajukan)
        btn_layout.addWidget(self.btn_simpan)
        layout.addLayout(btn_layout)

        # Terapkan nilai produk awal
        self._produk_berubah()

    def _muat_pilihan_anggota(self) -> None:
        self.combo_anggota.clear()
        daftar = ambil_daftar_anggota(self.conn, status_filter="aktif", limit=500)
        for ang in daftar:
            teks = f"{ang['no_anggota']} - {ang['nama']}"
            if ang["unit"]:
                teks += f" ({ang['unit']})"
            self.combo_anggota.addItem(teks, ang["id"])

    def _muat_pilihan_produk(self) -> None:
        self.combo_produk.clear()
        daftar = ambil_semua_produk_pinjaman(self.conn, hanya_aktif=True)
        for p in daftar:
            self.combo_produk.addItem(f"{p['nama']} ({p['jasa_persen_per_bulan']}%)", p["id"])

    def _produk_berubah(self) -> None:
        produk_id = self.combo_produk.currentData()
        if not produk_id:
            return
        prod = ambil_produk_by_id(self.conn, produk_id)
        if prod:
            self.spin_jasa.setValue(prod["jasa_persen_per_bulan"])
            self.input_admin.set_nilai(prod["biaya_admin"])
            self._hitung_pratinjau()

    def _get_plafon_angka(self) -> int:
        return self.input_plafon.ambil_nilai()

    def _hitung_pratinjau(self) -> None:
        plafon = self._get_plafon_angka()
        tenor = self.spin_tenor.value()
        jasa = self.spin_jasa.value()
        tgl_cair = self.input_tgl_cair.date().toString("yyyy-MM-dd")

        if plafon <= 0 or tenor <= 0:
            self.tabel_jadwal.setRowCount(0)
            self.label_total_info.setText("Total Pokok: Rp 0 | Total Jasa: Rp 0 | Total Pengembalian: Rp 0")
            return

        try:
            jadwal = hitung_jadwal_angsuran_flat(plafon, tenor, jasa, tgl_cair)
            self.tabel_jadwal.setRowCount(len(jadwal))

            total_pokok = sum(c["pokok"] for c in jadwal)
            total_jasa = sum(c["jasa"] for c in jadwal)

            for baris, c in enumerate(jadwal):
                self.tabel_jadwal.setItem(baris, 0, QTableWidgetItem(f"Ke-{c['angsuran_ke']}"))
                self.tabel_jadwal.setItem(baris, 1, QTableWidgetItem(format_tanggal_indo(c["jatuh_tempo"])))
                
                item_pokok = QTableWidgetItem(format_rupiah(c["pokok"]))
                item_pokok.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabel_jadwal.setItem(baris, 2, item_pokok)

                item_jasa = QTableWidgetItem(format_rupiah(c["jasa"]))
                item_jasa.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabel_jadwal.setItem(baris, 3, item_jasa)

                item_total = QTableWidgetItem(format_rupiah(c["total_angsuran"]))
                item_total.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.tabel_jadwal.setItem(baris, 4, item_total)

            self.label_total_info.setText(
                f"Total Pokok: {format_rupiah(total_pokok)} | Total Jasa: {format_rupiah(total_jasa)} | "
                f"Total Pengembalian: {format_rupiah(total_pokok + total_jasa)}"
            )
        except Exception:
            self.tabel_jadwal.setRowCount(0)

    def _simpan(self, langsung_cair: bool = True) -> None:
        anggota_id = self.combo_anggota.currentData()
        if not anggota_id:
            QMessageBox.warning(self, "Pilih Anggota", "Silakan pilih anggota terlebih dahulu.")
            return

        no_pinj = self.input_no_pinjaman.text().strip()
        if not no_pinj:
            QMessageBox.warning(self, "Nomor Kosong", "Nomor pinjaman tidak boleh kosong.")
            return

        plafon = self._get_plafon_angka()
        if plafon <= 0:
            QMessageBox.warning(self, "Plafon Kosong", "Masukkan plafon pinjaman lebih dari Rp 0.")
            self.input_plafon.setFocus()
            return

        tenor = self.spin_tenor.value()
        jasa = self.spin_jasa.value()
        tgl_cair = self.input_tgl_cair.date().toString("yyyy-MM-dd")
        
        biaya_admin = self.input_admin.ambil_nilai()
        keperluan = self.input_keperluan.text().strip()
        produk_id = self.combo_produk.currentData()

        if langsung_cair:
            konfirmasi = QMessageBox.question(
                self,
                "Konfirmasi Pencairan Pinjaman",
                f"Proses pencairan pinjaman sebesar {format_rupiah(plafon)} dengan tenor {tenor} bulan?\n"
                f"Sistem akan otomatis mencatat kas keluar dan menjadwalkan {tenor} angsuran.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if konfirmasi != QMessageBox.StandardButton.Yes:
                return

            try:
                buat_pinjaman_baru(
                    self.conn,
                    no_pinjaman=no_pinj,
                    anggota_id=anggota_id,
                    produk_id=produk_id,
                    plafon=plafon,
                    tenor=tenor,
                    jasa_persen_per_bulan=jasa,
                    biaya_admin=biaya_admin,
                    tanggal_cair=tgl_cair,
                    keperluan=keperluan or None
                )
                QMessageBox.information(
                    self, "Pinjaman Berhasil Disimpan",
                    f"Pinjaman {no_pinj} berhasil dicairkan dan seluruh jadwal angsuran telah dibuat."
                )
                self.accept()
            except ValueError as err:
                QMessageBox.warning(self, "Pemberitahuan", str(err))
            except sqlite3.IntegrityError:
                QMessageBox.warning(self, "Nomor Terdaftar", f"Nomor pinjaman '{no_pinj}' sudah pernah digunakan.")
            except Exception as err:
                QMessageBox.critical(self, "Gagal", f"Terjadi kesalahan saat memproses pinjaman: {err}")
        else:
            try:
                ajukan_pinjaman(
                    self.conn,
                    no_pinjaman=no_pinj,
                    anggota_id=anggota_id,
                    produk_id=produk_id,
                    plafon=plafon,
                    tenor=tenor,
                    jasa_persen_per_bulan=jasa,
                    biaya_admin=biaya_admin,
                    tanggal_pengajuan=tgl_cair,
                    keperluan=keperluan or None
                )
                QMessageBox.information(
                    self, "Pengajuan Berhasil",
                    f"Pengajuan pinjaman {no_pinj} berhasil dicatat dengan status 'Diajukan' untuk diputuskan dalam rapat pengurus."
                )
                self.accept()
            except Exception as err:
                QMessageBox.critical(self, "Gagal", f"Gagal mencatat pengajuan: {err}")


class DialogRincianPinjaman(QDialog):
    """Menampilkan detail pinjaman dan daftar jadwal angsurannya."""

    def __init__(self, conn: sqlite3.Connection, pinjaman_row: sqlite3.Row, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.pinj = pinjaman_row
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setWindowTitle(f"Jadwal Angsuran - {self.pinj['no_pinjaman']}")
        self.resize(750, 520)
        self.setFont(QFont("Segoe UI", 12))

        layout = QVBoxLayout(self)

        info_teks = (
            f"<b>No. Pinjaman:</b> {self.pinj['no_pinjaman']} &nbsp;|&nbsp; "
            f"<b>Anggota:</b> {self.pinj['nama_anggota']} ({self.pinj['no_anggota']})<br>"
            f"<b>Plafon:</b> {format_rupiah(self.pinj['plafon'])} &nbsp;|&nbsp; "
            f"<b>Tenor:</b> {self.pinj['tenor']} Bulan &nbsp;|&nbsp; "
            f"<b>Jasa:</b> {self.pinj['jasa_persen_per_bulan']}% / bln &nbsp;|&nbsp; "
            f"<b>Status:</b> {self.pinj['status'].upper()}"
        )
        label_info = QLabel(info_teks, self)
        label_info.setStyleSheet("background-color: #EFF6FF; padding: 10px; border-radius: 6px; color: #1E3A8A;")
        layout.addWidget(label_info)

        tabel = QTableWidget(self)
        tabel.setFont(QFont("Segoe UI", 11))
        tabel.setColumnCount(5)
        tabel.setHorizontalHeaderLabels([
            "Angsuran Ke", "Jatuh Tempo", "Tagihan Pokok", "Tagihan Jasa", "Total Angsuran"
        ])
        tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabel.setAlternatingRowColors(True)

        jadwal = ambil_jadwal_angsuran_pinjaman(self.conn, self.pinj["id"])
        tabel.setRowCount(len(jadwal))

        for baris, c in enumerate(jadwal):
            tabel.setItem(baris, 0, QTableWidgetItem(f"Ke-{c['angsuran_ke']}"))
            tabel.setItem(baris, 1, QTableWidgetItem(format_tanggal_indo(c["jatuh_tempo"])))

            p_item = QTableWidgetItem(format_rupiah(c["pokok"]))
            p_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tabel.setItem(baris, 2, p_item)

            j_item = QTableWidgetItem(format_rupiah(c["jasa"]))
            j_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tabel.setItem(baris, 3, j_item)

            tot_item = QTableWidgetItem(format_rupiah(c["pokok"] + c["jasa"]))
            tot_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tabel.setItem(baris, 4, tot_item)

        layout.addWidget(tabel)

        btn_tutup = QPushButton("Tutup", self)
        btn_tutup.setMinimumHeight(40)
        btn_tutup.clicked.connect(self.accept)
        layout.addWidget(btn_tutup)


class LayarPinjaman(QWidget):
    """Layar Daftar Pinjaman Koperasi."""

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 12))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header
        header_layout = QHBoxLayout()
        label_judul = QLabel("Data Pinjaman Anggota", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_layout.addWidget(label_judul)

        header_layout.addStretch()

        self.btn_pinjaman_baru = QPushButton("+ Pinjaman Baru", self)
        self.btn_pinjaman_baru.setProperty("tipe", "utama")
        self.btn_pinjaman_baru.clicked.connect(self._buka_dialog_baru)
        header_layout.addWidget(self.btn_pinjaman_baru)

        layout.addLayout(header_layout)

        # Filter
        filter_layout = QHBoxLayout()
        self.input_cari = QLineEdit(self)
        self.input_cari.setPlaceholderText("Cari no. pinjaman, nama anggota, atau keperluan...")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.textChanged.connect(self.muat_data)

        self.combo_status = QComboBox(self)
        self.combo_status.setMinimumHeight(40)
        self.combo_status.addItem("Semua Status", "semua")
        self.combo_status.addItem("Diajukan (Antrean Rapat)", "diajukan")
        self.combo_status.addItem("Hanya Aktif", "aktif")
        self.combo_status.addItem("Lunas", "lunas")
        self.combo_status.addItem("Ditolak", "ditolak")
        self.combo_status.currentIndexChanged.connect(self.muat_data)

        self.btn_segar = QPushButton("Segarkan", self)
        self.btn_segar.setMinimumHeight(40)
        self.btn_segar.clicked.connect(self.muat_data)

        filter_layout.addWidget(self.input_cari, 4)
        filter_layout.addWidget(self.combo_status, 2)
        filter_layout.addWidget(self.btn_segar, 1)
        layout.addLayout(filter_layout)

        # Tabel Pinjaman
        self.tabel = QTableWidget(self)
        self.tabel.setFont(QFont("Segoe UI", 11))
        self.tabel.setColumnCount(8)
        self.tabel.setHorizontalHeaderLabels([
            "ID", "No. Pinjaman", "Nama Anggota", "Plafon", "Tenor", "Jasa/Bln", "Tgl Cair", "Status"
        ])
        self.tabel.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tabel.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tabel.setColumnWidth(0, 50)   # ID
        self.tabel.setColumnWidth(1, 115)  # No. Pinjaman
        self.tabel.setColumnWidth(3, 135)  # Plafon
        self.tabel.setColumnWidth(4, 90)   # Tenor
        self.tabel.setColumnWidth(5, 115)  # Jasa/Bln
        self.tabel.setColumnWidth(6, 115)  # Tgl Cair
        self.tabel.setColumnWidth(7, 100)  # Status
        self.tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabel.setAlternatingRowColors(True)
        self.tabel.verticalHeader().setDefaultSectionSize(36)
        self.tabel.doubleClicked.connect(self._lihat_rincian)

        layout.addWidget(self.tabel)

        # Tombol Bawah
        aksi_layout = QHBoxLayout()
        self.btn_setujui = QPushButton("Setujui dan Cairkan Pengajuan", self)
        self.btn_setujui.setProperty("tipe", "sukses")
        self.btn_setujui.clicked.connect(self._setujui_pengajuan)

        self.btn_tolak = QPushButton("Tolak Pengajuan", self)
        self.btn_tolak.setProperty("tipe", "bahaya")
        self.btn_tolak.clicked.connect(self._tolak_pengajuan)

        self.btn_detail = QPushButton("Lihat Rincian dan Jadwal Angsuran", self)
        self.btn_detail.clicked.connect(self._lihat_rincian)

        aksi_layout.addWidget(self.btn_setujui)
        aksi_layout.addWidget(self.btn_tolak)
        aksi_layout.addWidget(self.btn_detail)
        aksi_layout.addStretch()
        layout.addLayout(aksi_layout)

        self.daftar_pinj = []
        self.muat_data()

    def muat_data(self) -> None:
        kata_kunci = self.input_cari.text().strip()
        status = self.combo_status.currentData()

        self.daftar_pinj = ambil_daftar_pinjaman(
            self.conn, status_filter=status, kata_kunci=kata_kunci, limit=200
        )
        self.tabel.setRowCount(len(self.daftar_pinj))

        for baris, p in enumerate(self.daftar_pinj):
            self.tabel.setItem(baris, 0, QTableWidgetItem(str(p["id"])))
            self.tabel.setItem(baris, 1, QTableWidgetItem(p["no_pinjaman"]))
            self.tabel.setItem(baris, 2, QTableWidgetItem(f"{p['nama_anggota']} ({p['no_anggota']})"))

            plafon_item = QTableWidgetItem(format_rupiah(p["plafon"]))
            plafon_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tabel.setItem(baris, 3, plafon_item)

            self.tabel.setItem(baris, 4, QTableWidgetItem(f"{p['tenor']} bln"))
            self.tabel.setItem(baris, 5, QTableWidgetItem(f"{p['jasa_persen_per_bulan']}%"))
            self.tabel.setItem(baris, 6, QTableWidgetItem(format_tanggal_indo(p["tanggal_cair"])))

            status_item = QTableWidgetItem(p["status"].capitalize())
            if p["status"] == "aktif":
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            elif p["status"] == "diajukan":
                status_item.setForeground(Qt.GlobalColor.darkYellow)
            elif p["status"] == "lunas":
                status_item.setForeground(Qt.GlobalColor.darkBlue)
            elif p["status"] == "ditolak":
                status_item.setForeground(Qt.GlobalColor.darkRed)
            self.tabel.setItem(baris, 7, status_item)

    def _setujui_pengajuan(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_pinj):
            QMessageBox.information(self, "Pilih Pinjaman", "Silakan klik baris pengajuan pinjaman terlebih dahulu.")
            return

        p = self.daftar_pinj[baris]
        if p["status"] != "diajukan":
            QMessageBox.information(self, "Bukan Pengajuan", f"Pinjaman ini sudah berstatus '{p['status']}'.")
            return

        tanya = QMessageBox.question(
            self, "Konfirmasi Persetujuan Pengurus",
            f"Setujui dan cairkan pinjaman {p['no_pinjaman']} atas nama {p['nama_anggota']} sebesar {format_rupiah(p['plafon'])}?\n\n"
            f"Jadwal cicilan {p['tenor']} bulan akan dibuat dan pengeluaran kas pencairan akan otomatis dicatat.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if tanya == QMessageBox.StandardButton.Yes:
            try:
                tgl_hari_ini = date.today().strftime("%Y-%m-%d")
                setujui_dan_cairkan_pinjaman(self.conn, p["id"], tgl_hari_ini)
                QMessageBox.information(self, "Berhasil", f"Pinjaman {p['no_pinjaman']} berhasil disetujui dan dicairkan.")
                self.muat_data()
            except Exception as err:
                QMessageBox.critical(self, "Gagal", f"Gagal menyetujui: {err}")

    def _tolak_pengajuan(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_pinj):
            QMessageBox.information(self, "Pilih Pinjaman", "Silakan klik baris pengajuan pinjaman terlebih dahulu.")
            return

        p = self.daftar_pinj[baris]
        if p["status"] != "diajukan":
            QMessageBox.information(self, "Bukan Pengajuan", f"Pinjaman ini sudah berstatus '{p['status']}'.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Penolakan Pengajuan Pinjaman")
        dlg.resize(400, 200)
        dlg.setFont(QFont("Segoe UI", 12))

        d_layout = QVBoxLayout(dlg)
        d_layout.addWidget(QLabel(f"Tolak pengajuan {p['no_pinjaman']} ({p['nama_anggota']})?"))
        form = QFormLayout()
        input_alasan = QLineEdit(dlg)
        input_alasan.setPlaceholderText("Alasan penolakan pengurus...")
        form.addRow("Alasan Penolakan *:", input_alasan)
        d_layout.addLayout(form)

        b_layout = QHBoxLayout()
        btn_b = QPushButton("Batal", dlg)
        btn_b.clicked.connect(dlg.reject)
        btn_t = QPushButton("Tolak Pengajuan", dlg)
        btn_t.setStyleSheet("background-color: #DC2626; color: white; font-weight: bold;")
        
        def do_t():
            alasan = input_alasan.text().strip()
            if not alasan:
                QMessageBox.warning(dlg, "Alasan Wajib", "Alasan penolakan wajib diisi.")
                return
            try:
                tolak_pengajuan_pinjaman(self.conn, p["id"], alasan)
                QMessageBox.information(dlg, "Selesai", f"Pengajuan {p['no_pinjaman']} telah ditolak.")
                dlg.accept()
                self.muat_data()
            except Exception as err:
                QMessageBox.critical(dlg, "Gagal", str(err))

        btn_t.clicked.connect(do_t)
        b_layout.addStretch()
        b_layout.addWidget(btn_b)
        b_layout.addWidget(btn_t)
        d_layout.addLayout(b_layout)
        dlg.exec()

    def _buka_dialog_baru(self) -> None:
        dlg = DialogPinjamanBaru(self.conn, parent=self)
        if dlg.exec():
            self.muat_data()

    def _lihat_rincian(self) -> None:
        baris = self.tabel.currentRow()
        if baris < 0 or baris >= len(self.daftar_pinj):
            QMessageBox.information(self, "Pilih Pinjaman", "Silakan klik baris pinjaman terlebih dahulu.")
            return

        pinj_row = self.daftar_pinj[baris]
        dlg = DialogRincianPinjaman(self.conn, pinjaman_row=pinj_row, parent=self)
        dlg.exec()

