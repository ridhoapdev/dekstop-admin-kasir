"""
app/ui/tema.py — Tema global, font rapi (Segoe UI), dan stylesheet terpadu untuk aplikasi desktop.
Menjamin kenyamanan visual, spasi/padding tombol yang lega (tidak mepet/terpotong),
header tabel proporsional, serta kontras warna yang ramah di mata.
"""

from pathlib import Path

# Font Segoe UI standar modern Windows yang sangat nyaman dibaca
FONT_KELUARGA = "Segoe UI"
FONT_UKURAN_DASAR = 11

_DIR_ASET = Path(__file__).resolve().parent.parent / "aset"
_ICON_PANAH = (_DIR_ASET / "panah_bawah.png").as_posix()
_ICON_PANAH_HOVER = (_DIR_ASET / "panah_bawah_hover.png").as_posix()
_ICON_PANAH_ATAS = (_DIR_ASET / "panah_atas.png").as_posix()
_ICON_PANAH_ATAS_HOVER = (_DIR_ASET / "panah_atas_hover.png").as_posix()

_CSS_PANAH = f"""
/* Panah dropdown halus elegan */
QComboBox::down-arrow, QDateEdit::down-arrow {{
    image: url({_ICON_PANAH});
    width: 12px;
    height: 12px;
}}

QComboBox::down-arrow:hover, QDateEdit::down-arrow:hover {{
    image: url({_ICON_PANAH_HOVER});
}}

/* Tombol SpinBox & DoubleSpinBox (Tenor, Jasa, dll) yang Elegan & Senada */
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 26px;
    border-left: 1px solid #CBD5E1;
    border-bottom: 0.5px solid #CBD5E1;
    border-top-right-radius: 6px;
    background-color: #F8FAFC;
}}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
    background-color: #F1F5F9;
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({_ICON_PANAH_ATAS});
    width: 10px;
    height: 10px;
}}

QSpinBox::up-arrow:hover, QDoubleSpinBox::up-arrow:hover {{
    image: url({_ICON_PANAH_ATAS_HOVER});
}}

QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 26px;
    border-left: 1px solid #CBD5E1;
    border-top: 0.5px solid #CBD5E1;
    border-bottom-right-radius: 6px;
    background-color: #F8FAFC;
}}

QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: #F1F5F9;
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({_ICON_PANAH});
    width: 10px;
    height: 10px;
}}

QSpinBox::down-arrow:hover, QDoubleSpinBox::down-arrow:hover {{
    image: url({_ICON_PANAH_HOVER});
}}
"""

STYLE_GLOBAL = """
/* Reset Font Dasar & Warna Latar */
QWidget {
    font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    color: #1E293B;
}

QMainWindow, QDialog {
    background-color: #F8FAFC;
}

/* Menu Bar Rapi & Lega */
QMenuBar {
    background-color: #FFFFFF;
    border-bottom: 1px solid #E2E8F0;
    padding: 2px 8px;
    font-size: 11pt;
}

QMenuBar::item {
    padding: 6px 14px;
    background: transparent;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #EFF6FF;
    color: #1D4ED8;
}

QMenu {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 6px 0;
}

QMenu::item {
    padding: 8px 24px;
}

QMenu::item:selected {
    background-color: #EFF6FF;
    color: #1D4ED8;
}

/* Tombol (Button) Standar: Tinggi Konsisten 38px, Solid, Elegan, Kontras Jelas */
QPushButton {
    background-color: #F1F5F9;
    border: 1.5px solid #94A3B8;
    border-radius: 6px;
    padding: 0 16px;
    min-height: 38px;
    font-weight: 600;
    color: #0F172A;
    outline: none;
}

QPushButton:hover {
    background-color: #E2E8F0;
    border-color: #64748B;
    color: #020617;
}

QPushButton:pressed {
    background-color: #CBD5E1;
    border-color: #475569;
}

QPushButton:focus {
    outline: none;
    border-color: #3B82F6;
}

QPushButton:disabled {
    background-color: #F8FAFC;
    color: #94A3B8;
    border-color: #E2E8F0;
}

/* Tombol Aksi Utama (Biru) */
QPushButton[tipe="utama"] {
    background-color: #2563EB;
    border: 1.5px solid #1D4ED8;
    color: #FFFFFF;
}

QPushButton[tipe="utama"]:hover {
    background-color: #1D4ED8;
    border-color: #1E40AF;
    color: #FFFFFF;
}

/* Tombol Aksi Sukses (Hijau) */
QPushButton[tipe="sukses"] {
    background-color: #16A34A;
    border: 1.5px solid #15803D;
    color: #FFFFFF;
}

QPushButton[tipe="sukses"]:hover {
    background-color: #15803D;
    border-color: #166534;
    color: #FFFFFF;
}

/* Tombol Bahaya / Batalkan (Merah) */
QPushButton[tipe="bahaya"] {
    background-color: #DC2626;
    border: 1.5px solid #B91C1C;
    color: #FFFFFF;
}

QPushButton[tipe="bahaya"]:hover {
    background-color: #B91C1C;
    border-color: #991B1B;
    color: #FFFFFF;
}

/* Tombol Info / Segarkan (Biru Lembut Solid) */
QPushButton[tipe="info"] {
    background-color: #EFF6FF;
    border: 1.5px solid #93C5FD;
    color: #1D4ED8;
}

QPushButton[tipe="info"]:hover {
    background-color: #DBEAFE;
    border-color: #60A5FA;
    color: #1E40AF;
}

/* Input Fields (QLineEdit, QComboBox, QDateEdit, QTextEdit) */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox {
    background-color: #FFFFFF;
    border: 1.5px solid #CBD5E1;
    border-radius: 6px;
    padding: 0 10px;
    min-height: 38px;
    max-height: 38px;
    selection-background-color: #3B82F6;
}

/* Styling Dropdown QComboBox & QDateEdit yang Bersih, Modern, dan Panah Minimalis */
QComboBox::drop-down, QDateEdit::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid #E2E8F0;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: #F8FAFC;
}

QComboBox::drop-down:hover, QDateEdit::drop-down:hover {
    background-color: #F1F5F9;
}

/* Panah dropdown akan digabung dari _CSS_PANAH */

QComboBox QAbstractItemView {
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    background-color: #FFFFFF;
    selection-background-color: #EFF6FF;
    selection-color: #1D4ED8;
    padding: 4px;
    outline: none;
}

QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
    border-color: #3B82F6;
    background-color: #FFFFFF;
}

QTextEdit {
    background-color: #FFFFFF;
    border: 1.5px solid #CBD5E1;
    border-radius: 6px;
    padding: 8px;
}

/* Tabel (QTableWidget) Rapi, Bersih, Header Tidak Berhimpitan (Standar Global) */
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

QHeaderView:vertical {
    width: 0px;
    border: none;
}

QHeaderView::section:vertical {
    width: 0px;
    height: 0px;
    padding: 0px;
    margin: 0px;
    border: none;
    background: transparent;
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

/* ScrollBar Ramping */
QScrollBar:vertical {
    border: none;
    background: #F8FAFC;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #CBD5E1;
    min-height: 25px;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* GroupBox & Status Bar */
QGroupBox {
    font-weight: 700;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
    background-color: #FFFFFF;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 10px;
    left: 12px;
    color: #1E293B;
}

QStatusBar {
    background-color: #FFFFFF;
    border-top: 1px solid #E2E8F0;
    color: #64748B;
    font-size: 10pt;
    padding: 4px 8px;
}
""" + _CSS_PANAH

from PySide6.QtWidgets import QPushButton

GAYA_TOMBOL = {
    "utama": (
        "QPushButton { background-color: #2563EB; color: #FFFFFF; border: 1.5px solid #1D4ED8; "
        "border-radius: 6px; padding: 0 16px; font-weight: bold; min-height: 38px; outline: none; } "
        "QPushButton:hover { background-color: #1D4ED8; } "
        "QPushButton:pressed { background-color: #1E40AF; } "
        "QPushButton:disabled { background-color: #93C5FD; color: #FFFFFF; border: 1.5px solid #BFDBFE; }"
    ),
    "sukses": (
        "QPushButton { background-color: #16A34A; color: #FFFFFF; border: 1.5px solid #15803D; "
        "border-radius: 6px; padding: 0 16px; font-weight: bold; min-height: 38px; outline: none; } "
        "QPushButton:hover { background-color: #15803D; } "
        "QPushButton:pressed { background-color: #166534; } "
        "QPushButton:disabled { background-color: #86EFAC; color: #FFFFFF; border: 1.5px solid #BBF7D0; }"
    ),
    "bahaya": (
        "QPushButton { background-color: #DC2626; color: #FFFFFF; border: 1.5px solid #B91C1C; "
        "border-radius: 6px; padding: 0 16px; font-weight: bold; min-height: 38px; outline: none; } "
        "QPushButton:hover { background-color: #B91C1C; } "
        "QPushButton:pressed { background-color: #991B1B; } "
        "QPushButton:disabled { background-color: #FCA5A5; color: #FFFFFF; border: 1.5px solid #FECACA; }"
    ),
    "info": (
        "QPushButton { background-color: #EFF6FF; color: #1D4ED8; border: 1.5px solid #93C5FD; "
        "border-radius: 6px; padding: 0 16px; font-weight: bold; min-height: 38px; outline: none; } "
        "QPushButton:hover { background-color: #DBEAFE; border-color: #60A5FA; } "
        "QPushButton:pressed { background-color: #BFDBFE; } "
        "QPushButton:disabled { background-color: #F8FAFC; color: #94A3B8; border: 1.5px solid #E2E8F0; }"
    ),
    "netral": (
        "QPushButton { background-color: #F1F5F9; color: #0F172A; border: 1.5px solid #94A3B8; "
        "border-radius: 6px; padding: 0 16px; font-weight: 600; min-height: 38px; outline: none; } "
        "QPushButton:hover { background-color: #E2E8F0; border-color: #64748B; color: #020617; } "
        "QPushButton:pressed { background-color: #CBD5E1; } "
        "QPushButton:disabled { background-color: #F8FAFC; color: #94A3B8; border: 1.5px solid #E2E8F0; }"
    ),
}

_asli_set_property = QPushButton.setProperty

def _set_property_tombol_aman(self, nama: str, nilai):
    hasil = _asli_set_property(self, nama, nilai)
    if nama == "tipe" and isinstance(nilai, str) and nilai in GAYA_TOMBOL:
        self.setStyleSheet(GAYA_TOMBOL[nilai])
    return hasil

QPushButton.setProperty = _set_property_tombol_aman

