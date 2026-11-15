"""
app/db/repo_pinjaman.py — Repositori akses data Pinjaman, Produk Pinjaman, dan Alur Pengajuan.
Murni operasi database tanpa dependensi UI. Sesuai RULES.md & DATABASE.md:
- Menghasilkan nomor pinjaman otomatis (P-0001, P-0002, dst)
- Mengajukan pinjaman (status='diajukan') untuk rapat pengurus
- Rekap daftar pengajuan pinjaman
- Menyetujui & mencairkan pinjaman (atomik: update status='aktif' + insert jadwal angsuran + kas keluar/masuk)
- Menolak pengajuan pinjaman (status='ditolak')
- Membuat pinjaman langsung cair (status='aktif')
"""
import sqlite3
from typing import List, Optional, Dict, Any
from app.logika.angsuran_flat import hitung_jadwal_angsuran_flat
from app.db.repo_simpanan import cek_periode_terkunci


def ambil_semua_produk_pinjaman(conn: sqlite3.Connection, hanya_aktif: bool = True) -> List[sqlite3.Row]:
    cur = conn.cursor()
    if hanya_aktif:
        cur.execute("SELECT * FROM produk_pinjaman WHERE aktif = 1 ORDER BY id ASC;")
    else:
        cur.execute("SELECT * FROM produk_pinjaman ORDER BY id ASC;")
    return cur.fetchall()


def ambil_produk_by_id(conn: sqlite3.Connection, produk_id: int) -> Optional[sqlite3.Row]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM produk_pinjaman WHERE id = ?;", (produk_id,))
    return cur.fetchone()


def buat_nomor_pinjaman_berikutnya(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    cur.execute("SELECT no_pinjaman FROM pinjaman ORDER BY id DESC LIMIT 1;")
    row = cur.fetchone()
    if not row or not row[0]:
        return "P-0001"
    
    no_terakhir = str(row[0]).strip()
    if no_terakhir.startswith("P-") and no_terakhir[2:].isdigit():
        angka = int(no_terakhir[2:]) + 1
        return f"P-{angka:04d}"

    cur.execute("SELECT COUNT(*) FROM pinjaman;")
    total = cur.fetchone()[0] + 1
    return f"P-{total:04d}"


def ajukan_pinjaman(
    conn: sqlite3.Connection,
    no_pinjaman: str,
    anggota_id: int,
    produk_id: Optional[int],
    plafon: int,
    tenor: int,
    jasa_persen_per_bulan: float,
    biaya_admin: int,
    tanggal_pengajuan: str,
    keperluan: Optional[str] = None
) -> int:
    """
    Menyimpan permohonan pengajuan pinjaman (status='diajukan').
    Belum mencairkan kas dan belum membuat jadwal cicilan sampai disetujui pengurus.
    """
    if not no_pinjaman.strip():
        raise ValueError("Nomor pinjaman tidak boleh kosong.")
    if plafon <= 0 or tenor <= 0:
        raise ValueError("Plafon dan tenor pinjaman harus valid.")

    periode = tanggal_pengajuan[:7]
    cur = conn.cursor()
    cur.execute("SELECT nama, status FROM anggota WHERE id = ?;", (anggota_id,))
    ang = cur.fetchone()
    if not ang or ang["status"] != "aktif":
        raise ValueError("Anggota peminjam tidak aktif atau tidak dapat meminjam.")

    with conn:
        cur = conn.execute(
            """
            INSERT INTO pinjaman 
            (no_pinjaman, anggota_id, produk_id, plafon, tenor, jasa_persen_per_bulan,
             biaya_admin, tanggal_cair, status, keperluan, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'diajukan', ?, ?);
            """,
            (
                no_pinjaman.strip(), anggota_id, produk_id, plafon, tenor,
                jasa_persen_per_bulan, biaya_admin, tanggal_pengajuan,
                keperluan.strip() if keperluan else None, periode
            )
        )
        pinj_id = cur.lastrowid
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "pinjaman", pinj_id, f"Pengajuan pinjaman baru {no_pinjaman} sebesar Rp {plafon:,} ({ang['nama']})".replace(",", "."))
        )
        return pinj_id


def setujui_dan_cairkan_pinjaman(
    conn: sqlite3.Connection,
    pinjaman_id: int,
    tanggal_cair: str
) -> None:
    """
    Menyetujui dan mencairkan pinjaman yang sebelumnya berstatus 'diajukan':
    - Update status menjadi 'aktif'
    - Hitung & simpan seluruh jadwal angsuran
    - Catat kas keluar (pencairan) & kas masuk (admin)
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.*, a.nama AS nama_anggota, a.status AS status_anggota
        FROM pinjaman p
        JOIN anggota a ON p.anggota_id = a.id
        WHERE p.id = ?;
        """,
        (pinjaman_id,)
    )
    p = cur.fetchone()
    if not p:
        raise ValueError("Data pinjaman tidak ditemukan.")
    if p["status"] != "diajukan":
        raise ValueError(f"Pinjaman tidak dapat dicairkan karena berstatus '{p['status']}'.")
    if p["status_anggota"] != "aktif":
        raise ValueError("Anggota peminjam sudah tidak aktif.")

    periode = tanggal_cair[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing).")

    jadwal = hitung_jadwal_angsuran_flat(p["plafon"], p["tenor"], p["jasa_persen_per_bulan"], tanggal_cair)

    with conn:
        # Update pinjaman
        conn.execute(
            "UPDATE pinjaman SET status = 'aktif', tanggal_cair = ?, periode = ? WHERE id = ?;",
            (tanggal_cair, periode, pinjaman_id)
        )

        # Insert jadwal angsuran
        for baris in jadwal:
            conn.execute(
                """
                INSERT INTO angsuran (pinjaman_id, angsuran_ke, jatuh_tempo, pokok, jasa)
                VALUES (?, ?, ?, ?, ?);
                """,
                (pinjaman_id, baris["angsuran_ke"], baris["jatuh_tempo"], baris["pokok"], baris["jasa"])
            )

        # Kas keluar (pencairan)
        conn.execute(
            """
            INSERT INTO kas_transaksi (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
            VALUES (?, ?, 0, ?, 'pencairan', ?, ?);
            """,
            (tanggal_cair, f"Pencairan pinjaman {p['no_pinjaman']} - {p['nama_anggota']}", p["plafon"], pinjaman_id, periode)
        )

        # Kas masuk (biaya admin)
        if p["biaya_admin"] > 0:
            conn.execute(
                """
                INSERT INTO kas_transaksi (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
                VALUES (?, ?, ?, 0, 'biaya_admin', ?, ?);
                """,
                (tanggal_cair, f"Biaya admin pinjaman {p['no_pinjaman']} - {p['nama_anggota']}", p["biaya_admin"], pinjaman_id, periode)
            )

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("ubah", "pinjaman", pinjaman_id, f"Persetujuan & pencairan pinjaman {p['no_pinjaman']} ({p['nama_anggota']})")
        )


def tolak_pengajuan_pinjaman(conn: sqlite3.Connection, pinjaman_id: int, alasan: str) -> None:
    """Menolak pengajuan pinjaman."""
    with conn:
        conn.execute(
            "UPDATE pinjaman SET status = 'ditolak', keperluan = keperluan || ? WHERE id = ? AND status = 'diajukan';",
            (f" [Ditolak: {alasan.strip()}]", pinjaman_id)
        )
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("ubah", "pinjaman", pinjaman_id, f"Penolakan pengajuan pinjaman ID #{pinjaman_id}: {alasan.strip()}")
        )


def buat_pinjaman_baru(
    conn: sqlite3.Connection,
    no_pinjaman: str,
    anggota_id: int,
    produk_id: Optional[int],
    plafon: int,
    tenor: int,
    jasa_persen_per_bulan: float,
    biaya_admin: int,
    tanggal_cair: str,
    keperluan: Optional[str] = None
) -> int:
    """Membuat pinjaman yang langsung cair seketika (status='aktif')."""
    pinj_id = ajukan_pinjaman(
        conn, no_pinjaman, anggota_id, produk_id, plafon, tenor,
        jasa_persen_per_bulan, biaya_admin, tanggal_cair, keperluan
    )
    setujui_dan_cairkan_pinjaman(conn, pinj_id, tanggal_cair)
    return pinj_id


def ambil_pinjaman_by_id(conn: sqlite3.Connection, pinjaman_id: int) -> Optional[sqlite3.Row]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.*, a.nama AS nama_anggota, a.no_anggota, a.unit, pr.nama AS nama_produk
        FROM pinjaman p
        JOIN anggota a ON p.anggota_id = a.id
        LEFT JOIN produk_pinjaman pr ON p.produk_id = pr.id
        WHERE p.id = ?;
        """,
        (pinjaman_id,)
    )
    return cur.fetchone()


def ambil_jadwal_angsuran_pinjaman(conn: sqlite3.Connection, pinjaman_id: int) -> List[sqlite3.Row]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM angsuran WHERE pinjaman_id = ? ORDER BY angsuran_ke ASC;", (pinjaman_id,))
    return cur.fetchall()


def ambil_daftar_pinjaman(
    conn: sqlite3.Connection,
    status_filter: str = "semua",
    kata_kunci: str = "",
    limit: int = 100,
    offset: int = 0
) -> List[sqlite3.Row]:
    cur = conn.cursor()
    query = """
        SELECT p.*, a.nama AS nama_anggota, a.no_anggota, a.unit, pr.nama AS nama_produk
        FROM pinjaman p
        JOIN anggota a ON p.anggota_id = a.id
        LEFT JOIN produk_pinjaman pr ON p.produk_id = pr.id
        WHERE 1=1
    """
    params: List[Any] = []

    if status_filter in ("diajukan", "aktif", "lunas", "ditolak", "batal"):
        query += " AND p.status = ?"
        params.append(status_filter)

    if kata_kunci.strip():
        k = f"%{kata_kunci.strip()}%"
        query += " AND (a.nama LIKE ? OR a.no_anggota LIKE ? OR p.no_pinjaman LIKE ? OR p.keperluan LIKE ?)"
        params.extend([k, k, k, k])

    query += " ORDER BY p.tanggal_cair DESC, p.id DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cur.execute(query, params)
    return cur.fetchall()
