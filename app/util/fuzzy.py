"""
app/util/fuzzy.py — Deteksi kemiripan nama (fuzzy matching) tanpa dependensi eksternal berat.
Menggunakan difflib.SequenceMatcher bawaan Python standar.
"""
from difflib import SequenceMatcher
from typing import List, Dict, Any, Tuple


def cari_nama_mirip(
    nama_baru: str,
    daftar_nama_ada: List[Tuple[int, str]],  # List of (id, nama)
    ambang_kemiripan: float = 0.75
) -> List[Dict[str, Any]]:
    """
    Mencari nama-nama yang mirip dalam daftar_nama_ada.
    Mengembalikan daftar entri yang memiliki kemiripan >= ambang_kemiripan (0.0 - 1.0).
    """
    nama_bersih = nama_baru.strip().lower()
    if not nama_bersih:
        return []

    hasil = []
    for item_id, nama_ada in daftar_nama_ada:
        ada_bersih = nama_ada.strip().lower()
        if nama_bersih == ada_bersih:
            rasio = 1.0
        else:
            rasio = SequenceMatcher(None, nama_bersih, ada_bersih).ratio()

        if rasio >= ambang_kemiripan:
            hasil.append({
                "id": item_id,
                "nama": nama_ada,
                "skor": rasio,
                "persen": int(round(rasio * 100))
            })

    hasil.sort(key=lambda x: x["skor"], reverse=True)
    return hasil
