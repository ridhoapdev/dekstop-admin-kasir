"""
app/layanan/bus_sinyal.py — Event bus sederhana untuk komunikasi antar-komponen/layar.
Mendukung notifikasi pembaruan data real-time ke seluruh layar tanpa coupling ketat.
"""
from typing import Callable, Dict, List

_pendengar: Dict[str, List[Callable[[], None]]] = {}


def langganan(topik: str, callback: Callable[[], None]) -> None:
    """Mendaftarkan fungsi callback untuk suatu topik event."""
    if topik not in _pendengar:
        _pendengar[topik] = []
    if callback not in _pendengar[topik]:
        _pendengar[topik].append(callback)


def lepas_langganan(topik: str, callback: Callable[[], None]) -> None:
    """Melepaskan pendaftaran fungsi callback."""
    if topik in _pendengar and callback in _pendengar[topik]:
        _pendengar[topik].remove(callback)


def kirim_sinyal(topik: str) -> None:
    """Mengirim sinyal event ke semua callback yang terdaftar pada topik tersebut."""
    for cb in _pendengar.get(topik, []):
        try:
            cb()
        except Exception:
            pass
