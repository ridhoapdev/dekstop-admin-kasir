"""
app/ui/layar_anggota.py — Tampilan antarmuka Manajemen Data Anggota.
Sesuai prinsip RULES.md & Modern Web Guidance:
- Font isi 14px, header 13px semibold, tinggi baris 40px, padding sel horizontal 12px
- Kolom ID disembunyikan dari UI tapi tersimpan di UserRole
- Kolom No. Pegawai (atau NIK tersamar 3201••••••••1234 jika 16 digit)
- Status render sebagai badge pill (StatusBadgeDelegate)
- Toolbar atas: "+ Tambah Anggota", input pencarian (clear button, Esc, debounce 200ms),
  dropdown status, dropdown semua unit dinamis, tombol ikon segarkan
- Toolbar bawah: Ubah Data & Ubah Status disabled-until-selected, label status dinamis,
  tombol Hapus di ujung kanan dengan outline merah, tooltip proteksi transaksi,
  dan dialog konfirmasi spesifik nama anggota
- Label penghitung data: "Menampilkan X dari Y anggota"
- Empty State interaktif dengan tombol aksi
- Double-click atau Enter = Ubah Data, klik kanan = menu konteks
"""
import sqlite3
import re
from datetime import datetime
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QMessageBox, QDialog, QFormLayout, QTextEdit,
    QDateEdit, QMenu
)
from PySide6.QtGui import QFont, QCursor, QAction, QKeyEvent
from PySide6.QtCore import Qt, QDate, QTimer

from app.db.repo_anggota import (
    ambil_daftar_anggota, tambah_anggota, ubah_anggota,
    set_status_anggota, hapus_anggota_jika_tanpa_transaksi,
    buat_nomor_anggota_berikutnya, ambil_anggota_by_id,
    cek_anggota_punya_transaksi
)
from app.util.format import format_tanggal_indo
from app.ui.komponen.tabel_helper import (
    terapkan_style_tabel_global, format_samarkan_nik,
    WidgetEmptyState
)
from app.ui.komponen.sidebar import buat_ikon_sidebar


class DialogFormAnggota(QDialog):
    """Dialog Tambah/Ubah Data Anggota."""

    def __init__(self, conn: sqlite3.Connection, anggota_id: int = None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.anggota_id = anggota_id
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        judul = "Ubah Data Anggota" if self.anggota_id else "Tambah Anggota Baru"
        self.setWindowTitle(judul)
        self.setMinimumWidth(480)
        self.setFont(QFont("Segoe UI", 11))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)

        # Field input
        self.input_no = QLineEdit(self)
        self.input_no.setMinimumHeight(38)
        self.input_nama = QLineEdit(self)
        self.input_nama.setMinimumHeight(38)
        self.input_nik = QLineEdit(self)
        self.input_nik.setMinimumHeight(38)
        self.input_unit = QLineEdit(self)
        self.input_unit.setMinimumHeight(38)
        self.input_hp = QLineEdit(self)
        self.input_hp.setMinimumHeight(38)
        self.input_alamat = QLineEdit(self)
        self.input_alamat.setMinimumHeight(38)
        
        self.input_tgl_masuk = QDateEdit(self)
        self.input_tgl_masuk.setMinimumHeight(38)
        self.input_tgl_masuk.setCalendarPopup(True)
        self.input_tgl_masuk.setDate(QDate.currentDate())
        self.input_tgl_masuk.setDisplayFormat("dd/MM/yyyy")

        self.input_catatan = QTextEdit(self)
        self.input_catatan.setMaximumHeight(80)

        form_layout.addRow("No. Anggota *:", self.input_no)
        form_layout.addRow("Nama Lengkap *:", self.input_nama)
        form_layout.addRow("No. Pegawai / NIK:", self.input_nik)
        form_layout.addRow("Unit / Bagian:", self.input_unit)
        form_layout.addRow("No. HP / WA:", self.input_hp)
        form_layout.addRow("Alamat:", self.input_alamat)
        form_layout.addRow("Tanggal Masuk:", self.input_tgl_masuk)
        form_layout.addRow("Catatan Tambahan:", self.input_catatan)

        layout.addLayout(form_layout)

        # Tombol Aksi
        btn_layout = QHBoxLayout()
        self.btn_batal = QPushButton("Batal", self)
        self.btn_batal.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_batal.setMinimumHeight(40)
        self.btn_batal.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9; color: #334155; font-weight: 500;
                border: 1px solid #CBD5E1; border-radius: 6px; padding: 0 18px;
            }
            QPushButton:hover { background-color: #E2E8F0; }
        """)
        self.btn_batal.clicked.connect(self.reject)

        self.btn_simpan = QPushButton("Simpan Anggota", self)
        self.btn_simpan.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_simpan.setMinimumHeight(40)
        self.btn_simpan.setStyleSheet("""
            QPushButton {
                background-color: #2563EB; color: white; font-weight: bold;
                border: none; border-radius: 6px; padding: 0 20px;
            }
            QPushButton:hover { background-color: #1D4ED8; }
        """)
        self.btn_simpan.clicked.connect(self._simpan)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_batal)
        btn_layout.addWidget(self.btn_simpan)
        layout.addLayout(btn_layout)

        # Muat data awal jika mode ubah
        if self.anggota_id:
            self._muat_data_edit()
        else:
            self.input_no.setText(buat_nomor_anggota_berikutnya(self.conn))

        self.input_nama.setFocus()

    def _muat_data_edit(self) -> None:
        data = ambil_anggota_by_id(self.conn, self.anggota_id)
        if not data:
            return
        self.input_no.setText(data["no_anggota"])
        self.input_no.setReadOnly(True)
        self.input_nama.setText(data["nama"] or "")
        self.input_nik.setText(data["nik_karyawan"] or "")
        self.input_unit.setText(data["unit"] or "")
        self.input_hp.setText(data["no_hp"] or "")
        self.input_alamat.setText(data["alamat"] or "")
        self.input_catatan.setPlainText(data["catatan"] or "")
        self.input_tgl_masuk.setEnabled(False)

    def _simpan(self) -> None:
        nama = self.input_nama.text().strip()
        no_ang = self.input_no.text().strip()

        if not no_ang:
            QMessageBox.warning(self, "Perhatian", "Nomor anggota tidak boleh kosong.")
            self.input_no.setFocus()
            return
        if not nama:
            QMessageBox.warning(self, "Perhatian", "Nama lengkap anggota tidak boleh kosong.")
            self.input_nama.setFocus()
            return

        try:
            if self.anggota_id:
                ubah_anggota(
                    self.conn,
                    anggota_id=self.anggota_id,
                    nama=nama,
                    nik_karyawan=self.input_nik.text().strip() or None,
                    unit=self.input_unit.text().strip() or None,
                    no_hp=self.input_hp.text().strip() or None,
                    alamat=self.input_alamat.text().strip() or None,
                    catatan=self.input_catatan.toPlainText().strip() or None
                )
            else:
                tgl_iso = self.input_tgl_masuk.date().toString("yyyy-MM-dd")
                tambah_anggota(
                    self.conn,
                    no_anggota=no_ang,
                    nama=nama,
                    nik_karyawan=self.input_nik.text().strip() or None,
                    unit=self.input_unit.text().strip() or None,
                    no_hp=self.input_hp.text().strip() or None,
                    alamat=self.input_alamat.text().strip() or None,
                    tanggal_masuk=tgl_iso,
                    catatan=self.input_catatan.toPlainText().strip() or None
                )
            self.accept()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Perhatian", f"Nomor anggota '{no_ang}' sudah terdaftar.")
        except Exception as err:
            QMessageBox.warning(self, "Gagal Menyimpan", f"Terjadi kendala saat menyimpan: {err}")


class LayarAnggota(QWidget):
    """
    Layar Manajemen Data Anggota Koperasi (Modern, Rapi, Standar Global).
    """

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._semua_anggota_cache: List[sqlite3.Row] = []
        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFont(QFont("Segoe UI", 11))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)

        # 1. Header: Judul & Tombol Tambah Primer
        header_layout = QHBoxLayout()
        header_teks = QVBoxLayout()
        header_teks.setSpacing(2)

        label_judul = QLabel("Data Anggota Koperasi", self)
        label_judul.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        label_judul.setStyleSheet("color: #0F172A;")
        header_teks.addWidget(label_judul)

        label_sub = QLabel("Kelola data anggota aktif dan nonaktif simpan pinjam", self)
        label_sub.setFont(QFont("Segoe UI", 9.5))
        label_sub.setStyleSheet("color: #64748B;")
        header_teks.addWidget(label_sub)

        header_layout.addLayout(header_teks, 1)

        self.btn_tambah = QPushButton("+ Tambah Anggota", self)
        self.btn_tambah.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_tambah.setMinimumHeight(42)
        self.btn_tambah.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                font-family: 'Segoe UI';
                font-size: 14px;
                font-weight: 600;
                border: none;
                border-radius: 6px;
                padding: 0 18px;
                outline: none;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_tambah.clicked.connect(self._buka_dialog_tambah)
        header_layout.addWidget(self.btn_tambah)

        layout.addLayout(header_layout)

        # 2. Toolbar Atas: Search (Debounce + Clear), Status, Unit, Refresh
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(10)

        # Input Pencarian dengan Clear Button bawaan & penanganan Esc
        self.input_cari = QLineEdit(self)
        self.input_cari.setClearButtonEnabled(True)
        self.input_cari.setPlaceholderText("Ketik nama, no. anggota, no. pegawai/NIK, unit... (Esc untuk hapus)")
        self.input_cari.setMinimumHeight(40)
        self.input_cari.setStyleSheet("""
            QLineEdit {
                background-color: #FFFFFF;
                border: 1.5px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 12px;
                font-family: 'Segoe UI';
                font-size: 13.5px;
                color: #1E293B;
            }
            QLineEdit:focus {
                border-color: #3B82F6;
            }
        """)

        # Debounce timer untuk input pencarian (200ms)
        self._timer_debounce = QTimer(self)
        self._timer_debounce.setSingleShot(True)
        self._timer_debounce.setInterval(200)
        self._timer_debounce.timeout.connect(self.muat_data)
        self.input_cari.textChanged.connect(self._on_search_text_changed)

        # Filter Dropdown Status
        self.combo_status = QComboBox(self)
        self.combo_status.setMinimumHeight(40)
        self.combo_status.addItem("Semua Status", "semua")
        self.combo_status.addItem("Hanya Aktif", "aktif")
        self.combo_status.addItem("Hanya Keluar", "keluar")
        self.combo_status.currentIndexChanged.connect(self.muat_data)
        self.combo_status.setStyleSheet("""
            QComboBox {
                background-color: #FFFFFF;
                border: 1.5px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 12px;
                font-family: 'Segoe UI';
                font-size: 13.5px;
                min-width: 130px;
            }
        """)

        # Filter Dropdown Unit Dinamis
        self.combo_unit = QComboBox(self)
        self.combo_unit.setMinimumHeight(40)
        self.combo_unit.addItem("Semua Unit", "semua")
        self.combo_unit.currentIndexChanged.connect(self.muat_data)
        self.combo_unit.setStyleSheet("""
            QComboBox {
                background-color: #FFFFFF;
                border: 1.5px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 12px;
                font-family: 'Segoe UI';
                font-size: 13.5px;
                min-width: 140px;
            }
        """)

        # Tombol Ikon Segarkan
        self.btn_segar = QPushButton("🔄", self)
        self.btn_segar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_segar.setFixedSize(40, 40)
        self.btn_segar.setToolTip("Muat ulang data anggota")
        self.btn_segar.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                color: #475569;
                border: 1.5px solid #CBD5E1;
                border-radius: 6px;
                font-size: 15px;
                outline: none;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
                border-color: #94A3B8;
                color: #1E293B;
            }
        """)
        self.btn_segar.clicked.connect(self._segarkan_manual)

        toolbar_layout.addWidget(self.input_cari, 4)
        toolbar_layout.addWidget(self.combo_status, 1)
        toolbar_layout.addWidget(self.combo_unit, 1)
        toolbar_layout.addWidget(self.btn_segar, 0)
        layout.addLayout(toolbar_layout)

        # 3. Tabel Data Anggota
        self.tabel = QTableWidget(self)
        self.tabel.setColumnCount(7)
        self.tabel.setHorizontalHeaderLabels([
            "ID", "No. Anggota", "Nama Lengkap", "No. Pegawai", "Unit / Bagian", "Tgl Masuk", "Status"
        ])
        
        # Penyesuaian lebar kolom
        hdr = self.tabel.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Nama stretch
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)  # Unit stretch
        self.tabel.setColumnWidth(0, 40)   # ID (sembunyi)
        self.tabel.setColumnWidth(1, 130)  # No. Anggota
        self.tabel.setColumnWidth(3, 140)  # No. Pegawai / NIK
        self.tabel.setColumnWidth(5, 130)  # Tgl Masuk
        self.tabel.setColumnWidth(6, 120)  # Status Badge

        # Terapkan standard global style & helper
        self.empty_state = terapkan_style_tabel_global(
            self.tabel,
            rata_kanan_kolom=[],
            rata_tengah_kolom=[],
            kolom_status=6,
            kolom_sembunyi=[0]  # Sembunyikan kolom ID database dari UI
        )

        # Interaksi baris
        self.tabel.itemSelectionChanged.connect(self._perbarui_status_tombol)
        self.tabel.doubleClicked.connect(self._buka_dialog_ubah)
        self.tabel.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabel.customContextMenuRequested.connect(self._tampilkan_menu_konteks)

        layout.addWidget(self.tabel, 1)

        # 4. Baris Penghitung Data & Toolbar Bawah
        footer_tabel_lay = QHBoxLayout()

        # Label Jumlah Data (Sisi Kiri)
        self.lbl_jumlah_data = QLabel("Menampilkan 0 dari 0 anggota", self)
        self.lbl_jumlah_data.setFont(QFont("Segoe UI", 9.5))
        self.lbl_jumlah_data.setStyleSheet("color: #64748B; font-weight: 500;")
        footer_tabel_lay.addWidget(self.lbl_jumlah_data)

        footer_tabel_lay.addStretch()
        layout.addLayout(footer_tabel_lay)

        # Toolbar Aksi Bawah
        aksi_layout = QHBoxLayout()
        aksi_layout.setSpacing(10)

        self.btn_ubah = QPushButton("Ubah Data", self)
        self.btn_ubah.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_ubah.setMinimumHeight(42)
        self.btn_ubah.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self.btn_ubah.setStyleSheet("""
            QPushButton {
                background-color: #EFF6FF;
                color: #1D4ED8;
                border: 1px solid #BFDBFE;
                border-radius: 6px;
                padding: 0 16px;
                font-weight: 600;
            }
            QPushButton:hover:!disabled { background-color: #DBEAFE; }
            QPushButton:disabled {
                background-color: #F8FAFC;
                color: #94A3B8;
                border-color: #E2E8F0;
            }
        """)
        self.btn_ubah.clicked.connect(self._buka_dialog_ubah)

        self.btn_status = QPushButton("Ubah Status", self)
        self.btn_status.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_status.setMinimumHeight(42)
        self.btn_status.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self.btn_status.setStyleSheet("""
            QPushButton {
                background-color: #F8FAFC;
                color: #334155;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 16px;
                font-weight: 600;
            }
            QPushButton:hover:!disabled { background-color: #F1F5F9; }
            QPushButton:disabled {
                background-color: #F8FAFC;
                color: #94A3B8;
                border-color: #E2E8F0;
            }
        """)
        self.btn_status.clicked.connect(self._toggle_status)

        # Tombol Hapus: diletakkan di ujung kanan dengan outline merah
        self.btn_hapus = QPushButton("Hapus", self)
        self.btn_hapus.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_hapus.setMinimumHeight(42)
        self.btn_hapus.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        self.btn_hapus.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #DC2626;
                border: 1.5px solid #F87171;
                border-radius: 6px;
                padding: 0 20px;
                font-weight: 600;
            }
            QPushButton:hover:!disabled {
                background-color: #DC2626;
                color: #FFFFFF;
                border-color: #DC2626;
            }
            QPushButton:disabled {
                background-color: transparent;
                color: #CBD5E1;
                border-color: #E2E8F0;
            }
        """)
        self.btn_hapus.clicked.connect(self._hapus_anggota)

        aksi_layout.addWidget(self.btn_ubah)
        aksi_layout.addWidget(self.btn_status)
        aksi_layout.addStretch()
        aksi_layout.addWidget(self.btn_hapus)

        layout.addLayout(aksi_layout)

        # Muat daftar unit ke dropdown dan data tabel
        self._muat_daftar_unit()
        self.muat_data()
        self._perbarui_status_tombol()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            if self.input_cari.text():
                self.input_cari.clear()
                return
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.tabel.hasFocus() and self.btn_ubah.isEnabled():
                self._buka_dialog_ubah()
                return
        super().keyPressEvent(event)

    def _on_search_text_changed(self, text: str):
        self._timer_debounce.start()

    def _segarkan_manual(self):
        self._muat_daftar_unit()
        self.muat_data()

    def _muat_daftar_unit(self):
        unit_terpilih = self.combo_unit.currentData()
        self.combo_unit.blockSignals(True)
        self.combo_unit.clear()
        self.combo_unit.addItem("Semua Unit", "semua")
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT DISTINCT unit FROM anggota WHERE unit IS NOT NULL AND TRIM(unit) != '' ORDER BY unit ASC;")
            rows = cur.fetchall()
            for r in rows:
                u = str(r[0]).strip()
                if u:
                    self.combo_unit.addItem(u, u)
        except Exception:
            pass

        # Kembalikan pilihan jika masih ada
        idx = self.combo_unit.findData(unit_terpilih)
        if idx >= 0:
            self.combo_unit.setCurrentIndex(idx)
        self.combo_unit.blockSignals(False)

    def muat_data(self) -> None:
        """Mengambil data dari database dan menampilkan di tabel secara terstruktur."""
        kata_kunci = self.input_cari.text().strip()
        status = self.combo_status.currentData()
        unit_filter = self.combo_unit.currentData()

        # Ambil total seluruh anggota
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM anggota;")
        total_anggota_global = cur.fetchone()[0]

        daftar = ambil_daftar_anggota(self.conn, kata_kunci=kata_kunci, status_filter=status, limit=1000)

        # Filter lokal untuk unit bila dipilih
        if unit_filter and unit_filter != "semua":
            daftar = [r for r in daftar if (r["unit"] or "").strip().lower() == unit_filter.lower()]

        # Cek tipe kolom NIK dari data
        nik_adalah_no_pegawai = True
        for r in daftar:
            nik_val = str(r["nik_karyawan"] or "")
            if len(nik_val) == 16 and nik_val.isdigit():
                nik_adalah_no_pegawai = False
                break
        
        judul_kolom_nik = "No. Pegawai" if nik_adalah_no_pegawai else "NIK"
        self.tabel.horizontalHeaderItem(3).setText(judul_kolom_nik)

        self.tabel.setSortingEnabled(False)
        self.tabel.setRowCount(len(daftar))

        for baris, row in enumerate(daftar):
            # Kolom 0: ID (disimpan juga di UserRole baris)
            id_item = QTableWidgetItem(str(row["id"]))
            id_item.setData(Qt.ItemDataRole.UserRole, row["id"])
            id_item.setData(Qt.ItemDataRole.UserRole + 1, dict(row))

            # Kolom 1: No. Anggota
            no_item = QTableWidgetItem(row["no_anggota"])

            # Kolom 2: Nama Lengkap
            nama_item = QTableWidgetItem(row["nama"])

            # Kolom 3: No. Pegawai / NIK (tersamar bila 16 digit)
            nik_item = QTableWidgetItem(format_samarkan_nik(row["nik_karyawan"]))

            # Kolom 4: Unit / Bagian
            unit_item = QTableWidgetItem(row["unit"] or "-")

            # Kolom 5: Tanggal Masuk
            tgl_item = QTableWidgetItem(format_tanggal_indo(row["tanggal_masuk"]))

            # Kolom 6: Status
            status_item = QTableWidgetItem("Aktif" if row["status"] == "aktif" else "Keluar")

            self.tabel.setItem(baris, 0, id_item)
            self.tabel.setItem(baris, 1, no_item)
            self.tabel.setItem(baris, 2, nama_item)
            self.tabel.setItem(baris, 3, nik_item)
            self.tabel.setItem(baris, 4, unit_item)
            self.tabel.setItem(baris, 5, tgl_item)
            self.tabel.setItem(baris, 6, status_item)

        self.tabel.setSortingEnabled(True)

        # Update label jumlah data
        jumlah_tampil = len(daftar)
        self.lbl_jumlah_data.setText(f"Menampilkan {jumlah_tampil} dari {total_anggota_global} anggota")

        # Handle Empty State
        if jumlah_tampil == 0:
            if kata_kunci:
                self.empty_state.tampilkan(
                    f"Tidak ada anggota yang cocok dengan '{kata_kunci}'",
                    label_tombol="Hapus pencarian",
                    callback_aksi=self.input_cari.clear
                )
            elif total_anggota_global == 0:
                self.empty_state.tampilkan(
                    "Belum ada data anggota di koperasi",
                    label_tombol="+ Tambah Anggota",
                    callback_aksi=self._buka_dialog_tambah
                )
            else:
                self.empty_state.tampilkan("Tidak ada data dengan filter yang dipilih.")
        else:
            self.empty_state.hide()

        self._perbarui_status_tombol()

    def _data_baris_terpilih(self) -> Optional[Dict[str, Any]]:
        baris = self.tabel.currentRow()
        if baris < 0:
            return None
        id_item = self.tabel.item(baris, 0)
        if not id_item:
            return None
        return id_item.data(Qt.ItemDataRole.UserRole + 1)

    def _id_terpilih(self) -> int:
        data = self._data_baris_terpilih()
        return data["id"] if data else 0

    def _perbarui_status_tombol(self) -> None:
        """Mengatur status tombol aksi bawah sesuai aturan disabled-until-selected."""
        data = self._data_baris_terpilih()
        if not data:
            self.btn_ubah.setEnabled(False)
            self.btn_status.setEnabled(False)
            self.btn_status.setText("Ubah Status")
            self.btn_hapus.setEnabled(False)
            self.btn_hapus.setToolTip("")
            return

        self.btn_ubah.setEnabled(True)
        self.btn_status.setEnabled(True)

        # Label dinamis Ubah Status
        status_aktif = (data.get("status") == "aktif")
        self.btn_status.setText("Nonaktifkan Anggota" if status_aktif else "Aktifkan Kembali")

        # Validasi Hapus: Nonaktif bila anggota punya riwayat transaksi
        punya_tx = cek_anggota_punya_transaksi(self.conn, data["id"])
        if punya_tx:
            self.btn_hapus.setEnabled(False)
            self.btn_hapus.setToolTip("Tidak bisa dihapus: anggota ini sudah memiliki transaksi. Gunakan Nonaktifkan Anggota.")
        else:
            self.btn_hapus.setEnabled(True)
            self.btn_hapus.setToolTip("Hapus data anggota (hanya bisa jika belum memiliki transaksi)")

    def _tampilkan_menu_konteks(self, pos):
        """Klik kanan pada baris tabel memunculkan menu konteks aksi yang sama."""
        baris = self.tabel.rowAt(pos.y())
        if baris < 0:
            return

        self.tabel.selectRow(baris)
        self._perbarui_status_tombol()
        data = self._data_baris_terpilih()
        if not data:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 4px;
                font-family: 'Segoe UI';
                font-size: 13.5px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #EFF6FF;
                color: #1D4ED8;
            }
            QMenu::separator {
                height: 1px;
                background-color: #E2E8F0;
                margin: 4px 6px;
            }
        """)

        aksi_ubah = menu.addAction("✏  Ubah Data Anggota")
        aksi_ubah.triggered.connect(self._buka_dialog_ubah)

        label_st = "Nonaktifkan Anggota" if data.get("status") == "aktif" else "Aktifkan Kembali"
        aksi_status = menu.addAction(f"🔄  {label_st}")
        aksi_status.triggered.connect(self._toggle_status)

        menu.addSeparator()

        aksi_hapus = menu.addAction("🗑  Hapus")
        aksi_hapus.setEnabled(self.btn_hapus.isEnabled())
        aksi_hapus.triggered.connect(self._hapus_anggota)

        menu.exec(self.tabel.viewport().mapToGlobal(pos))

    def _buka_dialog_tambah(self) -> None:
        dlg = DialogFormAnggota(self.conn, parent=self)
        if dlg.exec():
            self._muat_daftar_unit()
            self.muat_data()

    def _buka_dialog_ubah(self) -> None:
        anggota_id = self._id_terpilih()
        if not anggota_id:
            QMessageBox.information(self, "Pilih Anggota", "Silakan klik baris anggota yang ingin diubah.")
            return
        dlg = DialogFormAnggota(self.conn, anggota_id=anggota_id, parent=self)
        if dlg.exec():
            self._muat_daftar_unit()
            self.muat_data()

    def _toggle_status(self) -> None:
        data = self._data_baris_terpilih()
        if not data:
            return

        anggota_id = data["id"]
        status_lama = data["status"]
        status_baru = "keluar" if status_lama == "aktif" else "aktif"
        tgl_hari_ini = datetime.now().strftime("%Y-%m-%d") if status_baru == "keluar" else None

        pesan = (
            f"Aktifkan kembali status keanggotaan '{data['nama']}'?"
            if status_baru == "aktif"
            else f"Nonaktifkan keanggotaan '{data['nama']}' (status keluar)?\nAnggota yang keluar tidak bisa mengambil pinjaman baru."
        )

        jawaban = QMessageBox.question(
            self, "Konfirmasi Status Anggota", pesan,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if jawaban == QMessageBox.StandardButton.Yes:
            set_status_anggota(self.conn, anggota_id, status=status_baru, tanggal_keluar=tgl_hari_ini)
            self.muat_data()

    def _hapus_anggota(self) -> None:
        data = self._data_baris_terpilih()
        if not data:
            return

        anggota_id = data["id"]
        nama_anggota = data["nama"]

        # Dialog konfirmasi eksplisit dengan nama anggota dan default fokus di Batal
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Konfirmasi Hapus Anggota")
        dlg.setText(f"Hapus anggota {nama_anggota}?")
        dlg.setInformativeText("Tindakan ini tidak bisa dibatalkan.")
        dlg.setIcon(QMessageBox.Icon.Warning)

        btn_hapus = dlg.addButton("Hapus", QMessageBox.ButtonRole.DestructiveRole)
        btn_hapus.setStyleSheet("""
            QPushButton {
                background-color: #DC2626; color: white; font-weight: bold;
                border-radius: 5px; padding: 6px 18px;
            }
            QPushButton:hover { background-color: #B91C1C; }
        """)

        btn_batal = dlg.addButton("Batal", QMessageBox.ButtonRole.RejectRole)
        btn_batal.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9; color: #334155; font-weight: 500;
                border: 1px solid #CBD5E1; border-radius: 5px; padding: 6px 18px;
            }
            QPushButton:hover { background-color: #E2E8F0; }
        """)

        dlg.setDefaultButton(btn_batal)
        dlg.exec()

        if dlg.clickedButton() == btn_hapus:
            try:
                hapus_anggota_jika_tanpa_transaksi(self.conn, anggota_id)
                QMessageBox.information(self, "Berhasil", f"Data anggota '{nama_anggota}' berhasil dihapus.")
                self.muat_data()
            except ValueError as err:
                QMessageBox.warning(self, "Tidak Dapat Dihapus", str(err))
