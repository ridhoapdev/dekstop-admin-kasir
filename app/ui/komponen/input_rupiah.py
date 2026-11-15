"""
app/ui/komponen/input_rupiah.py — Komponen kustom QLineEdit untuk input nominal uang rupiah.
Fitur:
- Otomatis memformat pemisah ribuan dengan titik (contoh: 1.000.000) saat pengguna mengetik secara langsung (live formatting).
- Menjaga posisi kursor teks agar nyaman diedit di tengah maupun di akhir angka.
- Hanya menerima karakter digit angka (mencegah salah ketik huruf atau simbol).
- Menyediakan metode ambil_nilai() -> int dan set_nilai(int).
"""
import re
from PySide6.QtWidgets import QLineEdit
from PySide6.QtGui import QKeyEvent
from PySide6.QtCore import Qt


class InputRupiah(QLineEdit):
    """
    QLineEdit yang memformat angka ribuan Indonesia (menggunakan titik) secara otomatis.
    Contoh: Mengetik 1000000 langsung tampil sebagai '1.000.000'.
    """

    def __init__(self, parent=None, placeholder: str = "0"):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.textEdited.connect(self._on_text_edited)

    def _on_text_edited(self, text: str) -> None:
        """Memformat teks secara otomatis dengan pemisah ribuan titik tanpa merusak posisi kursor."""
        cursor_pos = self.cursorPosition()
        teks_sebelum_kursor = text[:cursor_pos]
        # Hitung berapa banyak digit angka murni di sebelah kiri posisi kursor saat ini
        digit_sebelum_kursor = len(re.sub(r"\D", "", teks_sebelum_kursor))

        # Ambil seluruh digit murni
        digit_murni = re.sub(r"\D", "", text)
        if not digit_murni:
            self.blockSignals(True)
            self.setText("")
            self.blockSignals(False)
            self.textChanged.emit("")
            return

        # Format ribuan dengan titik
        angka_int = int(digit_murni)
        teks_terformat = f"{angka_int:,}".replace(",", ".")

        # Hitung kembali posisi kursor baru yang sesuai dengan jumlah digit sebelum kursor
        posisi_kursor_baru = 0
        digit_terhitung = 0
        for char in teks_terformat:
            if digit_terhitung == digit_sebelum_kursor:
                break
            if char.isdigit():
                digit_terhitung += 1
            posisi_kursor_baru += 1

        self.blockSignals(True)
        self.setText(teks_terformat)
        self.setCursorPosition(posisi_kursor_baru)
        self.blockSignals(False)
        self.textChanged.emit(teks_terformat)

    def ambil_nilai(self) -> int:
        """Mengembalikan nilai nominal dalam bentuk integer rupiah murni."""
        digit_murni = re.sub(r"\D", "", self.text())
        return int(digit_murni) if digit_murni else 0

    def set_nilai(self, nominal: int) -> None:
        """Mengisi nilai dari integer ke tampilan berformat titik."""
        if nominal <= 0:
            if nominal == 0:
                self.setText("0")
            else:
                self.setText("")
            return
        teks_terformat = f"{int(nominal):,}".replace(",", ".")
        self.setText(teks_terformat)

