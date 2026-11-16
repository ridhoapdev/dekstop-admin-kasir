"""
app/db/repo_pihak.py — Repositori Master Data Pihak Terkait Toko (Supplier, Penitip, Pembeli).
Mendukung:
- CRUD pihak (tambah, perbarui, nonaktifkan)
- Peringatan nama mirip (fuzzy matching)
- Pengambilan daftar aktif/semua
"""
import sqlite3
from typing import List, Dict, Any, Optional
from app.util.fuzzy import cari_nama_mirip

TABEL_PIHAK = {
    "supplier": "supplier",
    "penitip": "penitip",
    "pembeli": "pembeli"
}


def ambil_daftar_pihak(
    conn: sqlite3.Connection,
    jenis_pihak: str,
    hanya_aktif: bool = True
) -> List[Dict[str, Any]]:
    """Mengambil daftar pihak (supplier/penitip/pembeli)."""
    tabel = TABEL_PIHAK.get(jenis_pihak)
    if not tabel:
        raise ValueError(f"Jenis pihak '{jenis_pihak}' tidak valid.")

    cur = conn.cursor()
    if jenis_pihak == "pembeli":
        query = """
            SELECT p.id, p.nama, p.no_hp, p.alamat, p.catatan, p.anggota_id, p.aktif, p.dibuat_pada,
                   a.no_anggota, a.nama AS nama_anggota
            FROM pembeli p
            LEFT JOIN anggota a ON p.anggota_id = a.id
        """
        if hanya_aktif:
            query += " WHERE p.aktif = 1"
        query += " ORDER BY p.nama COLLATE NOCASE ASC;"
    else:
        query = f"SELECT id, nama, no_hp, alamat, catatan, aktif, dibuat_pada FROM {tabel}"
        if hanya_aktif:
            query += " WHERE aktif = 1"
        query += " ORDER BY nama COLLATE NOCASE ASC;"

    cur.execute(query)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def cek_nama_mirip_pihak(
    conn: sqlite3.Connection,
    jenis_pihak: str,
    nama_baru: str,
    kecualikan_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Memeriksa nama mirip pihak yang sudah terdaftar."""
    tabel = TABEL_PIHAK.get(jenis_pihak)
    if not tabel:
        raise ValueError(f"Jenis pihak '{jenis_pihak}' tidak valid.")

    cur = conn.cursor()
    cur.execute(f"SELECT id, nama FROM {tabel};")
    semua_pihak = [(r[0], r[1]) for r in cur.fetchall() if r[0] != kecualikan_id]
    return cari_nama_mirip(nama_baru, semua_pihak)


def ambil_atau_buat_pembeli_umum(conn: sqlite3.Connection) -> int:
    """Mengambil ID pembeli default 'Umum' atau membuatnya jika belum ada."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM pembeli WHERE nama = 'Umum';")
    row = cur.fetchone()
    if row:
        return row[0]
    with conn:
        cur_ins = conn.execute(
            "INSERT INTO pembeli (nama, no_hp, alamat, catatan, aktif) VALUES ('Umum', NULL, NULL, 'Pelanggan Tunai Toko', 1);"
        )
        return cur_ins.lastrowid


def tambah_pihak(
    conn: sqlite3.Connection,
    jenis_pihak: str,
    nama: str,
    no_hp: Optional[str] = None,
    alamat: Optional[str] = None,
    catatan: Optional[str] = None,
    anggota_id: Optional[int] = None
) -> int:
    """Menambahkan entitas pihak baru."""
    tabel = TABEL_PIHAK.get(jenis_pihak)
    if not tabel:
        raise ValueError(f"Jenis pihak '{jenis_pihak}' tidak valid.")

    nama_bersih = nama.strip()
    if not nama_bersih:
        raise ValueError(f"Nama {jenis_pihak} tidak boleh kosong.")

    with conn:
        if jenis_pihak == "pembeli":
            cur = conn.execute(
                f"INSERT INTO {tabel} (nama, no_hp, alamat, catatan, anggota_id, aktif) VALUES (?, ?, ?, ?, ?, 1);",
                (nama_bersih, no_hp.strip() if no_hp else None, alamat.strip() if alamat else None, catatan.strip() if catatan else None, anggota_id)
            )
        else:
            cur = conn.execute(
                f"INSERT INTO {tabel} (nama, no_hp, alamat, catatan, aktif) VALUES (?, ?, ?, ?, 1);",
                (nama_bersih, no_hp.strip() if no_hp else None, alamat.strip() if alamat else None, catatan.strip() if catatan else None)
            )
        pihak_id = cur.lastrowid
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", tabel, pihak_id, f"Tambah {jenis_pihak}: {nama_bersih}")
        )
        return pihak_id


def ubah_pihak(
    conn: sqlite3.Connection,
    jenis_pihak: str,
    pihak_id: int,
    nama: str,
    no_hp: Optional[str] = None,
    alamat: Optional[str] = None,
    catatan: Optional[str] = None,
    anggota_id: Optional[int] = None,
    aktif: int = 1
) -> None:
    """Mengubah data pihak terkait."""
    tabel = TABEL_PIHAK.get(jenis_pihak)
    if not tabel:
        raise ValueError(f"Jenis pihak '{jenis_pihak}' tidak valid.")

    nama_bersih = nama.strip()
    if not nama_bersih:
        raise ValueError(f"Nama {jenis_pihak} tidak boleh kosong.")

    with conn:
        if jenis_pihak == "pembeli":
            conn.execute(
                f"""
                UPDATE {tabel}
                SET nama = ?, no_hp = ?, alamat = ?, catatan = ?, anggota_id = ?, aktif = ?
                WHERE id = ?;
                """,
                (nama_bersih, no_hp.strip() if no_hp else None, alamat.strip() if alamat else None, catatan.strip() if catatan else None, anggota_id, aktif, pihak_id)
            )
        else:
            conn.execute(
                f"""
                UPDATE {tabel}
                SET nama = ?, no_hp = ?, alamat = ?, catatan = ?, aktif = ?
                WHERE id = ?;
                """,
                (nama_bersih, no_hp.strip() if no_hp else None, alamat.strip() if alamat else None, catatan.strip() if catatan else None, aktif, pihak_id)
            )
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("ubah", tabel, pihak_id, f"Ubah {jenis_pihak}: {nama_bersih}")
        )
