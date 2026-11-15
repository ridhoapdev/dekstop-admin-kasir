"""
app/db/repo_laporan.py — Repositori data untuk Laporan Mingguan.
Murni database & aturan bisnis (tanpa GUI).
Sesuai SPEC.md 4.7 & RULES.md:
- Menghitung rentang tanggal minggu (default Senin - Minggu)
- Saldo kas awal (sebelum tanggal_awal)
- Total simpanan masuk (setor) & keluar (tarik)
- Total angsuran masuk (pokok, jasa, denda)
- Total pinjaman cair & biaya admin
- Total kas masuk & kas keluar
- Saldo kas akhir
- Rincian seluruh transaksi kas selama periode minggu tersebut
- Mencatat tanggal pembuatan laporan ke laporan_mingguan_log untuk pengingat
"""
import sqlite3
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
from app.logika.transaksi_efektif import (
    hitung_rekap_kas_bersih_rentang,
    ambil_daftar_transaksi_kas_lengkap
)


def tentukan_rentang_minggu(
    tanggal_patokan: Optional[date] = None, hari_awal: str = "senin"
) -> Tuple[date, date]:
    """
    Menghitung tanggal awal dan akhir minggu untuk tanggal patokan.
    Default: Senin s/d Minggu.
    """
    ref = tanggal_patokan or date.today()
    # Hari Senin = 0, Minggu = 6
    offset = ref.weekday()  # Jika hari Senin, offset 0
    tgl_awal = ref - timedelta(days=offset)
    tgl_akhir = tgl_awal + timedelta(days=6)
    return tgl_awal, tgl_akhir


def catat_log_laporan_mingguan(
    conn: sqlite3.Connection, tanggal_awal_iso: str, tanggal_akhir_iso: str
) -> None:
    """Mencatat pembuatan laporan mingguan agar pengingat dashboard hilang."""
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO laporan_mingguan_log (tanggal_awal, tanggal_akhir, dibuat_pada)
            VALUES (?, ?, datetime('now', 'localtime'));
            """,
            (tanggal_awal_iso, tanggal_akhir_iso)
        )


def ambil_data_laporan_mingguan(
    conn: sqlite3.Connection,
    tanggal_awal_iso: str,
    tanggal_akhir_iso: str,
    catat_log: bool = False,
    sembunyikan_dibatalkan: bool = True
) -> Dict[str, Any]:
    """
    Menghitung laporan mingguan lengkap BERSIH (efektif):
    - Saldo kas awal (sebelum tanggal_awal)
    - Total simpanan setor & tarik bersih
    - Total angsuran pokok, jasa, denda bersih
    - Total pencairan pinjaman & biaya admin bersih
    - Koreksi / pembatalan lintas periode (jika ada)
    - Arus kas masuk & keluar bersih
    - Saldo kas akhir
    - Daftar transaksi buku kas rinci selama periode dengan penanda status
    """
    rekap = hitung_rekap_kas_bersih_rentang(
        conn, tanggal_awal=tanggal_awal_iso, tanggal_akhir=tanggal_akhir_iso
    )

    daftar_transaksi = ambil_daftar_transaksi_kas_lengkap(
        conn,
        tanggal_awal=tanggal_awal_iso,
        tanggal_akhir=tanggal_akhir_iso,
        sembunyikan_dibatalkan=sembunyikan_dibatalkan
    )

    if catat_log:
        catat_log_laporan_mingguan(conn, tanggal_awal_iso, tanggal_akhir_iso)

    return {
        "tanggal_awal": tanggal_awal_iso,
        "tanggal_akhir": tanggal_akhir_iso,
        "saldo_kas_awal": rekap["saldo_kas_awal"],
        "total_simpanan_setor": rekap["simpanan_setor"],
        "total_simpanan_tarik": rekap["simpanan_tarik"],
        "total_angsuran_pokok": rekap["angsuran_pokok"],
        "total_angsuran_jasa": rekap["angsuran_jasa"],
        "total_angsuran_denda": rekap["angsuran_denda"],
        "total_angsuran_masuk": rekap["angsuran_total"],
        "total_pinjaman_cair": rekap["pencairan_pinjaman"],
        "total_biaya_admin": rekap["biaya_admin"],
        "total_kas_manual_masuk": rekap["kas_manual_masuk"],
        "total_kas_manual_keluar": rekap["kas_manual_keluar"],
        "koreksi_masuk_lintas": rekap["koreksi_masuk_lintas"],
        "koreksi_keluar_lintas": rekap["koreksi_keluar_lintas"],
        "jumlah_koreksi_lintas": rekap["jumlah_koreksi_lintas"],
        "total_kas_masuk": rekap["total_kas_masuk"],
        "total_kas_keluar": rekap["total_kas_keluar"],
        "saldo_kas_akhir": rekap["saldo_kas_akhir"],
        "daftar_transaksi": daftar_transaksi
    }
