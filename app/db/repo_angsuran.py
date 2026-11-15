"""
app/db/repo_angsuran.py — Repositori akses data Pembayaran Angsuran dan kalkulasi status cicilan.
Murni operasi database tanpa dependensi UI. Sesuai RULES.md & DATABASE.md:
- Menghitung status angsuran per baris: 'belum', 'sebagian', 'lunas', 'telat'
- Menghitung sisa pokok pinjaman = plafon - SUM(bayar_pokok)
- Menangani pembayaran angsuran normal (termasuk bayar sebagian)
- Menangani pelunasan dipercepat: sisa pokok + jasa berjalan (angsuran_id NULL)
- Menulis ke kas_transaksi secara atomik (sumber='angsuran')
- Transaksi pembalik pembayaran angsuran untuk koreksi kesalahan
- Memperbarui status pinjaman menjadi 'lunas' jika seluruh pokok telah terbayar
"""
import sqlite3
from datetime import datetime, date
from typing import List, Dict, Optional, Any
from app.db.repo_simpanan import cek_periode_terkunci
from app.util.format import format_rupiah


def hitung_status_angsuran(
    tagihan_pokok: int,
    tagihan_jasa: int,
    total_bayar_pokok: int,
    total_bayar_jasa: int,
    jatuh_tempo_iso: str,
    tanggal_patokan_iso: Optional[str] = None
) -> str:
    """
    Menghitung status cicilan:
    - 'lunas': bayar_pokok >= tagihan_pokok AND bayar_jasa >= tagihan_jasa
    - 'sebagian': ada pembayaran (pokok > 0 atau jasa > 0), tapi belum lunas
    - 'telat': belum lunas dan tanggal patokan > jatuh tempo
    - 'belum': belum ada pembayaran dan belum lewat jatuh tempo
    """
    lunas = (total_bayar_pokok >= tagihan_pokok) and (total_bayar_jasa >= tagihan_jasa)
    if lunas:
        return "lunas"

    ada_bayar = (total_bayar_pokok > 0) or (total_bayar_jasa > 0)
    
    tgl_cek = tanggal_patokan_iso or date.today().strftime("%Y-%m-%d")
    lewat_tempo = tgl_cek > jatuh_tempo_iso

    if lewat_tempo:
        return "telat"
    if ada_bayar:
        return "sebagian"
    return "belum"


def hitung_sisa_pokok_pinjaman(conn: sqlite3.Connection, pinjaman_id: int) -> int:
    """
    Menghitung sisa pokok pinjaman = plafon - SUM(bayar_pokok)
    Memperhitungkan transaksi pembalik (transaksi yang dibalik diabaikan).
    """
    cur = conn.cursor()
    cur.execute("SELECT plafon FROM pinjaman WHERE id = ?;", (pinjaman_id,))
    row = cur.fetchone()
    if not row:
        return 0
    plafon = row["plafon"]

    cur.execute(
        """
        SELECT COALESCE(SUM(bayar_pokok), 0)
        FROM v_pembayaran_angsuran_efektif
        WHERE pinjaman_id = ? AND status_efektif = 'NORMAL';
        """,
        (pinjaman_id,)
    )
    total_bayar = cur.fetchone()[0]
    sisa = plafon - total_bayar
    return max(0, sisa)


def ambil_daftar_angsuran_dengan_status(
    conn: sqlite3.Connection, pinjaman_id: int, tanggal_patokan: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Mengambil seluruh cicilan pinjaman beserta akumulasi pembayaran dan status saat ini.
    Hanya memperhitungkan pembayaran efektif yang berstatus 'NORMAL'.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT a.id, a.pinjaman_id, a.angsuran_ke, a.jatuh_tempo, a.pokok, a.jasa,
               COALESCE(SUM(p.bayar_pokok), 0) AS terbayar_pokok,
               COALESCE(SUM(p.bayar_jasa), 0) AS terbayar_jasa,
               COALESCE(SUM(p.denda), 0) AS terbayar_denda
        FROM angsuran a
        LEFT JOIN v_pembayaran_angsuran_efektif p ON a.id = p.angsuran_id AND p.status_efektif = 'NORMAL'
        WHERE a.pinjaman_id = ?
        GROUP BY a.id
        ORDER BY a.angsuran_ke ASC;
        """,
        (pinjaman_id,)
    )
    daftar = []
    for r in cur.fetchall():
        status = hitung_status_angsuran(
            tagihan_pokok=r["pokok"],
            tagihan_jasa=r["jasa"],
            total_bayar_pokok=r["terbayar_pokok"],
            total_bayar_jasa=r["terbayar_jasa"],
            jatuh_tempo_iso=r["jatuh_tempo"],
            tanggal_patokan_iso=tanggal_patokan
        )
        sisa_pokok_cicilan = max(0, r["pokok"] - r["terbayar_pokok"])
        sisa_jasa_cicilan = max(0, r["jasa"] - r["terbayar_jasa"])

        daftar.append({
            "id": r["id"],
            "pinjaman_id": r["pinjaman_id"],
            "angsuran_ke": r["angsuran_ke"],
            "jatuh_tempo": r["jatuh_tempo"],
            "tagihan_pokok": r["pokok"],
            "tagihan_jasa": r["jasa"],
            "terbayar_pokok": r["terbayar_pokok"],
            "terbayar_jasa": r["terbayar_jasa"],
            "terbayar_denda": r["terbayar_denda"],
            "sisa_pokok": sisa_pokok_cicilan,
            "sisa_jasa": sisa_jasa_cicilan,
            "total_sisa_tagihan": sisa_pokok_cicilan + sisa_jasa_cicilan,
            "status": status
        })
    return daftar


def ambil_angsuran_berikutnya_yang_harus_dibayar(
    conn: sqlite3.Connection, pinjaman_id: int
) -> Optional[Dict[str, Any]]:
    """Mencari angsuran terawal yang statusnya belum lunas."""
    semua = ambil_daftar_angsuran_dengan_status(conn, pinjaman_id)
    for c in semua:
        if c["status"] != "lunas":
            return c
    return None


def bayar_angsuran(
    conn: sqlite3.Connection,
    pinjaman_id: int,
    angsuran_id: Optional[int],
    tanggal: str,
    bayar_pokok: int,
    bayar_jasa: int,
    denda: int = 0,
    keterangan: Optional[str] = None
) -> int:
    """
    Menyimpan pembayaran angsuran.
    Mendukung pembayaran cicilan tertentu (angsuran_id ditentukan)
    maupun pelunasan dipercepat (angsuran_id = None).
    """
    if bayar_pokok < 0 or bayar_jasa < 0 or denda < 0:
        raise ValueError("Nominal pembayaran tidak boleh bernilai negatif.")
    
    total_bayar = bayar_pokok + bayar_jasa + denda
    if total_bayar <= 0:
        raise ValueError("Total pembayaran harus lebih dari Rp 0.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Pembayaran tidak dapat disimpan.")

    cur = conn.cursor()
    # Cek pinjaman
    cur.execute(
        """
        SELECT p.*, a.nama AS nama_anggota 
        FROM pinjaman p 
        JOIN anggota a ON p.anggota_id = a.id 
        WHERE p.id = ?;
        """,
        (pinjaman_id,)
    )
    pinj = cur.fetchone()
    if not pinj:
        raise ValueError("Pinjaman tidak ditemukan.")

    if pinj["status"] == "lunas":
        raise ValueError("Pinjaman ini sudah lunas.")
    if pinj["status"] == "batal":
        raise ValueError("Pinjaman ini berstatus batal.")

    # Cek sisa pokok keseluruhan
    sisa_pokok_saat_ini = hitung_sisa_pokok_pinjaman(conn, pinjaman_id)
    if bayar_pokok > sisa_pokok_saat_ini:
        raise ValueError(
            f"Pembayaran pokok ({format_rupiah(bayar_pokok)}) melebihi sisa pokok pinjaman ({format_rupiah(sisa_pokok_saat_ini)})."
        )

    ket_bersih = keterangan.strip() if keterangan else ""

    with conn:
        # 1. Simpan ke tabel pembayaran_angsuran
        cur = conn.execute(
            """
            INSERT INTO pembayaran_angsuran 
            (pinjaman_id, angsuran_id, tanggal, bayar_pokok, bayar_jasa, denda, keterangan, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (pinjaman_id, angsuran_id, tanggal, bayar_pokok, bayar_jasa, denda, ket_bersih or None, periode)
        )
        bayar_id = cur.lastrowid

        # 2. Catat kas masuk otomatis
        ket_kas = f"Angsuran pinjaman {pinj['no_pinjaman']} ({pinj['nama_anggota']})"
        if ket_bersih:
            ket_kas += f" - {ket_bersih}"
        
        conn.execute(
            """
            INSERT INTO kas_transaksi 
            (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
            VALUES (?, ?, ?, 0, 'angsuran', ?, ?);
            """,
            (tanggal, ket_kas, total_bayar, bayar_id, periode)
        )

        # 3. Cek apakah pinjaman kini sudah lunas
        sisa_pokok_baru = sisa_pokok_saat_ini - bayar_pokok
        if sisa_pokok_baru == 0:
            conn.execute(
                "UPDATE pinjaman SET status = 'lunas', tanggal_lunas = ? WHERE id = ?;",
                (tanggal, pinjaman_id)
            )

        # 4. Catat log aktivitas
        detail_log = (
            f"Bayar angsuran pinjaman {pinj['no_pinjaman']} ({pinj['nama_anggota']}): "
            f"Pokok {format_rupiah(bayar_pokok)}, Jasa {format_rupiah(bayar_jasa)}"
        )
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "pembayaran_angsuran", bayar_id, detail_log)
        )

    return bayar_id


def balik_pembayaran_angsuran(
    conn: sqlite3.Connection,
    pembayaran_id: int,
    alasan: str,
    tanggal_balik: str
) -> int:
    """
    Melakukan transaksi pembalik pembayaran angsuran (koreksi kesalahan).
    Tidak ada DELETE/UPDATE pada transaksi keuangan.
    """
    alasan_bersih = alasan.strip()
    if not alasan_bersih:
        raise ValueError("Alasan koreksi pembalik pembayaran wajib diisi.")

    cur = conn.cursor()
    cur.execute("SELECT * FROM pembayaran_angsuran WHERE id = ?;", (pembayaran_id,))
    tx = cur.fetchone()
    if not tx:
        raise ValueError("Transaksi pembayaran tidak ditemukan.")

    if tx["membalik_id"] is not None:
        raise ValueError("Transaksi ini merupakan transaksi pembalik dan tidak dapat dibalik lagi.")

    cur.execute("SELECT 1 FROM pembayaran_angsuran WHERE membalik_id = ? LIMIT 1;", (pembayaran_id,))
    if cur.fetchone():
        raise ValueError("Transaksi pembayaran ini sudah pernah dibalik.")

    periode_balik = tanggal_balik[:7]
    if cek_periode_terkunci(conn, periode_balik):
        raise ValueError(f"Periode pembalik {periode_balik} sudah ditutup (closing).")

    pinjaman_id = tx["pinjaman_id"]
    bayar_pokok_lawan = 0
    bayar_jasa_lawan = 0
    denda_lawan = 0
    total_kembali = tx["bayar_pokok"] + tx["bayar_jasa"] + tx["denda"]

    cur.execute(
        """
        SELECT p.no_pinjaman, a.nama AS nama_anggota
        FROM pinjaman p
        JOIN anggota a ON p.anggota_id = a.id
        WHERE p.id = ?;
        """,
        (pinjaman_id,)
    )
    pinj = cur.fetchone()

    with conn:
        # 1. Simpan transaksi pembalik
        ket_balik = f"Koreksi pembalik bayar #{pembayaran_id}: {alasan_bersih}"
        cur = conn.execute(
            """
            INSERT INTO pembayaran_angsuran 
            (pinjaman_id, angsuran_id, tanggal, bayar_pokok, bayar_jasa, denda, keterangan, membalik_id, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                pinjaman_id,
                tx["angsuran_id"],
                tanggal_balik,
                bayar_pokok_lawan,
                bayar_jasa_lawan,
                denda_lawan,
                ket_balik,
                pembayaran_id,
                periode_balik
            )
        )
        pembalik_id = cur.lastrowid

        # 2. Catat kas keluar karena uang dikembalikan/dibatalkan
        ket_kas = f"Pembalik bayar angsuran #{pembayaran_id} ({pinj['nama_anggota']}) - {alasan_bersih}"
        conn.execute(
            """
            INSERT INTO kas_transaksi 
            (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
            VALUES (?, ?, 0, ?, 'angsuran', ?, ?);
            """,
            (tanggal_balik, ket_kas, total_kembali, pembalik_id, periode_balik)
        )

        # 3. Pastikan status pinjaman kembali aktif jika sebelumnya lunas
        conn.execute(
            "UPDATE pinjaman SET status = 'aktif', tanggal_lunas = NULL WHERE id = ?;",
            (pinjaman_id,)
        )

        # 4. Log aktivitas
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("balik", "pembayaran_angsuran", pembalik_id, f"Pembalik pembayaran #{pembayaran_id}: {alasan_bersih}")
        )

    return pembalik_id


def ambil_riwayat_pembayaran_angsuran(
    conn: sqlite3.Connection,
    pinjaman_id: Optional[int] = None,
    kata_kunci: str = "",
    limit: int = 100,
    offset: int = 0
) -> List[sqlite3.Row]:
    """Mengambil riwayat pembayaran angsuran beserta informasi anggota dan pinjaman."""
    cur = conn.cursor()
    query = """
        SELECT pa.*, p.no_pinjaman, a.nama AS nama_anggota, a.no_anggota, a.unit, ang.angsuran_ke
        FROM pembayaran_angsuran pa
        JOIN pinjaman p ON pa.pinjaman_id = p.id
        JOIN anggota a ON p.anggota_id = a.id
        LEFT JOIN angsuran ang ON pa.angsuran_id = ang.id
        WHERE 1=1
    """
    params: List[Any] = []

    if pinjaman_id:
        query += " AND pa.pinjaman_id = ?"
        params.append(pinjaman_id)

    if kata_kunci.strip():
        k = f"%{kata_kunci.strip()}%"
        query += " AND (a.nama LIKE ? OR a.no_anggota LIKE ? OR p.no_pinjaman LIKE ? OR pa.keterangan LIKE ?)"
        params.extend([k, k, k, k])

    query += " ORDER BY pa.tanggal DESC, pa.id DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cur.execute(query, params)
    return cur.fetchall()

