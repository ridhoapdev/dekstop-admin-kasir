"""
app/db/repo_ringkasan_toko.py — Repositori Ringkasan Dasbor Toko (Single Source of Truth).
Menghitung angka-angka bersih (pembalik keluar):
- Penjualan hari ini
- Laba kotor hari ini
- Posisi kas toko saat ini
- Total piutang pembeli
- Hutang ke penitip hari ini
- Jumlah nota lewat jatuh tempo
- Jumlah barang di bawah stok minimum
"""
import sqlite3
from datetime import date
from typing import Dict, Any, Optional
from app.db.repo_kas_toko import hitung_saldo_kas_toko
from app.db.repo_piutang import hitung_total_piutang_semua_pembeli
from app.db.repo_penitipan import hitung_total_hutang_penitip_terkini


def ambil_ringkasan_dasbor_toko(conn: sqlite3.Connection, tanggal_patokan: Optional[str] = None) -> Dict[str, Any]:
    """Mengambil metrik ringkasan kartu toko secara akurat."""
    tgl = tanggal_patokan or date.today().isoformat()
    cur = conn.cursor()

    # 1. Penjualan Hari Ini & Laba Kotor Hari Ini (dari penjualan efektif)
    cur.execute(
        """
        SELECT 
            COALESCE(SUM(pj.total), 0) AS total_penjualan_hari_ini,
            COALESCE((
                SELECT SUM(pb.laba)
                FROM penjualan_baris pb
                JOIN v_penjualan_efektif p2 ON pb.penjualan_id = p2.id
                WHERE p2.tanggal = ? AND p2.status_efektif = 'NORMAL'
            ), 0) AS total_laba_hari_ini
        FROM v_penjualan_efektif pj
        WHERE pj.tanggal = ? AND pj.status_efektif = 'NORMAL';
        """,
        (tgl, tgl)
    )
    row_jual = cur.fetchone()
    jual_hari_ini = row_jual[0]
    laba_hari_ini = row_jual[1]

    # 2. Posisi Kas Toko Saat Ini
    kas_toko = hitung_saldo_kas_toko(conn)

    # 3. Total Piutang Pembeli
    total_piutang = hitung_total_piutang_semua_pembeli(conn)

    # 4. Hutang ke Penitip Hari Ini
    hutang_penitip = hitung_total_hutang_penitip_terkini(conn)

    # 5. Jumlah Nota Lewat Jatuh Tempo
    cur.execute(
        """
        SELECT COUNT(*)
        FROM v_penjualan_efektif pj
        WHERE pj.metode_bayar = 'kredit' AND pj.status_efektif = 'NORMAL'
          AND pj.jatuh_tempo < ?
          AND pj.total > (
              SELECT COALESCE(SUM(ap.jumlah), 0)
              FROM alokasi_piutang ap
              WHERE ap.penjualan_id = pj.id AND ap.membalik_id IS NULL
          );
        """,
        (tgl,)
    )
    nota_telat = cur.fetchone()[0]

    # 6. Jumlah Barang di Bawah Stok Minimum
    cur.execute(
        """
        SELECT COUNT(*)
        FROM barang
        WHERE aktif = 1 AND stok_saat_ini <= stok_minimum;
        """
    )
    stok_menipis = cur.fetchone()[0]

    return {
        "tanggal": tgl,
        "penjualan_hari_ini": jual_hari_ini,
        "laba_kotor_hari_ini": laba_hari_ini,
        "kas_toko": kas_toko,
        "total_piutang": total_piutang,
        "hutang_penitip": hutang_penitip,
        "jumlah_nota_telat": nota_telat,
        "jumlah_stok_menipis": stok_menipis
    }
