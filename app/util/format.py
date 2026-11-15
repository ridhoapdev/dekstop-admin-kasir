"""
app/util/format.py — Utilitas format uang, tanggal, dan sanitasi string.
"""
from datetime import datetime
from typing import Union, Optional

BULAN_INDONESIA = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mei", 6: "Jun",
    7: "Jul", 8: "Agt", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Des"
}


def format_rupiah(nominal: Union[int, float]) -> str:
    """Format integer rupiah menjadi Rp 1.250.000"""
    try:
        nominal_int = int(nominal)
        format_ribuan = f"{nominal_int:,}".replace(",", ".")
        return f"Rp {format_ribuan}"
    except (ValueError, TypeError):
        return "Rp 0"


def format_tanggal_indo(iso_date_str: Optional[str]) -> str:
    """Mengubah format YYYY-MM-DD menjadi 14 Nov 2026"""
    if not iso_date_str:
        return "-"
    try:
        tgl = datetime.strptime(iso_date_str[:10], "%Y-%m-%d")
        nama_bulan = BULAN_INDONESIA.get(tgl.month, "")
        return f"{tgl.day} {nama_bulan} {tgl.year}"
    except Exception:
        return iso_date_str

