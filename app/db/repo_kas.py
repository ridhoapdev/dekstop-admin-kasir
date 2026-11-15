"""
app/db/repo_kas.py — Repositori akses data Buku Kas Operasional.
Murni database & aturan bisnis (tanpa GUI).
- Mencatat kas masuk atau keluar manual (sumber='manual', misal: ATK, listrik, modal kas, dll.)
- Mengambil daftar transaksi kas beserta saldo berjalan
- Mengecek periode terkunci sebelum mencatat kas manual
- Transaksi pembalik kas manual jika ada koreksi
"""
import sqlite3
from typing import List, Dict, Any, Optional
from app.db.repo_simpanan import cek_periode_terkunci


def tambah_kas_manual(
    conn: sqlite3.Connection,
    tanggal: str,
    keterangan: str,
    jenis_arus: str,  # 'masuk' atau 'keluar'
    nominal: int
) -> int:
    """Mencatat transaksi kas operasional manual (masuk atau keluar)."""
    ket = keterangan.strip()
    if not ket:
        raise ValueError("Keterangan transaksi kas wajib diisi.")
    if nominal <= 0:
        raise ValueError("Nominal kas harus lebih dari Rp 0.")
    if jenis_arus not in ("masuk", "keluar"):
        raise ValueError("Jenis arus kas harus 'masuk' atau 'keluar'.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Transaksi kas tidak dapat disimpan.")

    masuk = nominal if jenis_arus == "masuk" else 0
    keluar = nominal if jenis_arus == "keluar" else 0

    with conn:
        cur = conn.execute(
            """
            INSERT INTO kas_transaksi 
            (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
            VALUES (?, ?, ?, ?, 'manual', NULL, ?);
            """,
            (tanggal, ket, masuk, keluar, periode)
        )
        kas_id = cur.lastrowid
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            (
                "tambah",
                "kas_transaksi",
                kas_id,
                f"Kas manual {jenis_arus} Rp {nominal:,} - {ket}".replace(",", ".")
            )
        )
        return kas_id


def ambil_daftar_buku_kas(
    conn: sqlite3.Connection,
    sumber_filter: Optional[str] = None,
    kata_kunci: str = "",
    limit: int = 200,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Mengambil daftar transaksi buku kas urut tanggal terbaru."""
    cur = conn.cursor()
    query = "SELECT * FROM kas_transaksi WHERE 1=1"
    params: List[Any] = []

    if sumber_filter in ('simpanan', 'pencairan', 'angsuran', 'biaya_admin', 'manual'):
        query += " AND sumber = ?"
        params.append(sumber_filter)

    if kata_kunci.strip():
        k = f"%{kata_kunci.strip()}%"
        query += " AND (keterangan LIKE ? OR sumber LIKE ?)"
        params.extend([k, k])

    query += " ORDER BY tanggal DESC, id DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cur.execute(query, params)
    return [dict(r) for r in cur.fetchall()]


def balik_kas_manual(
    conn: sqlite3.Connection, kas_id: int, alasan: str, tanggal_balik: str
) -> int:
    """Melakukan transaksi pembalik untuk kas manual yang salah catat."""
    alasan_bersih = alasan.strip()
    if not alasan_bersih:
        raise ValueError("Alasan pembalik wajib diisi.")

    cur = conn.cursor()
    cur.execute("SELECT * FROM kas_transaksi WHERE id = ?;", (kas_id,))
    tx = cur.fetchone()
    if not tx:
        raise ValueError("Transaksi kas tidak ditemukan.")
    if tx["sumber"] != "manual":
        raise ValueError("Hanya transaksi kas manual yang dapat dibalik melalui menu ini.")
    if tx["terkunci"] or cek_periode_terkunci(conn, tx["periode"]):
        raise ValueError("Periode transaksi kas ini sudah terkunci.")

    periode_balik = tanggal_balik[:7]
    if cek_periode_terkunci(conn, periode_balik):
        raise ValueError(f"Periode pembalik {periode_balik} sudah terkunci.")

    # Balik posisi: jika masuk maka keluar, jika keluar maka masuk
    masuk_lawan = tx["keluar"]
    keluar_lawan = tx["masuk"]
    ket_balik = f"Pembalik kas #{kas_id}: {alasan_bersih} ({tx['keterangan']})"

    with conn:
        cur = conn.execute(
            """
            INSERT INTO kas_transaksi 
            (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
            VALUES (?, ?, ?, ?, 'manual', ?, ?);
            """,
            (tanggal_balik, ket_balik, masuk_lawan, keluar_lawan, kas_id, periode_balik)
        )
        pembalik_id = cur.lastrowid
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("balik", "kas_transaksi", pembalik_id, f"Pembalik kas manual #{kas_id}: {alasan_bersih}")
        )
        return pembalik_id

