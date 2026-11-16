"""
app/layanan/layanan_stok.py — Satu Layanan Tunggal Pengelolaan Stok FIFO Real-time & Mutasi.
DILARANG keras mengubah kolom barang.stok_saat_ini langsung dari luar!
Semua perubahan stok wajib melalui fungsi layanan ini di dalam transaksi database atomik.

Fitur:
- tambah_stok_masuk(conn, barang_id, qty, total_biaya, asal, ref_tabel, ref_id, tanggal, supplier_id, penitip_id)
- kurangi_stok_fifo(conn, barang_id, qty, jenis_mutasi, ref_tabel, ref_id, tanggal)
- balik_mutasi_stok(conn, mutasi_id, tanggal_balik, keterangan)
- rekonsiliasi_stok_barang(conn, barang_id=None) -> Dict
- pengaturan stok minus (blokir vs izinkan)
- pembulatan serap sisa pada pemakaian lot terakhir
- realtime event trigger via app.layanan.bus_sinyal
"""
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from app.layanan.bus_sinyal import kirim_sinyal
from app.db.repo_simpanan import cek_periode_terkunci


def cek_izinkan_stok_minus(conn: sqlite3.Connection) -> bool:
    """Mengecek apakah pengaturan sistem mengizinkan stok minus."""
    cur = conn.cursor()
    cur.execute("SELECT nilai FROM pengaturan WHERE kunci = 'izinkan_stok_minus';")
    row = cur.fetchone()
    return row is not None and row[0] in ("1", "true", "True")


def atur_izinkan_stok_minus(conn: sqlite3.Connection, izinkan: bool) -> None:
    """Mengatur konfigurasi izinkan stok minus."""
    val = "1" if izinkan else "0"
    with conn:
        conn.execute(
            """
            INSERT INTO pengaturan (kunci, nilai) VALUES ('izinkan_stok_minus', ?)
            ON CONFLICT(kunci) DO UPDATE SET nilai = excluded.nilai;
            """,
            (val,)
        )


def ambil_stok_barang(conn: sqlite3.Connection, barang_id: int) -> int:
    """Mengambil stok_saat_ini dari tabel barang."""
    cur = conn.cursor()
    cur.execute("SELECT stok_saat_ini FROM barang WHERE id = ?;", (barang_id,))
    row = cur.fetchone()
    return row[0] if row else 0


def tambah_stok_masuk(
    conn: sqlite3.Connection,
    barang_id: int,
    qty: int,
    total_biaya: int,
    asal: str,  # 'pembelian', 'titipan', 'penyesuaian', 'koreksi'
    ref_tabel: str,
    ref_id: int,
    tanggal: str,
    supplier_id: Optional[int] = None,
    penitip_id: Optional[int] = None,
    harga_jual_satuan_dasar: int = 0
) -> Tuple[int, int]:
    """
    Menambah stok masuk ke inventori:
    1. Membuat lot_stok baru dengan qty_awal=qty, qty_sisa=qty, total_biaya_awal=total_biaya, biaya_sisa=total_biaya.
    2. Mencatat mutasi_stok append-only dengan jenis='masuk'.
    3. Mengupdate barang.stok_saat_ini secara atomik.
    4. Mengirim sinyal event bus 'stok_berubah'.
    Mengembalikan (lot_id, mutasi_id).
    """
    if qty <= 0:
        raise ValueError("Kuantitas barang masuk harus > 0.")
    if total_biaya < 0:
        raise ValueError("Total biaya tidak boleh negatif.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Transaksi tidak dapat disimpan.")

    with conn:
        # 1. Insert lot_stok
        cur = conn.execute(
            """
            INSERT INTO lot_stok (
                barang_id, asal, ref_tabel, ref_id, tanggal_masuk,
                supplier_id, penitip_id, qty_awal, qty_sisa,
                total_biaya_awal, biaya_sisa, harga_jual_satuan_dasar
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                barang_id, asal, ref_tabel, ref_id, tanggal,
                supplier_id, penitip_id, qty, qty,
                total_biaya, total_biaya, harga_jual_satuan_dasar
            )
        )
        lot_id = cur.lastrowid

        # 2. Insert mutasi_stok
        cur_m = conn.execute(
            """
            INSERT INTO mutasi_stok (
                barang_id, lot_id, tanggal, jenis, qty, biaya,
                ref_tabel, ref_id, periode
            ) VALUES (?, ?, ?, 'masuk', ?, ?, ?, ?, ?);
            """,
            (
                barang_id, lot_id, tanggal, qty, total_biaya,
                ref_tabel, ref_id, periode
            )
        )
        mutasi_id = cur_m.lastrowid

        # 3. Update cache stok_saat_ini
        conn.execute(
            "UPDATE barang SET stok_saat_ini = stok_saat_ini + ? WHERE id = ?;",
            (qty, barang_id)
        )

    kirim_sinyal("stok_berubah")
    return lot_id, mutasi_id


def kurangi_stok_fifo(
    conn: sqlite3.Connection,
    barang_id: int,
    qty_diminta: int,
    jenis_mutasi: str,  # 'keluar_jual', 'retur_supplier', 'retur_penitip', 'rusak', 'hilang', 'kedaluwarsa', 'penyesuaian_opname'
    ref_tabel: str,
    ref_id: int,
    tanggal: str
) -> List[Dict[str, Any]]:
    """
    Mengurangi stok menggunakan algoritma FIFO (First-In, First-Out) real-time:
    - Urut lot berdasarkan tanggal_masuk ASC, lalu id ASC.
    - Menghitung biaya proporsional secara akurat (integer).
    - Selisih pembulatan diserap sepenuhnya pada pemakaian terakhir lot tersebut
      sehingga jumlah total biaya yang terpakai pas = total biaya awal lot tanpa sisa/selisih.
    - Jika stok tidak cukup:
      * Jika izinkan_stok_minus = False -> tolak transaksi dengan pesan ramah.
      * Jika izinkan_stok_minus = True -> kurangi lot yang ada, sisa dicatat minus (lot_id=None).
    - Memperbarui barang.stok_saat_ini secara atomik.
    - Mengembalikan daftar mutasi yang dibuat: [{'lot_id': ..., 'qty': ..., 'biaya': ..., 'mutasi_id': ...}].
    """
    if qty_diminta <= 0:
        raise ValueError("Kuantitas pengurangan stok harus > 0.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Transaksi tidak dapat disimpan.")

    stok_saat_ini = ambil_stok_barang(conn, barang_id)
    izinkan_minus = cek_izinkan_stok_minus(conn)

    if stok_saat_ini < qty_diminta and not izinkan_minus:
        # Ambil nama barang untuk pesan ramah
        cur_b = conn.cursor()
        cur_b.execute("SELECT nama, satuan_dasar FROM barang WHERE id = ?;", (barang_id,))
        b_info = cur_b.fetchone()
        nama_b = b_info[0] if b_info else f"ID {barang_id}"
        satuan_b = b_info[1] if b_info else "unit"
        raise ValueError(
            f"Stok tidak mencukupi untuk barang '{nama_b}'. "
            f"Permintaan: {qty_diminta} {satuan_b}, Stok tersedia: {stok_saat_ini} {satuan_b}."
        )

    # Ambil lot aktif urut tanggal_masuk ASC, id ASC (FIFO)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, qty_awal, qty_sisa, total_biaya_awal, biaya_sisa, penitip_id, harga_jual_satuan_dasar
        FROM lot_stok
        WHERE barang_id = ? AND qty_sisa > 0
        ORDER BY tanggal_masuk ASC, id ASC;
        """,
        (barang_id,)
    )
    lot_list = [dict(r) for r in cur.fetchall()]

    sisa_perlu = qty_diminta
    hasil_mutasi: List[Dict[str, Any]] = []
    total_qty_berkurang = 0

    for lot in lot_list:
        if sisa_perlu <= 0:
            break

        lot_id = lot["id"]
        qty_sisa_lot = lot["qty_sisa"]
        biaya_sisa_lot = lot["biaya_sisa"]
        ambil = min(sisa_perlu, qty_sisa_lot)

        # Hitung biaya pemakaian
        if ambil == qty_sisa_lot:
            # Pemakaian terakhir menghabiskan lot -> serap semua sisa biaya tanpa selisih pembulatan
            biaya_ambil = biaya_sisa_lot
        else:
            # Proporsional dari total biaya awal atau sisa biaya
            biaya_ambil = int(round((ambil * lot["total_biaya_awal"]) / lot["qty_awal"]))
            if biaya_ambil > biaya_sisa_lot:
                biaya_ambil = biaya_sisa_lot

        # Update lot_stok
        baru_qty_sisa = qty_sisa_lot - ambil
        baru_biaya_sisa = biaya_sisa_lot - biaya_ambil

        conn.execute(
            """
            UPDATE lot_stok
            SET qty_sisa = ?, biaya_sisa = ?
            WHERE id = ?;
            """,
            (baru_qty_sisa, baru_biaya_sisa, lot_id)
        )

        # Catat mutasi_stok (qty negatif)
        cur_m = conn.execute(
            """
            INSERT INTO mutasi_stok (
                barang_id, lot_id, tanggal, jenis, qty, biaya,
                ref_tabel, ref_id, periode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                barang_id, lot_id, tanggal, jenis_mutasi, -ambil, biaya_ambil,
                ref_tabel, ref_id, periode
            )
        )
        mutasi_id = cur_m.lastrowid

        hasil_mutasi.append({
            "lot_id": lot_id,
            "qty": ambil,
            "biaya": biaya_ambil,
            "mutasi_id": mutasi_id,
            "penitip_id": lot.get("penitip_id"),
            "harga_jual_satuan_dasar": lot.get("harga_jual_satuan_dasar", 0)
        })

        sisa_perlu -= ambil
        total_qty_berkurang += ambil

    # Jika masih ada sisa_perlu dan diizinkan minus
    if sisa_perlu > 0 and izinkan_minus:
        # Catat mutasi stok minus tanpa lot (lot_id=None, biaya=0)
        cur_m = conn.execute(
            """
            INSERT INTO mutasi_stok (
                barang_id, lot_id, tanggal, jenis, qty, biaya,
                ref_tabel, ref_id, periode
            ) VALUES (?, NULL, ?, ?, ?, 0, ?, ?, ?);
            """,
            (
                barang_id, tanggal, jenis_mutasi, -sisa_perlu,
                ref_tabel, ref_id, periode
            )
        )
        mutasi_id = cur_m.lastrowid
        hasil_mutasi.append({
            "lot_id": None,
            "qty": sisa_perlu,
            "biaya": 0,
            "mutasi_id": mutasi_id
        })
        total_qty_berkurang += sisa_perlu

    # Update cache stok_saat_ini
    conn.execute(
        "UPDATE barang SET stok_saat_ini = stok_saat_ini - ? WHERE id = ?;",
        (total_qty_berkurang, barang_id)
    )

    kirim_sinyal("stok_berubah")
    return hasil_mutasi


def balik_mutasi_stok(
    conn: sqlite3.Connection,
    mutasi_id: int,
    tanggal_balik: str,
    keterangan: str = "Koreksi mutasi stok"
) -> int:
    """
    Membalik mutasi stok yang salah input:
    - Tidak ada DELETE pada mutasi_stok.
    - Mencatat entri pembalik dengan qty berkebalikan dan membalik_id menunjuk ke mutasi asli.
    - Menyesuaikan lot_stok dan barang.stok_saat_ini.
    """
    periode_balik = tanggal_balik[:7]
    if cek_periode_terkunci(conn, periode_balik):
        raise ValueError(f"Periode {periode_balik} sudah ditutup (closing). Pembalikan tidak dapat diproses.")

    cur = conn.cursor()
    cur.execute("SELECT * FROM mutasi_stok WHERE id = ?;", (mutasi_id,))
    row_m = cur.fetchone()
    if not row_m:
        raise ValueError("Mutasi stok tidak ditemukan.")

    m = dict(row_m)
    if m["membalik_id"] is not None:
        raise ValueError("Transaksi ini adalah transaksi pembalik dan tidak dapat dibalik lagi.")

    # Cek apakah sudah pernah dibalik
    cur.execute("SELECT id FROM mutasi_stok WHERE membalik_id = ?;", (mutasi_id,))
    if cur.fetchone():
        raise ValueError("Transaksi mutasi ini sudah pernah dibatalkan sebelumnya.")

    qty_balik = -m["qty"]
    biaya_balik = -m["biaya"]
    lot_id = m["lot_id"]

    # Jika mutasi asli adalah mutasi keluar (qty < 0), pembalik mengembalikan stok ke lot asal (jika ada)
    if m["qty"] < 0 and lot_id:
        conn.execute(
            """
            UPDATE lot_stok
            SET qty_sisa = qty_sisa + ?, biaya_sisa = biaya_sisa + ?
            WHERE id = ?;
            """,
            (abs(m["qty"]), m["biaya"], lot_id)
        )
    elif m["qty"] > 0 and lot_id:
        # Mutasi masuk dibatalkan: hanya bisa jika lot belum terpakai!
        cur.execute("SELECT qty_awal, qty_sisa FROM lot_stok WHERE id = ?;", (lot_id,))
        row_lot = cur.fetchone()
        if row_lot:
            qty_awal, qty_sisa = row_lot[0], row_lot[1]
            if qty_sisa < qty_awal:
                terpakai = qty_awal - qty_sisa
                raise ValueError(
                    f"Lot stok ini sudah terpakai sebagian ({terpakai} unit). "
                    "Tidak dapat dibatalkan langsung. Silakan lakukan retur atau penyesuaian stok."
                )
            conn.execute("UPDATE lot_stok SET qty_sisa = 0, biaya_sisa = 0 WHERE id = ?;", (lot_id,))

    # Insert pembalik mutasi
    cur_p = conn.execute(
        """
        INSERT INTO mutasi_stok (
            barang_id, lot_id, tanggal, jenis, qty, biaya,
            ref_tabel, ref_id, membalik_id, periode
        ) VALUES (?, ?, ?, 'koreksi', ?, ?, ?, ?, ?, ?);
        """,
        (
            m["barang_id"], lot_id, tanggal_balik, qty_balik, biaya_balik,
            m["ref_tabel"], m["ref_id"], mutasi_id, periode_balik
        )
    )
    pembalik_id = cur_p.lastrowid

    # Update cache stok
    conn.execute(
        "UPDATE barang SET stok_saat_ini = stok_saat_ini + ? WHERE id = ?;",
        (qty_balik, m["barang_id"])
    )

    kirim_sinyal("stok_berubah")
    return pembalik_id


def rekonsiliasi_stok_barang(
    conn: sqlite3.Connection,
    barang_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Pemeriksaan rekonsiliasi stok:
    stok_saat_ini == SUM(mutasi_stok) == SUM(qty_sisa lot_stok).
    Dijalankan saat aplikasi dibuka atau sebelum closing.
    Jika ada ketidakcocokan, mengembalikan daftar selisih untuk peringatan ramah.
    """
    cur = conn.cursor()
    query = """
        SELECT 
            b.id AS barang_id,
            b.kode,
            b.nama,
            b.stok_saat_ini,
            COALESCE((SELECT SUM(qty) FROM mutasi_stok WHERE barang_id = b.id), 0) AS total_mutasi,
            COALESCE((SELECT SUM(qty_sisa) FROM lot_stok WHERE barang_id = b.id), 0) AS total_sisa_lot
        FROM barang b
    """
    params: List[Any] = []
    if barang_id:
        query += " WHERE b.id = ?"
        params.append(barang_id)

    cur.execute(query, params)
    rows = cur.fetchall()

    selisih_list = []
    for r in rows:
        stok_cache = r["stok_saat_ini"]
        tot_mutasi = r["total_mutasi"]
        tot_lot = r["total_sisa_lot"]

        # Catatan: Jika ada stok minus, lot_stok mungkin 0 sedangkan mutasi < 0
        cocok = (stok_cache == tot_mutasi) and (stok_cache == tot_lot or stok_cache < 0)
        if not cocok:
            selisih_list.append({
                "barang_id": r["barang_id"],
                "kode": r["kode"],
                "nama": r["nama"],
                "stok_saat_ini": stok_cache,
                "total_mutasi": tot_mutasi,
                "total_sisa_lot": tot_lot,
                "selisih_mutasi": stok_cache - tot_mutasi,
                "selisih_lot": stok_cache - tot_lot
            })

    return selisih_list
