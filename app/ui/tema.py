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
    font-size: 11pt;
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

/* Tombol (Button) Standar: Tinggi Konsisten 38px, Lega, Elegan, Padding Rapi */
QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 0 16px;
    min-height: 38px;
    max-height: 38px;
    font-weight: 600;
    color: #334155;
}

QPushButton:hover {
    background-color: #F1F5F9;
    border-color: #94A3B8;
}

QPushButton:pressed {
    background-color: #E2E8F0;
}

QPushButton:disabled {
    background-color: #F1F5F9;
    color: #94A3B8;
    border-color: #E2E8F0;
}

/* Tombol Aksi Utama (Biru) */
QPushButton[tipe="utama"] {
    background-color: #2563EB;
    border: 1px solid #1D4ED8;
    color: #FFFFFF;
}

QPushButton[tipe="utama"]:hover {
    background-color: #1D4ED8;
}

/* Tombol Aksi Sukses (Hijau) */
QPushButton[tipe="sukses"] {
    background-color: #10B981;
    border: 1px solid #059669;
    color: #FFFFFF;
}

QPushButton[tipe="sukses"]:hover {
    background-color: #059669;
}

/* Tombol Bahaya / Batalkan (Merah) */
QPushButton[tipe="bahaya"] {
    background-color: #DC2626;
    border: 1px solid #B91C1C;
    color: #FFFFFF;
}

QPushButton[tipe="bahaya"]:hover {
    background-color: #B91C1C;
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

/* Tabel (QTableWidget) Rapi, Bersih, Header Tidak Berhimpitan */
QTableWidget {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    gridline-color: #F1F5F9;
    selection-background-color: #E0E7FF;
    selection-color: #1E293B;
    outline: none;
}

QHeaderView::section {
    background-color: #F8FAFC;
    color: #475569;
    padding: 8px 12px;
    border: none;
    border-bottom: 2px solid #CBD5E1;
    border-right: 1px solid #E2E8F0;
    font-weight: 700;
    font-size: 10.5pt;
}

QTableWidget::item {
    padding: 6px 10px;
}

QTableWidget::item:selected {
    background-color: #EFF6FF;
    color: #1E3A8A;
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

