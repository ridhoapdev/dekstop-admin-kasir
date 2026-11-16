"""
app/db/repo_kas_toko.py — Repositori Buku Kas Toko (TERPISAH dari Kas Simpan Pinjam).
Mendukung:
- Pencatatan kas masuk / keluar operasional toko (sumber='modal_awal', 'pembelian', 'bayar_hutang', 'penjualan', 'manual')
- Transaksi pembalik kas toko (koreksi tanpa delete)
- Pengecekan saldo kas toko dan mutasi kas toko
- Menggunakan view v_kas_toko_efektif untuk transaksi bersih
"""
import sqlite3
from typing import List, Dict, Any, Optional
from app.db.repo_simpanan import cek_periode_terkunci
from app.layanan.bus_sinyal import kirim_sinyal


def tambah_kas_toko(
    conn: sqlite3.Connection,
    tanggal: str,
    keterangan: str,
    masuk: int,
    keluar: int,
    sumber: str,
    ref_tabel: Optional[str] = None,
    ref_id: Optional[int] = None
) -> int:
    """Mencatat transaksi ke buku kas toko."""
    if masuk < 0 or keluar < 0:
        raise ValueError("Nominal kas toko tidak boleh negatif.")
    if (masuk > 0 and keluar > 0) or (masuk == 0 and keluar == 0):
        raise ValueError("Kas toko harus salah satu: masuk > 0 ATAU keluar > 0.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Transaksi kas toko tidak dapat disimpan.")

    cur = conn.execute(
        """
        INSERT INTO kas_toko_transaksi (
            tanggal, keterangan, masuk, keluar, sumber,
            ref_tabel, ref_id, periode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (tanggal, keterangan.strip(), masuk, keluar, sumber, ref_tabel, ref_id, periode)
    )
    kas_id = cur.lastrowid
    conn.execute(
        "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
        ("tambah", "kas_toko_transaksi", kas_id, f"Kas toko {sumber}: Masuk {masuk:,} Keluar {keluar:,} - {keterangan}".replace(",", "."))
    )
    kirim_sinyal("kas_toko_berubah")
    return kas_id


def balik_kas_toko(
    conn: sqlite3.Connection,
    kas_id: int,
    tanggal_balik: str,
    keterangan: str = "Koreksi kas toko"
) -> int:
    """Membuat transaksi pembalik kas toko."""
    periode_balik = tanggal_balik[:7]
    if cek_periode_terkunci(conn, periode_balik):
        raise ValueError(f"Periode {periode_balik} sudah ditutup (closing). Pembalikan kas toko tidak dapat disimpan.")

    cur = conn.cursor()
    cur.execute("SELECT * FROM kas_toko_transaksi WHERE id = ?;", (kas_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError("Transaksi kas toko tidak ditemukan.")

    tx = dict(row)
    if tx["membalik_id"] is not None:
        raise ValueError("Transaksi ini adalah transaksi pembalik dan tidak dapat dibalik lagi.")

    cur.execute("SELECT id FROM kas_toko_transaksi WHERE membalik_id = ?;", (kas_id,))
    if cur.fetchone():
        raise ValueError("Transaksi kas toko ini sudah pernah dibatalkan sebelumnya.")

    # Balikkan nilai masuk dan keluar
    baru_masuk = tx["keluar"]
    baru_keluar = tx["masuk"]

    cur_p = conn.execute(
        """
        INSERT INTO kas_toko_transaksi (
            tanggal, keterangan, masuk, keluar, sumber,
            ref_tabel, ref_id, membalik_id, periode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            tanggal_balik, f"[PEMBALIK #{kas_id}] {keterangan.strip()}",
            baru_masuk, baru_keluar, tx["sumber"],
            tx["ref_tabel"], tx["ref_id"], kas_id, periode_balik
        )
    )
    pembalik_id = cur_p.lastrowid
    conn.execute(
        "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
        ("balik", "kas_toko_transaksi", pembalik_id, f"Balik kas toko #{kas_id}")
    )
    kirim_sinyal("kas_toko_berubah")
    return pembalik_id


def hitung_saldo_kas_toko(conn: sqlite3.Connection) -> int:
    """Menghitung saldo kas toko terkini (SUM masuk - keluar)."""
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(masuk - keluar), 0) FROM kas_toko_transaksi;")
    return cur.fetchone()[0]


def ambil_daftar_kas_toko(
    conn: sqlite3.Connection,
    periode: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Mengambil riwayat transaksi kas toko beserta saldo berjalan."""
    cur = conn.cursor()
    query = "SELECT * FROM kas_toko_transaksi WHERE 1=1"
    params: List[Any] = []
    if periode:
        query += " AND periode = ?"
        params.append(periode)
    query += " ORDER BY tanggal ASC, id ASC;"

    cur.execute(query, params)
    rows = cur.fetchall()

    hasil = []
    saldo_berjalan = 0
    for r in rows:
        d = dict(r)
        saldo_berjalan += (d["masuk"] - d["keluar"])
        d["saldo_berjalan"] = saldo_berjalan
        hasil.append(d)

    # Urut terbalik untuk tampilan UI
    hasil.sort(key=lambda x: (x["tanggal"], x["id"]), reverse=True)
    return hasil[:limit]
