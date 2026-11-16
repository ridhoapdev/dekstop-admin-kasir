"""
app/db/repo_simpanan.py — Repositori akses data transaksi simpanan dan buku kas terkait.
Murni operasi database tanpa dependensi UI. Sesuai RULES.md & DATABASE.md:
- Uang disimpan sebagai INTEGER rupiah penuh
- Saldo dihitung dinamis dengan SUM(setor) - SUM(tarik)
- Koreksi melalui transaksi pembalik (membalik_id)
- Otomatis mencatat kas_transaksi saat setor (kas masuk) atau tarik (kas keluar)
- Mengecek periode terkunci sebelum transaksi baru/pembalik
"""
import sqlite3
from typing import Dict, List, Optional, Any
from app.util.format import format_rupiah


def cek_periode_terkunci(conn: sqlite3.Connection, periode: str) -> bool:
    """Mengecek apakah periode 'YYYY-MM' sudah di-closing di simpan pinjam atau toko."""
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM closing WHERE periode = ? AND status = 'tertutup' LIMIT 1;",
        (periode,)
    )
    if cur.fetchone() is not None:
        return True

    # Cek juga closing toko
    try:
        cur.execute(
            "SELECT 1 FROM closing_toko WHERE periode = ? AND status = 'closed' LIMIT 1;",
            (periode,)
        )
        if cur.fetchone() is not None:
            return True
    except sqlite3.OperationalError:
        pass

    return False


def hitung_saldo_simpanan_anggota(
    conn: sqlite3.Connection, anggota_id: int
) -> Dict[str, int]:
    """
    Menghitung saldo simpanan per jenis ('pokok', 'wajib', 'sukarela') serta total saldo.
    Saldo dihitung hanya dari transaksi efektif berstatus 'NORMAL'.
    Transaksi yang dibatalkan dan pembaliknya tidak mempengaruhi saldo.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT jenis,
               COALESCE(SUM(CASE WHEN arah = 'setor' THEN jumlah ELSE -jumlah END), 0) AS saldo
        FROM v_simpanan_efektif
        WHERE anggota_id = ? AND status_efektif = 'NORMAL'
        GROUP BY jenis;
        """,
        (anggota_id,)
    )
    hasil = {"pokok": 0, "wajib": 0, "sukarela": 0}
    for row in cur.fetchall():
        jenis = row["jenis"]
        if jenis in hasil:
            hasil[jenis] = row["saldo"]
    hasil["total"] = hasil["pokok"] + hasil["wajib"] + hasil["sukarela"]
    return hasil


def tambah_transaksi_simpanan(
    conn: sqlite3.Connection,
    anggota_id: int,
    jenis: str,
    arah: str,
    jumlah: int,
    tanggal: str,
    keterangan: Optional[str] = None
) -> int:
    """
    Menambah transaksi simpanan (setor atau tarik).
    Sekaligus menulis ke kas_transaksi secara atomik (transaksi database).
    """
    if jenis not in ("pokok", "wajib", "sukarela"):
        raise ValueError(f"Jenis simpanan tidak valid: {jenis}")
    if arah not in ("setor", "tarik"):
        raise ValueError(f"Arah simpanan harus 'setor' atau 'tarik': {arah}")
    if not isinstance(jumlah, int) or jumlah <= 0:
        raise ValueError("Jumlah simpanan harus berupa bilangan bulat rupiah lebih dari 0.")

    periode = tanggal[:7]  # Format 'YYYY-MM'
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Transaksi tidak dapat disimpan.")

    # Cek kecukupan saldo jika penarikan
    if arah == "tarik":
        saldo_saat_ini = hitung_saldo_simpanan_anggota(conn, anggota_id)
        saldo_jenis = saldo_saat_ini.get(jenis, 0)
        if jumlah > saldo_jenis:
            raise ValueError(
                f"Saldo simpanan {jenis} tidak mencukupi. Saldo saat ini: {format_rupiah(saldo_jenis)}"
            )

    # Ambil info nama anggota untuk detail kas & log
    cur = conn.cursor()
    cur.execute("SELECT nama, no_anggota, status FROM anggota WHERE id = ?;", (anggota_id,))
    anggota = cur.fetchone()
    if not anggota:
        raise ValueError("Data anggota tidak ditemukan.")

    nama_anggota = anggota["nama"]
    ket_bersih = keterangan.strip() if keterangan else ""

    with conn:
        # 1. Simpan transaksi simpanan
        cur = conn.execute(
            """
            INSERT INTO simpanan_transaksi 
            (anggota_id, jenis, arah, jumlah, tanggal, keterangan, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (anggota_id, jenis, arah, jumlah, tanggal, ket_bersih or None, periode)
        )
        simp_id = cur.lastrowid

        # 2. Simpan buku kas otomatis
        masuk = jumlah if arah == "setor" else 0
        keluar = jumlah if arah == "tarik" else 0
        ket_kas = f"Simpanan {jenis} ({arah}) {nama_anggota}"
        if ket_bersih:
            ket_kas += f" - {ket_bersih}"

        conn.execute(
            """
            INSERT INTO kas_transaksi 
            (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
            VALUES (?, ?, ?, ?, 'simpanan', ?, ?);
            """,
            (tanggal, ket_kas, masuk, keluar, simp_id, periode)
        )

        # 3. Catat log aktivitas
        detail_log = (
            f"Simpanan {jenis} {arah} Rp {jumlah:,} untuk {nama_anggota}"
        ).replace(",", ".")
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "simpanan_transaksi", simp_id, detail_log)
        )

    return simp_id


def balik_transaksi_simpanan(
    conn: sqlite3.Connection,
    transaksi_id: int,
    alasan: str,
    tanggal_balik: str
) -> int:
    """
    Melakukan transaksi pembalik untuk koreksi simpanan sesuai aturan keuangan RULES.md.
    Tidak ada DELETE/UPDATE pada transaksi keuangan.
    """
    alasan_bersih = alasan.strip()
    if not alasan_bersih:
        raise ValueError("Alasan koreksi pembalik wajib diisi.")

    cur = conn.cursor()
    cur.execute("SELECT * FROM simpanan_transaksi WHERE id = ?;", (transaksi_id,))
    tx = cur.fetchone()
    if not tx:
        raise ValueError("Transaksi simpanan yang ingin dibalik tidak ditemukan.")

    # Cek apakah transaksi sudah pernah dibalik
    if tx["membalik_id"] is not None:
        raise ValueError("Transaksi ini merupakan transaksi pembalik dan tidak dapat dibalik lagi.")

    cur.execute("SELECT 1 FROM simpanan_transaksi WHERE membalik_id = ? LIMIT 1;", (transaksi_id,))
    if cur.fetchone():
        raise ValueError("Transaksi ini sudah pernah dibalik sebelumnya.")

    # Pastikan tanggal pembalik berada di periode berjalan yang belum terkunci
    periode_balik = tanggal_balik[:7]
    if cek_periode_terkunci(conn, periode_balik):
        raise ValueError(f"Periode pembalik {periode_balik} sudah ditutup (closing).")

    arah_lawan = "tarik" if tx["arah"] == "setor" else "setor"
    anggota_id = tx["anggota_id"]
    jenis = tx["jenis"]
    jumlah = tx["jumlah"]

    # Ambil info anggota
    cur.execute("SELECT nama FROM anggota WHERE id = ?;", (anggota_id,))
    row_ang = cur.fetchone()
    nama_ang = row_ang["nama"] if row_ang else ""

    # Jika membalik setoran (artinya uang ditarik kembali), cek kecukupan saldo
    if arah_lawan == "tarik":
        saldo = hitung_saldo_simpanan_anggota(conn, anggota_id)
        if saldo.get(jenis, 0) < jumlah:
            raise ValueError(
                f"Saldo {jenis} tidak mencukupi untuk melakukan pembalik (sisa saldo {format_rupiah(saldo.get(jenis, 0))})."
            )

    # 1. Simpan transaksi pembalik (membalik_id menunjuk ke ID transaksi asal)
    ket_balik = f"Koreksi pembalik ID #{transaksi_id}: {alasan_bersih}"
    with conn:
        cur = conn.execute(
            """
            INSERT INTO simpanan_transaksi 
            (anggota_id, jenis, arah, jumlah, tanggal, keterangan, membalik_id, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (anggota_id, jenis, arah_lawan, jumlah, tanggal_balik, ket_balik, transaksi_id, periode_balik)
        )
        pembalik_id = cur.lastrowid

        # 3. Catat lawan di buku kas
        masuk = jumlah if arah_lawan == "setor" else 0
        keluar = jumlah if arah_lawan == "tarik" else 0
        ket_kas = f"Pembalik simpanan #{transaksi_id} ({nama_ang}) - {alasan_bersih}"
        conn.execute(
            """
            INSERT INTO kas_transaksi 
            (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
            VALUES (?, ?, ?, ?, 'simpanan', ?, ?);
            """,
            (tanggal_balik, ket_kas, masuk, keluar, pembalik_id, periode_balik)
        )

        # 4. Log aktivitas
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("balik", "simpanan_transaksi", pembalik_id, f"Pembalik transaksi simpanan #{transaksi_id}: {alasan_bersih}")
        )

    return pembalik_id


def ambil_riwayat_simpanan(
    conn: sqlite3.Connection,
    anggota_id: Optional[int] = None,
    jenis: Optional[str] = None,
    kata_kunci: str = "",
    limit: int = 100,
    offset: int = 0
) -> List[sqlite3.Row]:
    """Mengambil riwayat transaksi simpanan beserta nama anggota."""
    cur = conn.cursor()
    query = """
        SELECT st.*, a.nama AS nama_anggota, a.no_anggota, a.unit
        FROM simpanan_transaksi st
        JOIN anggota a ON st.anggota_id = a.id
        WHERE 1=1
    """
    params: List[Any] = []

    if anggota_id:
        query += " AND st.anggota_id = ?"
        params.append(anggota_id)

    if jenis in ("pokok", "wajib", "sukarela"):
        query += " AND st.jenis = ?"
        params.append(jenis)

    if kata_kunci.strip():
        k = f"%{kata_kunci.strip()}%"
        query += " AND (a.nama LIKE ? OR a.no_anggota LIKE ? OR st.keterangan LIKE ?)"
        params.extend([k, k, k])

    query += " ORDER BY st.tanggal DESC, st.id DESC LIMIT ? OFFSET ?;"
    params.extend([limit, offset])

    cur.execute(query, params)
    return cur.fetchall()
