"""
app/db/repo_anggota.py — Repositori akses data anggota.
Murni operasi database tanpa dependensi UI.
"""
import sqlite3
from typing import List, Optional, Dict, Any


def buat_nomor_anggota_berikutnya(conn: sqlite3.Connection) -> str:
    """
    Membuat nomor anggota otomatis (contoh: A-0001, A-0002, dst).
    """
    cur = conn.cursor()
    cur.execute("SELECT no_anggota FROM anggota ORDER BY id DESC LIMIT 1;")
    row = cur.fetchone()
    if not row or not row[0]:
        return "A-0001"
    
    no_terakhir = str(row[0]).strip()
    if no_terakhir.startswith("A-") and no_terakhir[2:].isdigit():
        angka = int(no_terakhir[2:]) + 1
        return f"A-{angka:04d}"
    
    # Fallback jika format nomor sebelumnya berbeda
    cur.execute("SELECT COUNT(*) FROM anggota;")
    total = cur.fetchone()[0] + 1
    return f"A-{total:04d}"


def tambah_anggota(
    conn: sqlite3.Connection,
    no_anggota: str,
    nama: str,
    nik_karyawan: Optional[str],
    unit: Optional[str],
    no_hp: Optional[str],
    alamat: Optional[str],
    tanggal_masuk: str,
    catatan: Optional[str] = None
) -> int:
    """Menambah data anggota baru."""
    nama_bersih = nama.strip()
    if not nama_bersih:
        raise ValueError("Nama anggota tidak boleh kosong.")
    if not no_anggota.strip():
        raise ValueError("Nomor anggota tidak boleh kosong.")

    with conn:
        cur = conn.execute(
            """
            INSERT INTO anggota 
            (no_anggota, nama, nik_karyawan, unit, no_hp, alamat, tanggal_masuk, status, catatan)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'aktif', ?);
            """,
            (
                no_anggota.strip(),
                nama_bersih,
                nik_karyawan.strip() if nik_karyawan else None,
                unit.strip() if unit else None,
                no_hp.strip() if no_hp else None,
                alamat.strip() if alamat else None,
                tanggal_masuk.strip(),
                catatan.strip() if catatan else None
            )
        )
        anggota_id = cur.lastrowid
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "anggota", anggota_id, f"Tambah anggota baru: {nama_bersih} ({no_anggota.strip()})")
        )
        return anggota_id


def ubah_anggota(
    conn: sqlite3.Connection,
    anggota_id: int,
    nama: str,
    nik_karyawan: Optional[str],
    unit: Optional[str],
    no_hp: Optional[str],
    alamat: Optional[str],
    catatan: Optional[str] = None
) -> None:
    """Memperbarui informasi data diri anggota."""
    nama_bersih = nama.strip()
    if not nama_bersih:
        raise ValueError("Nama anggota tidak boleh kosong.")

    with conn:
        conn.execute(
            """
            UPDATE anggota 
            SET nama = ?, nik_karyawan = ?, unit = ?, no_hp = ?, alamat = ?, catatan = ?
            WHERE id = ?;
            """,
            (
                nama_bersih,
                nik_karyawan.strip() if nik_karyawan else None,
                unit.strip() if unit else None,
                no_hp.strip() if no_hp else None,
                alamat.strip() if alamat else None,
                catatan.strip() if catatan else None,
                anggota_id
            )
        )
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("ubah", "anggota", anggota_id, f"Perbarui data anggota: {nama_bersih}")
        )


def set_status_anggota(
    conn: sqlite3.Connection,
    anggota_id: int,
    status: str,
    tanggal_keluar: Optional[str] = None
) -> None:
    """Mengubah status anggota ('aktif' atau 'keluar')."""
    if status not in ("aktif", "keluar"):
        raise ValueError("Status harus 'aktif' atau 'keluar'.")

    with conn:
        conn.execute(
            """
            UPDATE anggota
            SET status = ?, tanggal_keluar = ?
            WHERE id = ?;
            """,
            (status, tanggal_keluar if status == "keluar" else None, anggota_id)
        )
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("ubah", "anggota", anggota_id, f"Ubah status anggota menjadi {status}")
        )


def cek_anggota_punya_transaksi(conn: sqlite3.Connection, anggota_id: int) -> bool:
    """Mengecek apakah anggota sudah memiliki riwayat simpanan atau pinjaman."""
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM simpanan_transaksi WHERE anggota_id = ? LIMIT 1;", (anggota_id,))
    if cur.fetchone():
        return True
    cur.execute("SELECT 1 FROM pinjaman WHERE anggota_id = ? LIMIT 1;", (anggota_id,))
    if cur.fetchone():
        return True
    return False


def hapus_anggota_jika_tanpa_transaksi(conn: sqlite3.Connection, anggota_id: int) -> bool:
    """
    Hapus anggota hanya jika BELUM memiliki transaksi apa pun.
    Jika sudah punya transaksi, wajib ditolak (gunakan nonaktifkan/status='keluar').
    """
    if cek_anggota_punya_transaksi(conn, anggota_id):
        raise ValueError("Anggota yang sudah memiliki transaksi tidak boleh dihapus. Ubah status menjadi 'keluar'.")

    with conn:
        cur = conn.execute("SELECT nama, no_anggota FROM anggota WHERE id = ?;", (anggota_id,))
        row = cur.fetchone()
        nama = row["nama"] if row else str(anggota_id)
        no_ang = row["no_anggota"] if row else ""

        conn.execute("DELETE FROM anggota WHERE id = ?;", (anggota_id,))
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("ubah", "anggota", anggota_id, f"Hapus anggota tanpa riwayat transaksi: {nama} ({no_ang})")
        )
    return True


def ambil_anggota_by_id(conn: sqlite3.Connection, anggota_id: int) -> Optional[sqlite3.Row]:
    """Mengambil satu anggota berdasarkan id."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM anggota WHERE id = ?;", (anggota_id,))
    return cur.fetchone()


def ambil_daftar_anggota(
    conn: sqlite3.Connection,
    kata_kunci: str = "",
    status_filter: str = "semua",
    limit: int = 100,
    offset: int = 0
) -> List[sqlite3.Row]:
    """
    Mencari dan mengambil daftar anggota dengan limit & pagination.
    Mendukung filter nama, no_anggota, nik_karyawan, unit, dan status.
    """
    cur = conn.cursor()
    query = "SELECT * FROM anggota WHERE 1=1"
    params: List[Any] = []

    if kata_kunci.strip():
        k = f"%{kata_kunci.strip()}%"
        query += " AND (nama LIKE ? OR no_anggota LIKE ? OR nik_karyawan LIKE ? OR unit LIKE ?)"
        params.extend([k, k, k, k])

    if status_filter in ("aktif", "keluar"):
        query += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cur.execute(query, params)
    return cur.fetchall()

