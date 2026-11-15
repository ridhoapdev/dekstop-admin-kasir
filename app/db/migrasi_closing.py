"""
app/db/migrasi_closing.py — Skrip audit dan pembaruan angka closing lama.
Aturan:
- Untuk periode closing yang BELUM terkunci (mis. dibuka_kembali): hitung ulang angka bersih secara otomatis.
- Untuk periode closing yang SUDAH terkunci: JANGAN ubah diam-diam, melainkan laporkan rincian selisihnya.
"""
import sqlite3
from typing import List, Dict, Any
from app.logika.transaksi_efektif import hitung_rekap_kas_bersih_rentang


def audit_dan_migrasi_closing_lama(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Memeriksa seluruh baris di tabel `closing`.
    Mengembalikan laporan audit dan hasil migrasi.
    """
    cur = conn.cursor()
    cur.execute("SELECT * FROM closing ORDER BY periode ASC;")
    baris_closing = cur.fetchall()

    laporan: List[Dict[str, Any]] = []

    for c in baris_closing:
        periode = c["periode"]
        status = c["status"]
        rekap_bersih = hitung_rekap_kas_bersih_rentang(conn, periode=periode)

        selisih_masuk = c["total_kas_masuk"] - rekap_bersih["total_kas_masuk"]
        selisih_keluar = c["total_kas_keluar"] - rekap_bersih["total_kas_keluar"]
        ada_selisih = (selisih_masuk != 0 or selisih_keluar != 0)

        info: Dict[str, Any] = {
            "periode": periode,
            "status": status,
            "angka_lama": {
                "masuk": c["total_kas_masuk"],
                "keluar": c["total_kas_keluar"],
                "akhir": c["saldo_kas_akhir"]
            },
            "angka_bersih": {
                "masuk": rekap_bersih["total_kas_masuk"],
                "keluar": rekap_bersih["total_kas_keluar"],
                "akhir": rekap_bersih["saldo_kas_akhir"]
            },
            "ada_selisih": ada_selisih,
            "diperbarui": False
        }

        # Hanya perbarui jika status BUKAN tertutup (belum terkunci / dibuka_kembali)
        if status != "tertutup" and ada_selisih:
            with conn:
                conn.execute(
                    """
                    UPDATE closing 
                    SET total_kas_masuk = ?,
                        total_kas_keluar = ?,
                        saldo_kas_akhir = ?,
                        total_jasa_diterima = ?
                    WHERE id = ?;
                    """,
                    (
                        rekap_bersih["total_kas_masuk"],
                        rekap_bersih["total_kas_keluar"],
                        rekap_bersih["saldo_kas_akhir"],
                        rekap_bersih["angsuran_jasa"],
                        c["id"]
                    )
                )
            info["diperbarui"] = True

        laporan.append(info)

    return laporan

