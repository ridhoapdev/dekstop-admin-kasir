"""
app/db/repo_barang.py — Repositori Master Barang dan Satuan Barang (Konversi Melekat).
Mendukung:
- CRUD Master Barang (kode, nama, kategori, satuan_dasar, kata_kunci, harga_jual, jenis_kepemilikan, penitip_id, stok_minimum)
- Proteksi hapus jika sudah ada transaksi (hanya nonaktifkan)
- Satuan Barang (melekat per barang, dilarang global):
  * Penguncian 'isi_dalam_satuan_dasar' jika sudah pernah dipakai transaksi
  * Penambahan satuan baru atau pengubahan nama jika belum terkunci
- Pencarian barang toleran case-insensitive, partial matching (nama, kode, kata_kunci)
- Peringatan nama mirip (fuzzy match)
"""
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from app.util.fuzzy import cari_nama_mirip


def cek_nama_mirip_barang(
    conn: sqlite3.Connection,
    nama_baru: str,
    kecualikan_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Mencari nama barang mirip yang sudah terdaftar."""
    cur = conn.cursor()
    cur.execute("SELECT id, nama FROM barang;")
    semua_barang = [(r[0], r[1]) for r in cur.fetchall() if r[0] != kecualikan_id]
    return cari_nama_mirip(nama_baru, semua_barang)


def tambah_barang(
    conn: sqlite3.Connection,
    kode: str,
    nama: str,
    satuan_dasar: str,
    kategori: Optional[str] = None,
    kata_kunci: Optional[str] = None,
    harga_jual: int = 0,
    jenis_kepemilikan: str = "milik_koperasi",
    penitip_id: Optional[int] = None,
    stok_minimum: int = 0
) -> int:
    """Menambahkan master barang baru."""
    kode_clean = kode.strip()
    nama_clean = nama.strip()
    satuan_clean = satuan_dasar.strip().lower()

    if not kode_clean:
        raise ValueError("Kode barang tidak boleh kosong.")
    if not nama_clean:
        raise ValueError("Nama barang tidak boleh kosong.")
    if not satuan_clean:
        raise ValueError("Satuan dasar tidak boleh kosong.")
    if harga_jual < 0:
        raise ValueError("Harga jual tidak boleh negatif.")
    if jenis_kepemilikan not in ("milik_koperasi", "titipan"):
        raise ValueError("Jenis kepemilikan harus 'milik_koperasi' atau 'titipan'.")
    if jenis_kepemilikan == "titipan" and not penitip_id:
        raise ValueError("Barang titipan wajib memilih penitip.")

    with conn:
        cur = conn.execute(
            """
            INSERT INTO barang (
                kode, nama, kategori, satuan_dasar, kata_kunci,
                harga_jual, jenis_kepemilikan, penitip_id, stok_minimum,
                stok_saat_ini, aktif
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1);
            """,
            (
                kode_clean, nama_clean,
                kategori.strip() if kategori else None,
                satuan_clean,
                kata_kunci.strip() if kata_kunci else None,
                int(harga_jual),
                jenis_kepemilikan,
                penitip_id if jenis_kepemilikan == "titipan" else None,
                int(stok_minimum)
            )
        )
        barang_id = cur.lastrowid

        # Daftarkan satuan dasar ke satuan_barang (isi = 1)
        conn.execute(
            """
            INSERT OR IGNORE INTO satuan_barang (barang_id, nama_satuan, isi_dalam_satuan_dasar, terkunci)
            VALUES (?, ?, 1, 0);
            """,
            (barang_id, satuan_clean)
        )

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "barang", barang_id, f"Tambah barang {kode_clean} - {nama_clean}")
        )
        return barang_id


def ubah_barang(
    conn: sqlite3.Connection,
    barang_id: int,
    kode: str,
    nama: str,
    satuan_dasar: str,
    kategori: Optional[str] = None,
    kata_kunci: Optional[str] = None,
    harga_jual: int = 0,
    jenis_kepemilikan: str = "milik_koperasi",
    penitip_id: Optional[int] = None,
    stok_minimum: int = 0,
    aktif: int = 1
) -> None:
    """Mengubah data master barang."""
    kode_clean = kode.strip()
    nama_clean = nama.strip()
    satuan_clean = satuan_dasar.strip().lower()

    if not kode_clean or not nama_clean or not satuan_clean:
        raise ValueError("Kode, nama, dan satuan dasar wajib diisi.")
    if harga_jual < 0:
        raise ValueError("Harga jual tidak boleh negatif.")

    # Cek apakah satuan dasar diubah dan barang sudah punya transaksi mutasi
    cur = conn.cursor()
    cur.execute("SELECT satuan_dasar FROM barang WHERE id = ?;", (barang_id,))
    row_b = cur.fetchone()
    if row_b and row_b[0] != satuan_clean:
        cur.execute("SELECT COUNT(*) FROM mutasi_stok WHERE barang_id = ?;", (barang_id,))
        if cur.fetchone()[0] > 0:
            raise ValueError(
                f"Satuan dasar barang '{row_b[0]}' tidak dapat diubah karena barang sudah memiliki transaksi mutasi stok."
            )

    with conn:
        conn.execute(
            """
            UPDATE barang
            SET kode = ?, nama = ?, kategori = ?, satuan_dasar = ?, kata_kunci = ?,
                harga_jual = ?, jenis_kepemilikan = ?, penitip_id = ?,
                stok_minimum = ?, aktif = ?
            WHERE id = ?;
            """,
            (
                kode_clean, nama_clean,
                kategori.strip() if kategori else None,
                satuan_clean,
                kata_kunci.strip() if kata_kunci else None,
                int(harga_jual),
                jenis_kepemilikan,
                penitip_id if jenis_kepemilikan == "titipan" else None,
                int(stok_minimum),
                aktif,
                barang_id
            )
        )
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("ubah", "barang", barang_id, f"Ubah barang {kode_clean} - {nama_clean}")
        )


def ambil_barang_by_id(conn: sqlite3.Connection, barang_id: int) -> Optional[Dict[str, Any]]:
    """Mengambil satu barang berdasarkan ID beserta detail penitip."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT b.*, p.nama AS nama_penitip
        FROM barang b
        LEFT JOIN penitip p ON b.penitip_id = p.id
        WHERE b.id = ?;
        """,
        (barang_id,)
    )
    row = cur.fetchone()
    return dict(row) if row else None


def cari_barang(
    conn: sqlite3.Connection,
    kata_kunci: str,
    hanya_aktif: bool = True,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Pencarian barang: tidak peka huruf besar-kecil, mencocokkan kode, nama, dan kata_kunci.
    Contoh: 'pucuk' menemukan 'Teh Pucuk Harum 350ml'.
    """
    k = kata_kunci.strip()
    cur = conn.cursor()
    query = """
        SELECT b.*, p.nama AS nama_penitip
        FROM barang b
        LEFT JOIN penitip p ON b.penitip_id = p.id
        WHERE 1=1
    """
    params: List[Any] = []
    if hanya_aktif:
        query += " AND b.aktif = 1"

    if k:
        tokens = [t.strip() for t in k.split() if t.strip()]
        for tok in tokens:
            like_tok = f"%{tok}%"
            query += " AND (b.nama LIKE ? OR b.kode LIKE ? OR COALESCE(b.kata_kunci, '') LIKE ?)"
            params.extend([like_tok, like_tok, like_tok])

    query += " ORDER BY b.nama COLLATE NOCASE ASC LIMIT ?;"
    params.append(limit)

    cur.execute(query, params)
    return [dict(r) for r in cur.fetchall()]


def ambil_daftar_barang(
    conn: sqlite3.Connection,
    hanya_aktif: bool = True
) -> List[Dict[str, Any]]:
    """Mengambil seluruh daftar barang (misal untuk inisialisasi stock opname)."""
    cur = conn.cursor()
    query = """
        SELECT b.*, p.nama AS nama_penitip
        FROM barang b
        LEFT JOIN penitip p ON b.penitip_id = p.id
    """
    if hanya_aktif:
        query += " WHERE b.aktif = 1"
    query += " ORDER BY b.nama COLLATE NOCASE ASC;"
    cur.execute(query)
    return [dict(r) for r in cur.fetchall()]


def nonaktifkan_barang(conn: sqlite3.Connection, barang_id: int) -> None:
    """
    Menonaktifkan barang. Jika ada transaksi mutasi, barang TIDAK boleh dihapus permanen,
    hanya dinonaktifkan (aktif = 0). Jika belum ada transaksi, boleh dihapus.
    """
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM mutasi_stok WHERE barang_id = ?;", (barang_id,))
    ada_transaksi = cur.fetchone()[0] > 0

    with conn:
        if ada_transaksi:
            conn.execute("UPDATE barang SET aktif = 0 WHERE id = ?;", (barang_id,))
            conn.execute(
                "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
                ("ubah", "barang", barang_id, f"Nonaktifkan barang ID {barang_id} (memiliki transaksi)")
            )
        else:
            conn.execute("DELETE FROM satuan_barang WHERE barang_id = ?;", (barang_id,))
            conn.execute("DELETE FROM barang WHERE id = ?;", (barang_id,))
            conn.execute(
                "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
                ("hapus", "barang", barang_id, f"Hapus permanen barang ID {barang_id} (belum ada transaksi)")
            )


# -------------------------------------------------------------
# PENGELOLAAN SATUAN BARANG (KONVERSI MELEKAT PER BARANG)
# -------------------------------------------------------------

def ambil_satuan_barang(conn: sqlite3.Connection, barang_id: int) -> List[Dict[str, Any]]:
    """Mengambil seluruh satuan yang terdaftar untuk suatu barang."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, barang_id, nama_satuan, isi_dalam_satuan_dasar, terkunci, dibuat_pada
        FROM satuan_barang
        WHERE barang_id = ?
        ORDER BY isi_dalam_satuan_dasar ASC, nama_satuan ASC;
        """,
        (barang_id,)
    )
    return [dict(r) for r in cur.fetchall()]


def tambah_satuan_barang(
    conn: sqlite3.Connection,
    barang_id: int,
    nama_satuan: str,
    isi_dalam_satuan_dasar: int
) -> int:
    """Menambahkan satuan baru untuk barang tertentu."""
    nama_clean = nama_satuan.strip().lower()
    if not nama_clean:
        raise ValueError("Nama satuan tidak boleh kosong.")
    if isi_dalam_satuan_dasar <= 0:
        raise ValueError("Isi satuan dalam satuan dasar harus bilangan bulat positif (> 0).")

    with conn:
        cur = conn.execute(
            """
            INSERT INTO satuan_barang (barang_id, nama_satuan, isi_dalam_satuan_dasar, terkunci)
            VALUES (?, ?, ?, 0);
            """,
            (barang_id, nama_clean, isi_dalam_satuan_dasar)
        )
        satuan_id = cur.lastrowid
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "satuan_barang", satuan_id, f"Tambah satuan {nama_clean}={isi_dalam_satuan_dasar} pada barang ID {barang_id}")
        )
        return satuan_id


def ubah_satuan_barang(
    conn: sqlite3.Connection,
    satuan_id: int,
    nama_satuan: str,
    isi_dalam_satuan_dasar: int
) -> None:
    """
    Mengubah satuan barang.
    Jika satuan sudah TERKUNCI (sudah dipakai di transaksi pembelian/mutasi):
    Isi dalam satuan dasar DIKUNCI dan TIDAK BOLEH diubah.
    Pengguna diarahkan membuat entri satuan baru.
    """
    nama_clean = nama_satuan.strip().lower()
    if not nama_clean:
        raise ValueError("Nama satuan tidak boleh kosong.")
    if isi_dalam_satuan_dasar <= 0:
        raise ValueError("Isi satuan dalam satuan dasar harus bilangan bulat positif (> 0).")

    cur = conn.cursor()
    cur.execute(
        "SELECT barang_id, nama_satuan, isi_dalam_satuan_dasar, terkunci FROM satuan_barang WHERE id = ?;",
        (satuan_id,)
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Satuan barang tidak ditemukan.")

    barang_id, lama_nama, lama_isi, terkunci = row[0], row[1], row[2], row[3]

    if terkunci and isi_dalam_satuan_dasar != lama_isi:
        raise ValueError(
            f"Konversi satuan '{lama_nama}' ({lama_isi} satuan dasar) sudah terkunci karena telah dipakai dalam transaksi. "
            "Untuk konversi baru, buatlah entri satuan baru (misal: dus-baru atau renteng-isi12)."
        )

    with conn:
        conn.execute(
            """
            UPDATE satuan_barang
            SET nama_satuan = ?, isi_dalam_satuan_dasar = ?
            WHERE id = ?;
            """,
            (nama_clean, isi_dalam_satuan_dasar, satuan_id)
        )
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("ubah", "satuan_barang", satuan_id, f"Ubah satuan ID {satuan_id} pada barang ID {barang_id} menjadi {nama_clean}={isi_dalam_satuan_dasar}")
        )


def kunci_satuan_barang_jika_dipakai(conn: sqlite3.Connection, barang_id: int, nama_satuan: str) -> None:
    """Mengunci satuan barang agar isi_dalam_satuan_dasar tidak bisa diubah lagi."""
    with conn:
        conn.execute(
            "UPDATE satuan_barang SET terkunci = 1 WHERE barang_id = ? AND LOWER(nama_satuan) = LOWER(?);",
            (barang_id, nama_satuan.strip())
        )
