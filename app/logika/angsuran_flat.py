"""
app/logika/angsuran_flat.py — Logika bisnis murni perhitungan jadwal angsuran flat.
Sesuai aturan RULES.md & DATABASE.md:
- TIDAK BOLEH mengimpor PySide6 (bisa diuji murni tanpa GUI).
- Uang = int rupiah penuh (Dilarang float untuk uang).
- Persen menggunakan decimal.Decimal, dibulatkan ke int.
- Rumus flat:
    pokok_dasar = plafon // tenor
    jasa_dasar = round(Decimal(plafon) * Decimal(str(persen)) / Decimal(100))
    Angsuran 1..(tenor-1): pokok = pokok_dasar, jasa = jasa_dasar
    Angsuran tenor (terakhir): pokok = plafon - pokok_dasar * (tenor - 1)
- Total pokok pas sama dengan plafon (SUM(pokok) == plafon).
- Tanggal jatuh tempo = tanggal cair + k bulan.
  Jika tanggal tidak ada di bulan tujuan (misal 31 Jan -> Feb), disesuaikan ke hari terakhir bulan tersebut.
"""
import calendar
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any


def tambah_bulan(tgl_awal: date, jumlah_bulan: int) -> date:
    """
    Menambahkan jumlah_bulan ke tgl_awal.
    Jika hari melebihi jumlah hari di bulan tujuan (misal 31 ke Feb),
    maka disesuaikan ke hari terakhir di bulan tujuan.
    """
    tahun = tgl_awal.year + (tgl_awal.month + jumlah_bulan - 1) // 12
    bulan = (tgl_awal.month + jumlah_bulan - 1) % 12 + 1
    
    # Ambil hari maksimal di bulan target
    _, hari_maksimal = calendar.monthrange(tahun, bulan)
    hari = min(tgl_awal.day, hari_maksimal)
    
    return date(tahun, bulan, hari)


def hitung_jadwal_angsuran_flat(
    plafon: int,
    tenor: int,
    jasa_persen_per_bulan: float,
    tanggal_cair_iso: str
) -> List[Dict[str, Any]]:
    """
    Menghitung jadwal angsuran lengkap dengan penanganan pembulatan di cicilan terakhir.
    Mengembalikan list dict:
    [
        {
            "angsuran_ke": 1,
            "jatuh_tempo": "2026-12-14",
            "pokok": 1000000,
            "jasa": 100000,
            "total_angsuran": 1100000
        },
        ...
    ]
    """
    if not isinstance(plafon, int) or plafon <= 0:
        raise ValueError("Plafon pinjaman harus berupa bilangan bulat rupiah lebih dari 0.")
    if not isinstance(tenor, int) or tenor <= 0:
        raise ValueError("Tenor pinjaman harus berupa bilangan bulat minimal 1 bulan.")
    if jasa_persen_per_bulan < 0:
        raise ValueError("Persen jasa pinjaman tidak boleh bernilai negatif.")

    tgl_cair = datetime.strptime(tanggal_cair_iso[:10], "%Y-%m-%d").date()

    # Hitung nilai dasar
    pokok_dasar = plafon // tenor
    
    # Hitung jasa memakai Decimal dengan pembulatan ROUND_HALF_UP ke integer rupiah
    d_plafon = Decimal(plafon)
    d_persen = Decimal(str(jasa_persen_per_bulan))
    d_jasa = (d_plafon * d_persen / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    jasa_dasar = int(d_jasa)

    jadwal: List[Dict[str, Any]] = []
    total_pokok_terhitung = 0

    for ke in range(1, tenor + 1):
        jatuh_tempo = tambah_bulan(tgl_cair, ke)
        
        if ke == tenor:
            # Cicilan terakhir menyerap selisih pembulatan
            pokok_cicilan = plafon - total_pokok_terhitung
        else:
            pokok_cicilan = pokok_dasar
            total_pokok_terhitung += pokok_cicilan

        jadwal.append({
            "angsuran_ke": ke,
            "jatuh_tempo": jatuh_tempo.strftime("%Y-%m-%d"),
            "pokok": pokok_cicilan,
            "jasa": jasa_dasar,
            "total_angsuran": pokok_cicilan + jasa_dasar
        })

    # Verifikasi integritas: total pokok harus persis sama dengan plafon
    sum_pokok = sum(item["pokok"] for item in jadwal)
    assert sum_pokok == plafon, f"Total pokok {sum_pokok} tidak sama dengan plafon {plafon}"

    return jadwal

