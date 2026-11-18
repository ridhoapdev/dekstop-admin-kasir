"""
app/ui/komponen/sidebar.py — Komponen Sidebar Navigasi Modern (3 Level).
Hierarki:
1. Link Langsung: Dasbor Utama (tanpa dropdown, tanpa chevron).
2. Grup (Dropdown Accordion): Ikon 20px, label Title Case, chevron beranimasi di kanan.
3. Anak Menu: Indentasi 40px, garis vertikal pemandu 1px, titik bullet 4px.
Footer: Backup Sekarang & Keluar Aplikasi terpisah, selalu terlihat.
Mode Terlipat: 64px (hanya ikon + tooltip), mode normal 248px.
"""
import sqlite3
from typing import Dict, List, Optional, Callable

from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QMessageBox, QDialog, QGraphicsOpacityEffect, QButtonGroup,
    QApplication
)
from PySide6.QtGui import (
    QFont, QCursor, QIcon, QPixmap, QPainter, QColor, QPen, QPainterPath,
    QKeyEvent
)
from PySide6.QtCore import (
    Qt, QRectF, QSize, QPropertyAnimation, QEasingCurve, QVariantAnimation,
    Signal, Slot
)

from app.layanan.backup import buat_backup, ambil_info_backup_terakhir


def buat_ikon_sidebar(nama: str, warna_hex: str = "#E2E8F0") -> QIcon:
    """Membuat set ikon vektor monokrom konsisten (stroke 1.75-2px, ukuran 20px)."""
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(warna_hex))
    pen.setWidthF(1.75)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    if nama == "dasbor":
        # Grid 4 kotak minimalis
        p.drawRoundedRect(QRectF(3, 3, 6, 6), 1.5, 1.5)
        p.drawRoundedRect(QRectF(11, 3, 6, 6), 1.5, 1.5)
        p.drawRoundedRect(QRectF(3, 11, 6, 6), 1.5, 1.5)
        p.drawRoundedRect(QRectF(11, 11, 6, 6), 1.5, 1.5)
    elif nama == "simpan_pinjam":
        # Ikon dompet / wallet
        p.drawRoundedRect(QRectF(2.5, 4, 15, 12), 2, 2)
        p.drawLine(2.5, 8.5, 17.5, 8.5)
        p.drawEllipse(QRectF(12.5, 11, 2, 2))
    elif nama == "toko":
        # Ikon kasir / belanja
        p.drawRoundedRect(QRectF(3, 6, 14, 11), 2, 2)
        path = QPainterPath()
        path.arcMoveTo(QRectF(7, 2, 6, 7), 0)
        path.arcTo(QRectF(7, 2, 6, 7), 0, 180)
        p.drawPath(path)
    elif nama == "stok_master":
        # Ikon kotak paket / inventori
        p.drawRoundedRect(QRectF(3, 3, 14, 14), 2, 2)
        p.drawLine(3, 7.5, 17, 7.5)
        p.drawLine(10, 7.5, 10, 17)
    elif nama == "laporan_sp":
        # Ikon diagram batang SP
        p.drawRoundedRect(QRectF(3, 2.5, 14, 15), 2, 2)
        p.drawLine(6, 13, 6, 10.5)
        p.drawLine(10, 13, 10, 7.5)
        p.drawLine(14, 13, 14, 5.5)
    elif nama == "laporan_toko":
        # Ikon analitik / tren toko
        p.drawRoundedRect(QRectF(3, 2.5, 14, 15), 2, 2)
        path = QPainterPath()
        path.moveTo(6, 12)
        path.lineTo(9.5, 8.5)
        path.lineTo(12, 10.5)
        path.lineTo(14.5, 6.5)
        p.drawPath(path)
    elif nama == "sistem":
        # Ikon database silinder
        p.drawEllipse(QRectF(3, 3, 14, 4.5))
        p.drawLine(3, 5.25, 3, 14.5)
        p.drawLine(17, 5.25, 17, 14.5)
        path = QPainterPath()
        path.arcMoveTo(QRectF(3, 12, 14, 5), 180)
        path.arcTo(QRectF(3, 12, 14, 5), 180, 180)
        p.drawPath(path)
    elif nama == "backup":
        # Ikon backup database
        p.drawRoundedRect(QRectF(3, 2.5, 14, 15), 2, 2)
        p.drawLine(10, 6, 10, 11.5)
        p.drawLine(7.5, 9, 10, 11.5)
        p.drawLine(12.5, 9, 10, 11.5)
        p.drawLine(6, 14, 14, 14)
    elif nama == "keluar":
        # Ikon logout pintu
        p.drawLine(14, 4, 17, 4)
        p.drawLine(17, 4, 17, 16)
        p.drawLine(17, 16, 14, 16)
        p.drawLine(4, 10, 13, 10)
        p.drawLine(10, 7, 13, 10)
        p.drawLine(10, 13, 13, 10)
    elif nama == "panah_kiri":
        p.drawLine(13, 5, 8, 10)
        p.drawLine(8, 10, 13, 15)
    elif nama == "panah_kanan":
        p.drawLine(8, 5, 13, 10)
        p.drawLine(13, 10, 8, 15)
    elif nama == "menu":
        p.drawLine(4, 6, 16, 6)
        p.drawLine(4, 10, 16, 10)
        p.drawLine(4, 14, 16, 14)
    p.end()
    return QIcon(pix)


def buat_ikon_chevron(sudut_derajat: float = 0.0, warna_hex: str = "#94A3B8") -> QIcon:
    """Membuat ikon chevron 16x16 dengan orientasi sudut rotasi halus."""
    pix = QPixmap(16, 16)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(8, 8)
    p.rotate(sudut_derajat)
    p.translate(-8, -8)

    pen = QPen(QColor(warna_hex))
    pen.setWidthF(1.75)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    # Menggambar chevron menghadap kanan (0 derajat = ▸)
    p.drawLine(6, 4, 11, 8)
    p.drawLine(11, 8, 6, 12)
    p.end()
    return QIcon(pix)


class TombolAnakNavigasi(QPushButton):
    """
    Item navigasi level 3 (anak menu dalam grup dropdown).
    Indentasi 40px dari tepi kiri dengan bullet titik halus dan garis pemandu.
    """

    def __init__(self, label: str, kunci: str, parent=None):
        super().__init__(label, parent)
        self.kunci = kunci
        self.setCheckable(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(40)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding-left: 40px;
                padding-right: 12px;
                border: none;
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 14px;
                font-weight: 400;
                color: #CBD5E1;
                background-color: transparent;
                outline: none;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.06);
                color: #FFFFFF;
            }
            QPushButton:focus {
                border: 2px solid #3B82F6;
            }
            QPushButton:checked {
                background-color: rgba(59, 130, 246, 0.18);
                color: #FFFFFF;
                font-weight: 600;
                border-left: 3px solid #3B82F6;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
                padding-left: 37px;
            }
        """)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Gambar titik bullet 4px di posisi x=24px (tengah antara garis pemandu x=18px dan teks x=40px)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        warna_bullet = QColor("#60A5FA") if self.isChecked() else QColor("#64748B")
        p.setBrush(warna_bullet)
        p.setPen(Qt.PenStyle.NoPen)
        cy = self.height() / 2.0
        p.drawEllipse(QRectF(22, cy - 2, 4, 4))
        p.end()


class GrupNavigasiAccordion(QWidget):
    """
    Komponen Level 2: Header Grup dengan Chevron di kanan dan daftar anak di dalamnya.
    Mendukung animasi rotasi chevron dan mode accordion terpadu.
    """

    status_berubah = Signal(object, bool)  # self, terbuka

    def __init__(self, judul: str, nama_ikon: str, kunci_sec: str, parent=None):
        super().__init__(parent)
        self.judul = judul
        self.nama_ikon = nama_ikon
        self.kunci_sec = kunci_sec
        self.terbuka = False
        self.anak_items: List[TombolAnakNavigasi] = []
        self._sudut_chevron = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header Tombol Grup (Tinggi 44px)
        self.btn_header = QPushButton(self)
        self.btn_header.setFixedHeight(44)
        self.btn_header.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_header.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_header.setStyleSheet("""
            QPushButton {
                text-align: left;
                border: none;
                border-radius: 6px;
                background-color: transparent;
                outline: none;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.06);
            }
            QPushButton:focus {
                border: 2px solid #3B82F6;
            }
        """)

        # Isi Header: Ikon 20px di kiri + Teks 15px Semibold + Chevron di Kanan
        h_layout = QHBoxLayout(self.btn_header)
        h_layout.setContentsMargins(12, 0, 12, 0)
        h_layout.setSpacing(10)

        self.lbl_ikon = QLabel(self.btn_header)
        self.lbl_ikon.setFixedSize(20, 20)
        self.lbl_ikon.setPixmap(buat_ikon_sidebar(nama_ikon, "#E2E8F0").pixmap(20, 20))
        h_layout.addWidget(self.lbl_ikon)

        self.lbl_judul = QLabel(judul, self.btn_header)
        self.lbl_judul.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        self.lbl_judul.setStyleSheet("color: #E2E8F0; font-size: 15px; font-weight: 600; border: none; background: transparent;")
        h_layout.addWidget(self.lbl_judul, 1)

        self.lbl_chevron = QLabel(self.btn_header)
        self.lbl_chevron.setFixedSize(16, 16)
        self.lbl_chevron.setPixmap(buat_ikon_chevron(0.0, "#94A3B8").pixmap(16, 16))
        h_layout.addWidget(self.lbl_chevron)

        self.btn_header.clicked.connect(self.toggle)
        layout.addWidget(self.btn_header)

        # Wadah Anak (Dengan garis vertikal pemandu 1px di x=18)
        self.wadah_anak = QFrame(self)
        self.wadah_anak.setStyleSheet("background-color: transparent; border: none;")
        self.lay_anak = QVBoxLayout(self.wadah_anak)
        self.lay_anak.setContentsMargins(0, 2, 0, 2)
        self.lay_anak.setSpacing(2)
        self.wadah_anak.hide()
        layout.addWidget(self.wadah_anak)

        # Animasi rotasi chevron
        self.anim_chevron = QVariantAnimation(self)
        self.anim_chevron.setDuration(160)
        self.anim_chevron.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.anim_chevron.valueChanged.connect(self._on_anim_chevron)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Jika terbuka dan ada anak, gambar garis pemandu vertikal di wadah anak
        if self.terbuka and self.anak_items and self.wadah_anak.isVisible():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(255, 255, 255, 31))  # rgba(255,255,255,0.12)
            pen.setWidthF(1.0)
            p.setPen(pen)
            
            top_y = float(self.btn_header.height() + 4)
            bottom_y = float(self.height() - 6)
            if bottom_y > top_y:
                p.drawLine(18.0, top_y, 18.0, bottom_y)
            p.end()

    def tambah_anak(self, btn_anak: TombolAnakNavigasi) -> None:
        self.anak_items.append(btn_anak)
        self.lay_anak.addWidget(btn_anak)

    def _on_anim_chevron(self, val):
        self._sudut_chevron = float(val)
        self.lbl_chevron.setPixmap(buat_ikon_chevron(self._sudut_chevron, "#94A3B8").pixmap(16, 16))

    def buka(self, emit_sinyal: bool = True) -> None:
        if not self.terbuka:
            self.terbuka = True
            self.wadah_anak.show()
            self.anim_chevron.stop()
            self.anim_chevron.setStartValue(self._sudut_chevron)
            self.anim_chevron.setEndValue(90.0)  # Menghadap ke bawah (▾)
            self.anim_chevron.start()
            self.update()
            if emit_sinyal:
                self.status_berubah.emit(self, True)

    def tutup(self, emit_sinyal: bool = True) -> None:
        if self.terbuka:
            self.terbuka = False
            self.wadah_anak.hide()
            self.anim_chevron.stop()
            self.anim_chevron.setStartValue(self._sudut_chevron)
            self.anim_chevron.setEndValue(0.0)  # Menghadap ke kanan (▸)
            self.anim_chevron.start()
            self.update()
            if emit_sinyal:
                self.status_berubah.emit(self, False)

    def toggle(self) -> None:
        if self.terbuka:
            self.tutup()
        else:
            self.buka()

    def set_sorot_anak_aktif(self, aktif: bool) -> None:
        """Jika ada anak aktif di dalam grup ini, beri teks putih + ikon aksen tanpa latar penuh."""
        if aktif:
            self.lbl_judul.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 600; border: none; background: transparent;")
            self.lbl_ikon.setPixmap(buat_ikon_sidebar(self.nama_ikon, "#60A5FA").pixmap(20, 20))
        else:
            self.lbl_judul.setStyleSheet("color: #E2E8F0; font-size: 15px; font-weight: 600; border: none; background: transparent;")
            self.lbl_ikon.setPixmap(buat_ikon_sidebar(self.nama_ikon, "#E2E8F0").pixmap(20, 20))

    def atur_mode_terlipat(self, terlipat: bool) -> None:
        """Penyesuaian saat sidebar terlipat / mini."""
        if terlipat:
            self.lbl_judul.hide()
            self.lbl_chevron.hide()
            self.wadah_anak.hide()
            self.btn_header.setToolTip(self.judul)
        else:
            self.lbl_judul.show()
            self.lbl_chevron.show()
            self.btn_header.setToolTip("")
            if self.terbuka:
                self.wadah_anak.show()


class KomponenSidebar(QFrame):
    """
    Komponen Bilah Samping (Sidebar) Mandiri.
    Mendukung mode normal (248px) dan mode terlipat (64px).
    """

    navigasi_diminta = Signal(str)

    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.terlipat = False
        self.grup_accordions: Dict[str, GrupNavigasiAccordion] = {}
        self.tombol_nav: Dict[str, QPushButton] = {}
        self.pemetaan_anak_ke_grup: Dict[str, str] = {}
        self.kunci_aktif_saat_ini: str = "ringkasan"

        self.grup_exclusive = QButtonGroup(self)
        self.grup_exclusive.setExclusive(True)

        self._inisialisasi_ui()

    def _inisialisasi_ui(self) -> None:
        self.setFixedWidth(248)
        self.setStyleSheet("""
            KomponenSidebar {
                background-color: #0F172A;
                border-right: 1px solid #1E293B;
            }
        """)

        layout_utama = QVBoxLayout(self)
        layout_utama.setContentsMargins(0, 0, 0, 0)
        layout_utama.setSpacing(0)

        # 1. Header Sidebar
        self.header_widget = QWidget(self)
        self.header_widget.setFixedHeight(64)
        self.header_widget.setStyleSheet("background-color: #0B1120; border-bottom: 1px solid #1E293B;")
        h_lay = QHBoxLayout(self.header_widget)
        h_lay.setContentsMargins(14, 0, 10, 0)
        h_lay.setSpacing(6)

        self.box_brand = QWidget(self.header_widget)
        b_lay = QVBoxLayout(self.box_brand)
        b_lay.setContentsMargins(0, 0, 0, 0)
        b_lay.setSpacing(2)

        self.lbl_brand_judul = QLabel("Koperasi dan Toko", self.box_brand)
        self.lbl_brand_judul.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.lbl_brand_judul.setStyleSheet("color: #F8FAFC; font-size: 16px; font-weight: 700; border: none; background: transparent;")
        b_lay.addWidget(self.lbl_brand_judul)

        self.lbl_brand_sub = QLabel("Sistem Terpadu", self.box_brand)
        self.lbl_brand_sub.setFont(QFont("Segoe UI", 9.5))
        self.lbl_brand_sub.setStyleSheet("color: #94A3B8; font-size: 13px; border: none; background: transparent;")
        b_lay.addWidget(self.lbl_brand_sub)

        h_lay.addWidget(self.box_brand, 1)

        self.btn_collapse = QPushButton(self.header_widget)
        self.btn_collapse.setFixedSize(32, 32)
        self.btn_collapse.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_collapse.setToolTip("Lipat menu")
        self.btn_collapse.setIcon(buat_ikon_sidebar("panah_kiri", "#94A3B8"))
        self.btn_collapse.setIconSize(QSize(18, 18))
        self.btn_collapse.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                outline: none;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }
        """)
        self.btn_collapse.clicked.connect(self.toggle_mode_lipat)
        h_lay.addWidget(self.btn_collapse)

        layout_utama.addWidget(self.header_widget)

        # 2. Area Scroll Navigasi
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea { background-color: #0F172A; border: none; }
            QScrollBar:vertical {
                border: none;
                background: #0F172A;
                width: 5px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #334155;
                min-height: 20px;
                border-radius: 2px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.nav_konten = QWidget()
        self.nav_konten.setStyleSheet("background-color: #0F172A;")
        self.nav_layout = QVBoxLayout(self.nav_konten)
        self.nav_layout.setContentsMargins(10, 10, 10, 12)
        self.nav_layout.setSpacing(4)

        # === LEVEL 1: LINK LANGSUNG DASBOR UTAMA (TANPA DROPDOWN / CHEVRON) ===
        self.btn_dasbor = QPushButton(self.nav_konten)
        self.btn_dasbor.setFixedHeight(44)
        self.btn_dasbor.setCheckable(True)
        self.btn_dasbor.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_dasbor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.btn_dasbor.setStyleSheet("""
            QPushButton {
                text-align: left;
                border: none;
                border-radius: 6px;
                background-color: transparent;
                outline: none;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.06);
            }
            QPushButton:focus {
                border: 2px solid #3B82F6;
            }
            QPushButton:checked {
                background-color: rgba(59, 130, 246, 0.18);
                border-left: 3px solid #3B82F6;
                border-top-left-radius: 0px;
                border-bottom-left-radius: 0px;
            }
        """)

        h_dasbor = QHBoxLayout(self.btn_dasbor)
        h_dasbor.setContentsMargins(12, 0, 12, 0)
        h_dasbor.setSpacing(10)

        self.lbl_dasbor_ikon = QLabel(self.btn_dasbor)
        self.lbl_dasbor_ikon.setFixedSize(20, 20)
        self.lbl_dasbor_ikon.setPixmap(buat_ikon_sidebar("dasbor", "#60A5FA").pixmap(20, 20))
        h_dasbor.addWidget(self.lbl_dasbor_ikon)

        self.lbl_dasbor_teks = QLabel("Dasbor Utama", self.btn_dasbor)
        self.lbl_dasbor_teks.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        self.lbl_dasbor_teks.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 600; border: none; background: transparent;")
        h_dasbor.addWidget(self.lbl_dasbor_teks, 1)

        self.btn_dasbor.clicked.connect(lambda: self._klik_item("ringkasan"))
        self.grup_exclusive.addButton(self.btn_dasbor)
        self.tombol_nav["ringkasan"] = self.btn_dasbor
        self.nav_layout.addWidget(self.btn_dasbor)

        # Garis Pemisah Tipis antara Link Langsung dan Grup
        self.garis_pemisah = QFrame(self.nav_konten)
        self.garis_pemisah.setFixedHeight(1)
        self.garis_pemisah.setStyleSheet("background-color: rgba(255, 255, 255, 0.08); border: none; margin: 4px 6px;")
        self.nav_layout.addWidget(self.garis_pemisah)

        # === LEVEL 2 & 3: GRUP DROPDOWN DAN ANAK MENU ===
        self._bangun_menu_grup()

        self.nav_layout.addStretch()
        scroll_area.setWidget(self.nav_konten)
        layout_utama.addWidget(scroll_area, 1)

        # 3. Footer Sidebar (Tempel di bawah, dipisah garis tipis, selalu terlihat)
        self.footer_widget = QWidget(self)
        self.footer_widget.setStyleSheet("background-color: #0B1120; border-top: 1px solid #1E293B;")
        f_lay = QVBoxLayout(self.footer_widget)
        f_lay.setContentsMargins(10, 12, 10, 12)
        f_lay.setSpacing(8)

        # Tombol Backup Sekarang (Outline Lebar Penuh)
        self.btn_backup = QPushButton(self.footer_widget)
        self.btn_backup.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_backup.setMinimumHeight(44)
        self.btn_backup.setToolTip("Cadangkan database koperasi dan toko sekarang")
        self.btn_backup.setStyleSheet("""
            QPushButton {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 6px;
                outline: none;
                text-align: left;
                padding-left: 10px;
                padding-right: 10px;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #60A5FA;
            }
            QPushButton:focus {
                border: 2px solid #3B82F6;
            }
        """)

        lay_btn_bk = QHBoxLayout(self.btn_backup)
        lay_btn_bk.setContentsMargins(4, 4, 4, 4)
        lay_btn_bk.setSpacing(8)

        self.lbl_bk_ikon = QLabel(self.btn_backup)
        self.lbl_bk_ikon.setFixedSize(20, 20)
        self.lbl_bk_ikon.setPixmap(buat_ikon_sidebar("backup", "#93C5FD").pixmap(20, 20))
        lay_btn_bk.addWidget(self.lbl_bk_ikon)

        self.box_bk_teks = QWidget(self.btn_backup)
        lay_bk_teks = QVBoxLayout(self.box_bk_teks)
        lay_bk_teks.setContentsMargins(0, 0, 0, 0)
        lay_bk_teks.setSpacing(1)

        self.lbl_bk_judul = QLabel("Backup Sekarang", self.box_bk_teks)
        self.lbl_bk_judul.setFont(QFont("Segoe UI", 9.5, QFont.Weight.DemiBold))
        self.lbl_bk_judul.setStyleSheet("color: #E2E8F0; font-size: 13.5px; font-weight: 600; border: none; background: transparent;")
        lay_bk_teks.addWidget(self.lbl_bk_judul)

        self.lbl_bk_sub = QLabel("Terakhir: -", self.box_bk_teks)
        self.lbl_bk_sub.setFont(QFont("Segoe UI", 8))
        self.lbl_bk_sub.setStyleSheet("color: #94A3B8; font-size: 11px; border: none; background: transparent;")
        lay_bk_teks.addWidget(self.lbl_bk_sub)

        lay_btn_bk.addWidget(self.box_bk_teks, 1)
        self.btn_backup.clicked.connect(self._jalankan_backup_dengan_indikator)
        f_lay.addWidget(self.btn_backup)

        # Tombol Keluar Aplikasi (Item Terpisah di Bawah Backup)
        self.btn_keluar = QPushButton(self.footer_widget)
        self.btn_keluar.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_keluar.setFixedHeight(38)
        self.btn_keluar.setToolTip("Keluar dari aplikasi")
        self.btn_keluar.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                outline: none;
                text-align: left;
                padding-left: 10px;
                padding-right: 10px;
            }
            QPushButton:hover {
                background-color: rgba(239, 68, 68, 0.12);
                border: 1px solid rgba(239, 68, 68, 0.25);
            }
            QPushButton:focus {
                border: 2px solid #EF4444;
            }
        """)

        lay_btn_klr = QHBoxLayout(self.btn_keluar)
        lay_btn_klr.setContentsMargins(4, 0, 4, 0)
        lay_btn_klr.setSpacing(8)

        self.lbl_klr_ikon = QLabel(self.btn_keluar)
        self.lbl_klr_ikon.setFixedSize(20, 20)
        self.lbl_klr_ikon.setPixmap(buat_ikon_sidebar("keluar", "#FCA5A5").pixmap(20, 20))
        lay_btn_klr.addWidget(self.lbl_klr_ikon)

        self.lbl_klr_teks = QLabel("Keluar Aplikasi", self.btn_keluar)
        self.lbl_klr_teks.setFont(QFont("Segoe UI", 9.5, QFont.Weight.DemiBold))
        self.lbl_klr_teks.setStyleSheet("color: #FCA5A5; font-size: 13.5px; font-weight: 600; border: none; background: transparent;")
        lay_btn_klr.addWidget(self.lbl_klr_teks, 1)

        self.btn_keluar.clicked.connect(self._konfirmasi_keluar)
        f_lay.addWidget(self.btn_keluar)

        layout_utama.addWidget(self.footer_widget)

        # Segarkan status info backup
        self.segarkan_info_backup()

    def _bangun_menu_grup(self) -> None:
        """Membangun 6 grup dropdown accordion dan item-item anak navigasi."""
        struktur = [
            ("simpan_pinjam", "Simpan Pinjam", "simpan_pinjam", [
                ("anggota", "Data Anggota"),
                ("simpanan", "Transaksi Simpanan"),
                ("pinjaman", "Data Pinjaman"),
                ("angsuran", "Pembayaran Angsuran"),
                ("kartu_anggota", "Kartu Anggota"),
                ("kas", "Buku Kas Operasional"),
                ("filter_cepat", "Filter Cepat"),
            ]),
            ("toko", "Operasional Toko", "toko", [
                ("penjualan", "Kasir Penjualan"),
                ("piutang", "Piutang Pembeli"),
                ("penitipan", "Penitipan Harian"),
                ("pembelian", "Pembelian Stok"),
            ]),
            ("stok_master", "Stok dan Master Barang", "stok_master", [
                ("barang", "Master Barang"),
                ("pihak", "Pihak Terkait"),
                ("stok", "Daftar Stok FIFO"),
                ("kartu_barang", "Kartu Barang"),
                ("retur", "Retur Barang"),
                ("opname", "Stock Opname"),
            ]),
            ("laporan_sp", "Laporan dan Closing SP", "laporan_sp", [
                ("laporan_mingguan", "Laporan Mingguan SP"),
                ("laporan_bulanan", "Laporan Bulanan SP"),
                ("laporan_tahunan", "Laporan Tahunan SP"),
                ("closing_sp", "Closing Bulanan SP"),
            ]),
            ("laporan_toko", "Laporan dan Closing Toko", "laporan_toko", [
                ("laporan_toko", "Laporan Toko Retail"),
                ("closing_toko", "Closing Unit Toko"),
            ]),
            ("sistem", "Sistem dan Data", "sistem", [
                ("impor", "Impor Data Excel"),
            ]),
        ]

        for kunci_sec, judul, nama_ikon, anak_list in struktur:
            grup = GrupNavigasiAccordion(judul, nama_ikon, kunci_sec, self.nav_konten)
            grup.status_berubah.connect(self._on_grup_status_berubah)
            self.grup_accordions[kunci_sec] = grup

            for kunci_btn, label_btn in anak_list:
                btn_anak = TombolAnakNavigasi(label_btn, kunci_btn, grup.wadah_anak)
                btn_anak.clicked.connect(lambda ch, k=kunci_btn: self._klik_item(k))
                self.grup_exclusive.addButton(btn_anak)
                self.tombol_nav[kunci_btn] = btn_anak
                self.pemetaan_anak_ke_grup[kunci_btn] = kunci_sec
                grup.tambah_anak(btn_anak)

            self.nav_layout.addWidget(grup)

    def _on_grup_status_berubah(self, grup_sumber: GrupNavigasiAccordion, terbuka: bool) -> None:
        """Mode Accordion: Ketika satu grup dibuka, tutup grup yang lain."""
        if terbuka:
            for g in self.grup_accordions.values():
                if g != grup_sumber and g.terbuka:
                    g.tutup(emit_sinyal=False)

    def _klik_item(self, kunci: str) -> None:
        self.kunci_aktif_saat_ini = kunci
        self.navigasi_diminta.emit(kunci)
        self.set_aktif(kunci)

    def set_aktif(self, kunci: str) -> None:
        """Menandai item navigasi aktif dan membuka grup accordion terkait secara otomatis."""
        self.kunci_aktif_saat_ini = kunci
        btn = self.tombol_nav.get(kunci)
        if btn and not btn.isChecked():
            btn.setChecked(True)

        if kunci == "ringkasan":
            self.lbl_dasbor_teks.setStyleSheet("color: #FFFFFF; font-size: 15px; font-weight: 600; border: none; background: transparent;")
            self.lbl_dasbor_ikon.setPixmap(buat_ikon_sidebar("dasbor", "#60A5FA").pixmap(20, 20))
            for g in self.grup_accordions.values():
                g.set_sorot_anak_aktif(False)
        else:
            self.lbl_dasbor_teks.setStyleSheet("color: #E2E8F0; font-size: 15px; font-weight: 600; border: none; background: transparent;")
            self.lbl_dasbor_ikon.setPixmap(buat_ikon_sidebar("dasbor", "#E2E8F0").pixmap(20, 20))

            kunci_grup = self.pemetaan_anak_ke_grup.get(kunci)
            for k_sec, g in self.grup_accordions.items():
                if k_sec == kunci_grup:
                    g.set_sorot_anak_aktif(True)
                    if not self.terlipat and not g.terbuka:
                        g.buka()
                else:
                    g.set_sorot_anak_aktif(False)

    def toggle_mode_lipat(self) -> None:
        """Beralih antara mode normal (248px) dan mode terlipat (64px)."""
        self.terlipat = not self.terlipat
        if self.terlipat:
            self.setFixedWidth(64)
            self.box_brand.hide()
            self.btn_collapse.setIcon(buat_ikon_sidebar("panah_kanan", "#94A3B8"))
            self.btn_collapse.setToolTip("Buka menu (248px)")

            self.lbl_dasbor_teks.hide()
            self.btn_dasbor.setToolTip("Dasbor Utama")

            for g in self.grup_accordions.values():
                g.atur_mode_terlipat(True)

            self.box_bk_teks.hide()
            self.btn_backup.setToolTip("Backup Sekarang")
            self.lbl_klr_teks.hide()
            self.btn_keluar.setToolTip("Keluar Aplikasi")
        else:
            self.setFixedWidth(248)
            self.box_brand.show()
            self.btn_collapse.setIcon(buat_ikon_sidebar("panah_kiri", "#94A3B8"))
            self.btn_collapse.setToolTip("Lipat menu")

            self.lbl_dasbor_teks.show()
            self.btn_dasbor.setToolTip("")

            for g in self.grup_accordions.values():
                g.atur_mode_terlipat(False)

            self.box_bk_teks.show()
            self.btn_backup.setToolTip("Cadangkan database koperasi dan toko sekarang")
            self.lbl_klr_teks.show()
            self.btn_keluar.setToolTip("Keluar dari aplikasi")

            # Pulihkan status grup yang aktif
            self.set_aktif(self.kunci_aktif_saat_ini)

    def segarkan_info_backup(self) -> None:
        try:
            info = ambil_info_backup_terakhir()
            if info:
                self.lbl_bk_sub.setText(f"Terakhir: {info}")
            else:
                self.lbl_bk_sub.setText("Terakhir: Belum ada")
        except Exception:
            self.lbl_bk_sub.setText("Terakhir: -")

    def _jalankan_backup_dengan_indikator(self) -> None:
        """Menampilkan indikator proses saat backup lalu memberikan notifikasi hasil."""
        self.lbl_bk_judul.setText("Mencadangkan...")
        self.btn_backup.setEnabled(False)
        QApplication.processEvents()

        try:
            file_hasil = buat_backup(self.conn)
            if file_hasil:
                self.segarkan_info_backup()
                QMessageBox.information(
                    self.window(),
                    "Backup Berhasil",
                    f"Salinan database berhasil dibuat dengan aman:\n{file_hasil.name}"
                )
        except Exception as err:
            QMessageBox.warning(
                self.window(),
                "Pemberitahuan Backup",
                f"Gagal melakukan backup database: {err}"
            )
        finally:
            self.lbl_bk_judul.setText("Backup Sekarang")
            self.btn_backup.setEnabled(True)

    def _konfirmasi_keluar(self) -> None:
        """Dialog konfirmasi keluar aplikasi dengan pilihan Batal dan Keluar."""
        dlg = QMessageBox(self.window())
        dlg.setWindowTitle("Konfirmasi Keluar")
        dlg.setText("Keluar dari aplikasi?")
        dlg.setInformativeText("Pastikan semua transaksi yang sedang diinput telah disimpan.")
        dlg.setIcon(QMessageBox.Icon.Question)

        btn_keluar = dlg.addButton("Keluar", QMessageBox.ButtonRole.AcceptRole)
        btn_keluar.setStyleSheet("""
            QPushButton {
                background-color: #DC2626; color: #FFFFFF; font-weight: bold;
                border-radius: 5px; padding: 6px 16px; min-width: 70px;
            }
            QPushButton:hover { background-color: #B91C1C; }
        """)

        btn_batal = dlg.addButton("Batal", QMessageBox.ButtonRole.RejectRole)
        btn_batal.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9; color: #334155; font-weight: 500;
                border: 1px solid #CBD5E1; border-radius: 5px; padding: 6px 16px; min-width: 70px;
            }
            QPushButton:hover { background-color: #E2E8F0; }
        """)

        dlg.setDefaultButton(btn_batal)
        dlg.exec()

        if dlg.clickedButton() == btn_keluar:
            self.window().close()
