"""
app/ui/komponen/grafik_batang_qt.py — Komponen grafik batang kas masuk vs keluar ringan berbasis QPainter.
Menampilkan perbandingan arus kas bulanan secara responsif, cepat, tanpa dependensi berat (zero heavy memory overhead),
serta aman untuk target PC rendah (i3-3220, RAM 4 GB).
"""
from typing import List, Dict, Any
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PySide6.QtCore import Qt, QRectF


class WidgetGrafikBatangTahunan(QWidget):
    """Widget grafik batang interaktif ringan untuk 12 bulan."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data_12_bulan: List[Dict[str, Any]] = []
        self.setMinimumHeight(180)
        self.setMaximumHeight(240)
        self.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px;")

    def set_data(self, data_12_bulan: List[Dict[str, Any]]) -> None:
        self.data_12_bulan = data_12_bulan or []
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.setPen(QPen(QColor("#E2E8F0"), 1))
        painter.drawRoundedRect(0, 0, w - 1, h - 1, 8, 8)

        if not self.data_12_bulan:
            painter.setPen(QColor("#94A3B8"))
            painter.setFont(QFont("Segoe UI", 11))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Belum ada data untuk ditampilkan.")
            painter.end()
            return

        # Judul & Legend
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.setPen(QColor("#1E293B"))
        painter.drawText(16, 22, "Grafik Arus Kas Bulanan (Kas Masuk vs Kas Keluar)")

        # Legend Hijau (Masuk)
        painter.setBrush(QBrush(QColor("#10B981")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(w - 180, 12, 12, 12, 3, 3)
        painter.setPen(QColor("#334155"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(w - 164, 22, "Kas Masuk")

        # Legend Merah (Keluar)
        painter.setBrush(QBrush(QColor("#EF4444")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(w - 95, 12, 12, 12, 3, 3)
        painter.setPen(QColor("#334155"))
        painter.drawText(w - 79, 22, "Kas Keluar")

        # Area Plot
        margin_left = 30
        margin_right = 20
        margin_top = 40
        margin_bottom = 30

        plot_w = w - margin_left - margin_right
        plot_h = h - margin_top - margin_bottom

        # Garis Dasar (Baseline)
        painter.setPen(QPen(QColor("#CBD5E1"), 1.5))
        painter.drawLine(margin_left, h - margin_bottom, margin_left + plot_w, h - margin_bottom)

        max_val = max([max(b.get("kas_masuk", 0), b.get("kas_keluar", 0)) for b in self.data_12_bulan] + [100000])

        slot_w = plot_w / 12
        bar_w = max(4.0, min(slot_w * 0.35, 20.0))

        singkatan = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

        for idx, b in enumerate(self.data_12_bulan):
            x_center = margin_left + idx * slot_w + (slot_w / 2)
            masuk = b.get("kas_masuk", 0)
            keluar = b.get("kas_keluar", 0)

            h_masuk = (masuk / max_val) * (plot_h - 10)
            h_keluar = (keluar / max_val) * (plot_h - 10)

            # Batang Kas Masuk
            x_masuk = x_center - bar_w - 1
            y_masuk = (h - margin_bottom) - h_masuk
            painter.setBrush(QBrush(QColor("#10B981")))
            painter.setPen(Qt.PenStyle.NoPen)
            if h_masuk > 0:
                painter.drawRoundedRect(QRectF(x_masuk, y_masuk, bar_w, h_masuk), 2, 2)

            # Batang Kas Keluar
            x_keluar = x_center + 1
            y_keluar = (h - margin_bottom) - h_keluar
            painter.setBrush(QBrush(QColor("#EF4444")))
            if h_keluar > 0:
                painter.drawRoundedRect(QRectF(x_keluar, y_keluar, bar_w, h_keluar), 2, 2)

            # Label Nama Bulan di bawah garis
            painter.setPen(QColor("#64748B"))
            painter.setFont(QFont("Segoe UI", 9))
            lbl = singkatan[idx] if idx < len(singkatan) else str(idx + 1)
            painter.drawText(
                QRectF(x_center - (slot_w / 2), h - margin_bottom + 5, slot_w, 20),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                lbl
            )

        painter.end()

