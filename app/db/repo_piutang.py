"""
app/db/repo_piutang.py — Repositori Piutang Pembeli dan Pembayaran Otomatis FIFO Nota.
Aturan Bisnis:
- Pembayaran piutang dicatat per pembeli: tabel pembayaran_piutang.
- Otomatis dialokasikan ke NOTA KREDIT TERTUA dulu (tabel alokasi_piutang).
- Saldo piutang per nota dan per pembeli = total kredit - total alokasi (memperhitungkan pembalik).
- Pembayaran piutang menulis kas_toko masuk (sumber='bayar_piutang').
- Rekonsiliasi piutang: SUM(nota kredit efektif) - SUM(alokasi piutang efektif) = SUM(saldo piutang per pembeli).
- Peringatan batas utang pembeli dan nota lewat jatuh tempo.
"""
import sqlite3
from datetime import date
from typing import List, Dict, Any, Optional, Tuple
from app.db.repo_simpanan import cek_periode_terkunci
from app.db.repo_kas_toko import tambah_kas_toko
from app.layanan.bus_sinyal import kirim_sinyal


def ambil_daftar_ringkasan_piutang_pembeli(
    conn: sqlite3.Connection,
    hanya_yang_punya_utang: bool = True
) -> List[Dict[str, Any]]:
    """
    Mengambil daftar pembeli beserta total piutang, nota tertua, dan status keterlambatan jatuh tempo.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 
            p.id AS pembeli_id,
            p.nama AS nama_pembeli,
            p.no_hp,
            p.alamat,
            p.anggota_id,
            a.no_anggota,
            COALESCE((
                SELECT SUM(pj.total)
                FROM v_penjualan_efektif pj
                WHERE pj.pembeli_id = p.id AND pj.metode_bayar = 'kredit' AND pj.status_efektif = 'NORMAL'
            ), 0) AS total_kredit,
            COALESCE((
                SELECT SUM(ap.jumlah)
                FROM alokasi_piutang ap
                JOIN v_penjualan_efektif pj ON ap.penjualan_id = pj.id
                WHERE pj.pembeli_id = p.id AND ap.membalik_id IS NULL AND pj.status_efektif = 'NORMAL'
            ), 0) AS total_terbayar,
            (
                SELECT MIN(pj.tanggal)
                FROM v_penjualan_efektif pj
                WHERE pj.pembeli_id = p.id AND pj.metode_bayar = 'kredit' AND pj.status_efektif = 'NORMAL'
                  AND pj.total > (
                      SELECT COALESCE(SUM(ap.jumlah), 0) 
                      FROM alokasi_piutang ap 
                      WHERE ap.penjualan_id = pj.id AND ap.membalik_id IS NULL
                  )
            ) AS tanggal_nota_tertua,
            (
                SELECT MIN(pj.jatuh_tempo)
                FROM v_penjualan_efektif pj
                WHERE pj.pembeli_id = p.id AND pj.metode_bayar = 'kredit' AND pj.status_efektif = 'NORMAL'
                  AND pj.total > (
                      SELECT COALESCE(SUM(ap.jumlah), 0) 
                      FROM alokasi_piutang ap 
                      WHERE ap.penjualan_id = pj.id AND ap.membalik_id IS NULL
                  )
            ) AS jatuh_tempo_terdekat
        FROM pembeli p
        LEFT JOIN anggota a ON p.anggota_id = a.id
        WHERE p.aktif = 1
        ORDER BY p.nama COLLATE NOCASE ASC;
        """
    )
    rows = cur.fetchall()
    hasil = []
    tgl_ini = date.today().isoformat()

    for r in rows:
        d = dict(r)
        sisa_piutang = d["total_kredit"] - d["total_terbayar"]
        d["sisa_piutang"] = max(0, sisa_piutang)

        jt = d.get("jatuh_tempo_terdekat")
        d["lewat_jatuh_tempo"] = bool(jt and jt < tgl_ini and d["sisa_piutang"] > 0)

        if hanya_yang_punya_utang and d["sisa_piutang"] <= 0:
            continue
        hasil.append(d)

    return hasil


def ambil_daftar_nota_kredit_pembeli(
    conn: sqlite3.Connection,
    pembeli_id: int
) -> List[Dict[str, Any]]:
    """
    Mengambil seluruh nota kredit efektif milik pembeli beserta status alokasi pembayarannya.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 
            pj.id AS penjualan_id,
            pj.no_nota,
            pj.tanggal,
            pj.total,
            pj.jatuh_tempo,
            COALESCE((
                SELECT SUM(ap.jumlah)
                FROM alokasi_piutang ap
                WHERE ap.penjualan_id = pj.id AND ap.membalik_id IS NULL
            ), 0) AS terbayar
        FROM v_penjualan_efektif pj
        WHERE pj.pembeli_id = ? AND pj.metode_bayar = 'kredit' AND pj.status_efektif = 'NORMAL'
        ORDER BY pj.tanggal ASC, pj.id ASC;
        """,
        (pembeli_id,)
    )
    rows = cur.fetchall()
    tgl_ini = date.today().isoformat()

    hasil = []
    for r in rows:
        d = dict(r)
        sisa = d["total"] - d["terbayar"]
        d["sisa"] = max(0, sisa)
        if sisa <= 0:
            d["status"] = "Lunas"
        elif d["terbayar"] > 0:
            d["status"] = "Sebagian"
        elif d["jatuh_tempo"] and d["jatuh_tempo"] < tgl_ini:
            d["status"] = "Telat (Jatuh Tempo)"
        else:
            d["status"] = "Belum Lunas"
        hasil.append(d)

    return hasil


def bayar_piutang_pembeli(
    conn: sqlite3.Connection,
    pembeli_id: int,
    tanggal: str,
    jumlah: int,
    keterangan: Optional[str] = None
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Menerima pembayaran piutang dari pembeli:
    - Otomatis dialokasikan ke nota kredit TERTUA yang belum lunas (FIFO).
    - Mencatat pembayaran_piutang dan alokasi_piutang.
    - Menulis kas_toko masuk (sumber='bayar_piutang').
    Mengembalikan (pembayaran_piutang_id, alokasi_list).
    """
    if jumlah <= 0:
        raise ValueError("Jumlah pembayaran piutang harus > 0.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Pembayaran tidak dapat diproses.")

    cur = conn.cursor()
    cur.execute("SELECT nama FROM pembeli WHERE id = ?;", (pembeli_id,))
    row_pem = cur.fetchone()
    if not row_pem:
        raise ValueError("Pembeli tidak ditemukan.")
    nama_pembeli = row_pem[0]

    # Ambil nota kredit belum lunas urut tanggal ASC, id ASC (FIFO)
    semua_nota = ambil_daftar_nota_kredit_pembeli(conn, pembeli_id)
    nota_belum_lunas = [n for n in semua_nota if n["sisa"] > 0]

    total_utang_semua = sum(n["sisa"] for n in nota_belum_lunas)
    if jumlah > total_utang_semua:
        raise ValueError(
            f"Jumlah pembayaran (Rp {jumlah:,}) melebihi total seluruh utang pembeli {nama_pembeli} (Rp {total_utang_semua:,}).".replace(",", ".")
        )

    with conn:
        # 1. Simpan pembayaran_piutang
        cur_pp = conn.execute(
            """
            INSERT INTO pembayaran_piutang (pembeli_id, tanggal, jumlah, keterangan, periode)
            VALUES (?, ?, ?, ?, ?);
            """,
            (pembeli_id, tanggal, jumlah, keterangan.strip() if keterangan else f"Bayar piutang {nama_pembeli}", periode)
        )
        pembayaran_id = cur_pp.lastrowid

        # 2. Alokasikan ke nota tertua
        sisa_dana = jumlah
        alokasi_dibuat = []

        for n in nota_belum_lunas:
            if sisa_dana <= 0:
                break
            alok = min(sisa_dana, n["sisa"])
            conn.execute(
                """
                INSERT INTO alokasi_piutang (pembayaran_piutang_id, penjualan_id, jumlah)
                VALUES (?, ?, ?);
                """,
                (pembayaran_id, n["penjualan_id"], alok)
            )
            alokasi_dibuat.append({
                "penjualan_id": n["penjualan_id"],
                "no_nota": n["no_nota"],
                "jumlah_dialokasikan": alok
            })
            sisa_dana -= alok

        # 3. Catat kas toko masuk
        tambah_kas_toko(
            conn=conn,
            tanggal=tanggal,
            keterangan=f"Pembayaran piutang dari {nama_pembeli}",
            masuk=jumlah,
            keluar=0,
            sumber="bayar_piutang",
            ref_tabel="pembayaran_piutang",
            ref_id=pembayaran_id
        )

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "pembayaran_piutang", pembayaran_id, f"Bayar piutang {nama_pembeli} Rp {jumlah:,}".replace(",", "."))
        )

    kirim_sinyal("piutang_berubah")
    kirim_sinyal("kas_toko_berubah")
    return pembayaran_id, alokasi_dibuat


def balik_pembayaran_piutang(
    conn: sqlite3.Connection,
    pembayaran_piutang_id: int,
    tanggal_balik: str,
    keterangan: str = "Pembatalan pembayaran piutang"
) -> int:
    """
    Membatalkan pembayaran piutang:
    - Balikkan alokasi piutang.
    - Balikkan kas toko yang masuk.
    - Catat pembalik di pembayaran_piutang.
    """
    periode_balik = tanggal_balik[:7]
    if cek_periode_terkunci(conn, periode_balik):
        raise ValueError(f"Periode {periode_balik} sudah ditutup (closing). Pembatalan tidak dapat diproses.")

    cur = conn.cursor()
    cur.execute("SELECT * FROM pembayaran_piutang WHERE id = ?;", (pembayaran_piutang_id,))
    row_pp = cur.fetchone()
    if not row_pp:
        raise ValueError("Pembayaran piutang tidak ditemukan.")

    pp = dict(row_pp)
    if pp["membalik_id"] is not None:
        raise ValueError("Transaksi ini adalah pembalik dan tidak dapat dibatalkan lagi.")

    cur.execute("SELECT id FROM pembayaran_piutang WHERE membalik_id = ?;", (pembayaran_piutang_id,))
    if cur.fetchone():
        raise ValueError("Pembayaran piutang ini sudah pernah dibatalkan sebelumnya.")

    with conn:
        # 1. Balikkan alokasi piutang
        cur.execute("SELECT id, penjualan_id, jumlah FROM alokasi_piutang WHERE pembayaran_piutang_id = ? AND membalik_id IS NULL;", (pembayaran_piutang_id,))
        for r_al in cur.fetchall():
            al_id, pj_id, jml = r_al[0], r_al[1], r_al[2]
            conn.execute(
                """
                INSERT INTO alokasi_piutang (pembayaran_piutang_id, penjualan_id, jumlah, membalik_id)
                VALUES (?, ?, ?, ?);
                """,
                (pembayaran_piutang_id, pj_id, -jml, al_id)
            )

        # 2. Balikkan kas toko
        tambah_kas_toko(
            conn=conn,
            tanggal=tanggal_balik,
            keterangan=f"[PEMBALIK #{pembayaran_piutang_id}] Pembatalan pembayaran piutang",
            masuk=0,
            keluar=pp["jumlah"],
            sumber="bayar_piutang",
            ref_tabel="pembayaran_piutang",
            ref_id=pembayaran_piutang_id
        )

        # 3. Catat pembalik pembayaran_piutang
        cur_pem = conn.execute(
            """
            INSERT INTO pembayaran_piutang (pembeli_id, tanggal, jumlah, keterangan, membalik_id, periode)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                pp["pembeli_id"], tanggal_balik, -pp["jumlah"],
                f"[PEMBALIK #{pembayaran_piutang_id}] {keterangan}",
                pembayaran_piutang_id, periode_balik
            )
        )
        pembalik_id = cur_pem.lastrowid

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("balik", "pembayaran_piutang", pembalik_id, f"Balik pembayaran piutang #{pembayaran_piutang_id}")
        )

    kirim_sinyal("piutang_berubah")
    kirim_sinyal("kas_toko_berubah")
    return pembalik_id


def hitung_total_piutang_semua_pembeli(conn: sqlite3.Connection) -> int:
    """Menghitung saldo seluruh piutang pembeli aktif toko."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 
            COALESCE((
                SELECT SUM(total) FROM v_penjualan_efektif WHERE metode_bayar = 'kredit' AND status_efektif = 'NORMAL'
            ), 0) -
            COALESCE((
                SELECT SUM(jumlah) FROM alokasi_piutang WHERE membalik_id IS NULL
            ), 0);
        """
    )
    return cur.fetchone()[0]
