"""
app/util/teks.py — Utilitas sanitasi dan escape teks untuk UI PySide6.
Menangani karakter khusus seperti '&' yang oleh Qt dianggap sebagai pintasan mnemonic (shortcut underscore).
"""
import re


def escape_teks_ui(teks: str) -> str:
    """
    Mengganti karakter tunggal '&' menjadi 'dan' atau '&&' agar tidak tampil sebagai garis bawah (underscore) di Qt.
    Contoh: 'Simpan & Keluar' -> 'Simpan dan Keluar'.
    Jika teks sudah '&&', dibiarkan tetap '&&'.
    """
    if not teks:
        return ""
    # Ganti ' & ' menjadi ' dan '
    hasil = re.sub(r"\s+&\s+", " dan ", teks)
    # Jika masih ada '&' yang bukan '&&', ubah jadi 'dan'
    hasil = re.sub(r"(?<!&)&(?!&)", " dan ", hasil)
    return hasil

