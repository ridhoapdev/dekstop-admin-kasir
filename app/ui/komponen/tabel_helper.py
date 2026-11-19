"""
app/ui/komponen/tabel_helper.py — Standarisasi Tampilan, Style, dan Helper Tabel Global.
Dipakai oleh SEMUA tabel di seluruh aplikasi untuk memastikan konsistensi UI:
- Font isi 14px, header 13px semibold, tinggi baris 40px, padding sel horizontal 12px.
- Sembunyikan verticalHeader bawaan (row numbers) dan kolom ID database.
- Header latar #F1F5F9, teks #334155, border bawah 2px #CBD5E1.
- Tanpa garis vertikal antarkolom (setShowGrid(False)), border horizontal halus 1px #E5E7EB.
- Hover baris #EFF6FF, baris terpilih #DBEAFE dengan teks #0F172A (tetap stabil saat tabel kehilangan fokus).
- Kolom Status dirender dengan StatusBadgeDelegate (pill dengan titik warna).
- Rata header sama persis dengan isi: teks/tanggal rata kiri, angka/uang rata kanan.
- Pengurutan numerik akurat dengan NumericTableWidgetItem.
- Empty State terpadu dengan teks ramah dan tombol aksi.
"""
import re
from typing import List, Optional, Callable, Dict, Any

from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QWidget, QVBoxLayout,
    QLabel, QPushButton, QStyledItemDelegate, QStyleOptionViewItem, QStyle
)
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QCursor
from PySide6.QtCore import Qt, QRectF, QModelIndex, QSize


STYLE_TABEL_GLOBAL = """
QTableWidget {
    background-color: #FFFFFF;
    alternate-background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    font-family: 'Segoe UI';
    font-size: 14px;
    color: #1E293B;
    outline: none;
    gridline-color: transparent;
}

QTableWidget::item {
    padding-left: 12px;
    padding-right: 12px;
    border-bottom: 1px solid #E5E7EB;
    border-top: none;
    border-left: none;
    border-right: none;
}

QTableWidget::item:hover {
    background-color: #EFF6FF;
}

QTableWidget::item:selected {
    background-color: #DBEAFE;
    color: #0F172A;
}

QTableWidget::item:selected:!active {
    background-color: #DBEAFE;
    color: #0F172A;
}

QHeaderView::section {
    background-color: #F1F5F9;
    color: #334155;
    font-family: 'Segoe UI';
    font-size: 13px;
    font-weight: 600;
    padding: 8px 12px;
    border: none;
    border-bottom: 2px solid #CBD5E1;
}

QHeaderView::section:hover {
    background-color: #E2E8F0;
}

QHeaderView::down-arrow {
    width: 10px;
    height: 10px;
    padding-right: 4px;
}

QHeaderView::up-arrow {
    width: 10px;
    height: 10px;
    padding-right: 4px;
}

QScrollBar:vertical {
    border: none;
    background: #F8FAFC;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #CBD5E1;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    border: none;
    background: #F8FAFC;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #CBD5E1;
    min-width: 24px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal:hover {
    background: #94A3B8;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
"""


class StatusBadgeDelegate(QStyledItemDelegate):
    """
    Delegate untuk merender badge status pill yang cantik dan konsisten:
    - Aktif / Normal / Lunas / Selesai: Latar #DCFCE7, Teks #166534, Titik #16A34A
    - Keluar / Dibatalkan / Telat / Menunggak: Latar #FEE2E2, Teks #991B1B, Titik #DC2626
    - Draft / Tertutup / Lainnya: Latar #F1F5F9, Teks #475569, Titik #94A3B8
    """

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        teks = index.data(Qt.ItemDataRole.DisplayRole)
        if not teks:
            super().paint(painter, option, index)
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Latar seleksi baris tetap terjaga saat baris dipilih
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#DBEAFE"))

        teks_lower = str(teks).strip().lower()
        if teks_lower in ("aktif", "lunas", "selesai", "terbuka", "final", "normal"):
            bg_color = QColor("#DCFCE7")
            text_color = QColor("#166534")
            dot_color = QColor("#16A34A")
        elif "telat" in teks_lower or "menunggak" in teks_lower or "batal" in teks_lower or "keluar" in teks_lower:
            bg_color = QColor("#FEE2E2")
            text_color = QColor("#991B1B")
            dot_color = QColor("#DC2626")
        else:
            bg_color = QColor("#F1F5F9")
            text_color = QColor("#475569")
            dot_color = QColor("#94A3B8")

        # Ukuran pill
        font = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        painter.setFont(font)

        badge_w = 90
        badge_h = 24
        rect = option.rect
        x = rect.x() + 10
        y = rect.y() + (rect.height() - badge_h) / 2.0
        badge_rect = QRectF(x, y, badge_w, badge_h)

        # Gambar rounded pill
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, 12, 12)

        # Gambar titik bulat
        painter.setBrush(dot_color)
        dot_size = 6
        dot_x = x + 10
        dot_y = y + (badge_h - dot_size) / 2.0
        painter.drawEllipse(QRectF(dot_x, dot_y, dot_size, dot_size))

        # Gambar teks status
        painter.setPen(text_color)
        text_rect = QRectF(x + 22, y, badge_w - 24, badge_h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(teks))

        painter.restore()


class NumericTableWidgetItem(QTableWidgetItem):
    """
    QTableWidgetItem khusus angka/mata uang dengan:
    - Rata kanan otomatis (tabular figures)
    - Pengurutan numerik akurat (menggunakan nilai mentah integer/float)
    """

    def __init__(self, teks: str, nilai_mentah: float = 0.0):
        super().__init__(teks)
        self.nilai_mentah = float(nilai_mentah)
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self.nilai_mentah < other.nilai_mentah
        try:
            return self.nilai_mentah < float(other.nilai_mentah)
        except Exception:
            return super().__lt__(other)


class WidgetEmptyState(QWidget):
    """
    Overlay state saat tabel kosong atau hasil pencarian nihil.
    """

    def __init__(self, parent: QTableWidget):
        super().__init__(parent)
        self.tabel_induk = parent
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        self.lbl_pesan = QLabel(self)
        self.lbl_pesan.setFont(QFont("Segoe UI", 11))
        self.lbl_pesan.setStyleSheet("color: #64748B; font-size: 14px; text-align: center; border: none; background: transparent;")
        self.lbl_pesan.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_pesan)

        self.btn_aksi = QPushButton(self)
        self.btn_aksi.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_aksi.setMinimumHeight(36)
        self.btn_aksi.setStyleSheet("""
            QPushButton {
                background-color: #EFF6FF;
                color: #1D4ED8;
                border: 1px solid #93C5FD;
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 13px;
                font-weight: 600;
                padding: 0 16px;
                outline: none;
            }
            QPushButton:hover {
                background-color: #DBEAFE;
                border-color: #60A5FA;
            }
        """)
        self.btn_aksi.hide()
        layout.addWidget(self.btn_aksi, 0, Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def tampilkan(self, pesan: str, label_tombol: Optional[str] = None, callback_aksi: Optional[Callable] = None):
        self.lbl_pesan.setText(pesan)
        if label_tombol and callback_aksi:
            self.btn_aksi.setText(label_tombol)
            try:
                self.btn_aksi.disconnect()
            except Exception:
                pass
            self.btn_aksi.clicked.connect(callback_aksi)
            self.btn_aksi.show()
        else:
            self.btn_aksi.hide()

        self.sesuaikan_posisi()
        self.show()
        self.raise_()

    def sesuaikan_posisi(self):
        hdr_h = self.tabel_induk.horizontalHeader().height() if self.tabel_induk.horizontalHeader().isVisible() else 0
        w = self.tabel_induk.viewport().width()
        h = self.tabel_induk.viewport().height()
        self.setGeometry(0, hdr_h, w, max(h, 150))


def format_samarkan_nik(nik: Optional[str]) -> str:
    """
    Jika nomor pegawai (EMP-xxx), tampilkan apa adanya.
    Jika NIK 16 digit, samarkan 8 digit tengah (mis. 3201••••••••1234).
    """
    if not nik:
        return "-"
    nik_str = str(nik).strip()
    if re.match(r"^[A-Za-z]+-\d+", nik_str):
        return nik_str
    if len(nik_str) == 16 and nik_str.isdigit():
        return f"{nik_str[:4]}••••••••{nik_str[-4:]}"
    if len(nik_str) > 8:
        return f"{nik_str[:3]}••••{nik_str[-3:]}"
    return nik_str


def terapkan_style_tabel_global(
    tabel: QTableWidget,
    rata_kanan_kolom: Optional[List[int]] = None,
    rata_tengah_kolom: Optional[List[int]] = None,
    kolom_status: Optional[int] = None,
    kolom_sembunyi: Optional[List[int]] = None
) -> WidgetEmptyState:
    """
    Menerapkan konfigurasi tabel global yang konsisten ke QTableWidget mana pun:
    1. Sembunyikan verticalHeader bawaan (nomor baris 1, 2, 3...)
    2. Nonaktifkan grid vertikal (setShowGrid(False))
    3. Atur tinggi baris default 40px
    4. Terapkan stylesheet global
    5. Atur alignment header agar sejajar dengan isi kolom
    6. Aktifkan sorting dan seleksi satu baris penuh
    7. Pasang delegate status badge jika kolom status ditentukan
    8. Sembunyikan kolom ID jika diminta
    9. Kembalikan instans WidgetEmptyState untuk empty state handling
    """
    rata_kanan = set(rata_kanan_kolom or [])
    rata_tengah = set(rata_tengah_kolom or [])
    sembunyi = set(kolom_sembunyi or [])

    # 1. Konfigurasi struktur tabel
    tabel.verticalHeader().setVisible(False)
    tabel.verticalHeader().setDefaultSectionSize(40)
    tabel.setShowGrid(False)
    tabel.setAlternatingRowColors(True)
    tabel.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    tabel.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    tabel.setSortingEnabled(True)
    tabel.setStyleSheet(STYLE_TABEL_GLOBAL)

    # 2. Header horizontal
    hdr = tabel.horizontalHeader()
    hdr.setSortIndicatorShown(True)
    hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    for col in range(tabel.columnCount()):
        item = tabel.horizontalHeaderItem(col)
        align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        if col in rata_kanan:
            align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        elif col in rata_tengah:
            align = Qt.AlignmentFlag.AlignCenter
        
        if item:
            item.setTextAlignment(align)
        
        if col in sembunyi:
            tabel.setColumnHidden(col, True)

    # 3. Pasang delegate badge status
    if kolom_status is not None and 0 <= kolom_status < tabel.columnCount():
        tabel.setItemDelegateForColumn(kolom_status, StatusBadgeDelegate(tabel))

    # 4. Pasang overlay empty state
    empty_state = WidgetEmptyState(tabel)
    
    # Event resize handler untuk empty state
    old_resize = tabel.resizeEvent
    def on_resize(event):
        old_resize(event)
        empty_state.sesuaikan_posisi()
    tabel.resizeEvent = on_resize

    return empty_state
