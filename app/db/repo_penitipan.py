"""
app/db/repo_penitipan.py — Repositori Penitipan Harian dan Setoran Penitip (Sore Hari).
Aturan Bisnis:
- Penitipan dicatat per penitip per tanggal.
- Setiap baris penitipan membentuk LOT FIFO di lot_stok (asal='titipan') dengan total_biaya = harga_titip * qty.
- Harga titip dan harga jual boleh berbeda setiap penitipan dan setiap hari.
- Barang titipan terikat ke satu penitip (barang.penitip_id).
- Kewajiban ke penitip tercipta SAAT TERJUAL: hutang_penitip = qty terjual x harga titip (hpp).
- Setoran Penitip (Sore Hari):
  1) Hitung barang dititip, terjual, sisa, dan total yang harus dibayar.
  2) Bayar penitip (kas_toko KELUAR, sumber='bayar_penitip').
  3) Retur sisa barang (mutasi stok retur_penitip, lot berkurang).
  4) Mengunci baris agar tidak terbayar ganda.
  5) Mendukung bayar sebagian / bayar kemudian.
"""
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from app.db.repo_simpanan import cek_periode_terkunci
from app.db.repo_barang import kunci_satuan_barang_jika_dipakai
from app.layanan.layanan_stok import tambah_stok_masuk, ambil_stok_barang
from app.db.repo_kas_toko import tambah_kas_toko, hitung_saldo_kas_toko
from app.layanan.bus_sinyal import kirim_sinyal


def catat_penitipan_harian(
    conn: sqlite3.Connection,
    penitip_id: int,
    tanggal: str,
    items: List[Dict[str, Any]],
    catatan: Optional[str] = None
) -> int:
    """
    Mencatat penitipan harian baru secara atomik.
    items: [
        {
            "barang_id": int,
            "jumlah_input": int,
            "satuan_input": str,
            "isi_per_satuan": int,
            "harga_titip_satuan_dasar": int,
            "harga_jual_satuan_dasar": int
        }, ...
    ]
    """
    if not items:
        raise ValueError("Penitipan harus memiliki minimal satu baris barang.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Transaksi tidak dapat disimpan.")

    cur = conn.cursor()
    # Validasi barang titipan terikat ke penitip ini
    for it in items:
        b_id = int(it["barang_id"])
        cur.execute("SELECT jenis_kepemilikan, penitip_id, nama FROM barang WHERE id = ?;", (b_id,))
        row_b = cur.fetchone()
        if not row_b:
            raise ValueError(f"Barang ID {b_id} tidak ditemukan.")
        if row_b[0] != "titipan" or row_b[1] != penitip_id:
            raise ValueError(
                f"Barang '{row_b[2]}' bukan merupakan barang titipan untuk penitip ini. "
                "Barang titipan hanya boleh dititipkan oleh pemiliknya."
            )
        if int(it["jumlah_input"]) <= 0:
            raise ValueError(f"Jumlah titip barang '{row_b[2]}' harus > 0.")
        if int(it["harga_titip_satuan_dasar"]) < 0 or int(it["harga_jual_satuan_dasar"]) < 0:
            raise ValueError(f"Harga titip dan harga jual barang '{row_b[2]}' tidak boleh negatif.")

    with conn:
        cur_p = conn.execute(
            """
            INSERT INTO penitipan (penitip_id, tanggal, status, catatan, periode)
            VALUES (?, ?, 'aktif', ?, ?);
            """,
            (penitip_id, tanggal, catatan.strip() if catatan else None, periode)
        )
        penitipan_id = cur_p.lastrowid

        for it in items:
            b_id = int(it["barang_id"])
            jml_input = int(it["jumlah_input"])
            sat_input = str(it["satuan_input"]).strip()
            isi_per_satuan = int(it["isi_per_satuan"])
            hrg_titip = int(it["harga_titip_satuan_dasar"])
            hrg_jual = int(it["harga_jual_satuan_dasar"])
            jml_dasar = jml_input * isi_per_satuan
            total_biaya_lot = jml_dasar * hrg_titip

            # Kunci satuan barang jika belum terkunci
            kunci_satuan_barang_jika_dipakai(conn, b_id, sat_input)

            # Tambah lot stok FIFO
            lot_id, _ = tambah_stok_masuk(
                conn=conn,
                barang_id=b_id,
                qty=jml_dasar,
                total_biaya=total_biaya_lot,
                asal="titipan",
                ref_tabel="penitipan_baris",
                ref_id=0,  # di-update setelah insert baris
                tanggal=tanggal,
                penitip_id=penitip_id,
                harga_jual_satuan_dasar=hrg_jual
            )

            cur_b = conn.execute(
                """
                INSERT INTO penitipan_baris (
                    penitipan_id, barang_id, jumlah_input, satuan_input,
                    isi_per_satuan, jumlah_dasar, harga_titip_satuan_dasar,
                    harga_jual_satuan_dasar, lot_id, selesai
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0);
                """,
                (
                    penitipan_id, b_id, jml_input, sat_input,
                    isi_per_satuan, jml_dasar, hrg_titip, hrg_jual, lot_id
                )
            )
            baris_id = cur_b.lastrowid
            conn.execute("UPDATE lot_stok SET ref_id = ? WHERE id = ?;", (baris_id, lot_id))

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "penitipan", penitipan_id, f"Penitipan harian ID #{penitipan_id} tanggal {tanggal}")
        )

    kirim_sinyal("penitipan_berubah")
    kirim_sinyal("stok_berubah")
    return penitipan_id


def ambil_daftar_titipan_aktif_penitip(conn: sqlite3.Connection, penitip_id: int) -> List[Dict[str, Any]]:
    """
    Mengambil daftar baris penitipan yang belum diselesaikan untuk seorang penitip:
    Menghitung:
    - dititip (qty_awal lot)
    - sisa (qty_sisa lot)
    - terjual (dititip - sisa)
    - harga_titip
    - total_bayar = terjual * harga_titip
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 
            pb.id AS penitipan_baris_id,
            pb.penitipan_id,
            p.tanggal,
            pb.barang_id,
            b.kode AS kode_barang,
            b.nama AS nama_barang,
            b.satuan_dasar,
            pb.jumlah_input,
            pb.satuan_input,
            pb.isi_per_satuan,
            pb.jumlah_dasar,
            pb.harga_titip_satuan_dasar,
            pb.harga_jual_satuan_dasar,
            pb.lot_id,
            l.qty_awal,
            l.qty_sisa
        FROM penitipan_baris pb
        JOIN penitipan p ON pb.penitipan_id = p.id
        JOIN barang b ON pb.barang_id = b.id
        JOIN lot_stok l ON pb.lot_id = l.id
        WHERE p.penitip_id = ? AND pb.selesai = 0 AND p.status = 'aktif'
        ORDER BY p.tanggal ASC, pb.id ASC;
        """,
        (penitip_id,)
    )
    rows = cur.fetchall()
    hasil = []
    for r in rows:
        d = dict(r)
        qty_awal = d["qty_awal"]
        qty_sisa = d["qty_sisa"]
        qty_terjual = max(0, qty_awal - qty_sisa)
        d["qty_terjual"] = qty_terjual
        d["subtotal_bayar"] = qty_terjual * d["harga_titip_satuan_dasar"]
        hasil.append(d)
    return hasil


def hitung_total_hutang_penitip_terkini(conn: sqlite3.Connection, penitip_id: Optional[int] = None) -> int:
    """
    Menghitung total hutang yang belum dibayarkan ke penitip atas barang yang sudah terjual.
    Hutang = SUM(qty_terjual * harga_titip) - SUM(total_laku_terbayar efektif).
    Catatan: Baris titipan yang sudah diselesaikan (retur/tuntas) atau lot yang tidak terjual tidak dihitung sebagai hutang.
    """
    cur = conn.cursor()
    # 1. Total kewajiban dari barang laku yang tercatat di penjualan_lot untuk barang titipan
    # Atau dari penyelesaian_titipan_baris
    q1 = """
        SELECT COALESCE(SUM(pl.qty * pb.harga_titip_satuan_dasar), 0)
        FROM penjualan_lot pl
        JOIN penjualan_baris pjb ON pl.penjualan_baris_id = pjb.id
        JOIN v_penjualan_efektif pj ON pjb.penjualan_id = pj.id
        JOIN lot_stok l ON pl.lot_id = l.id
        JOIN penitipan_baris pb ON l.id = pb.lot_id
        WHERE pj.status_efektif = 'NORMAL' AND l.asal = 'titipan'
    """
    params1: List[Any] = []
    if penitip_id:
        q1 += " AND l.penitip_id = ?"
        params1.append(penitip_id)
    cur.execute(q1, params1)
    tot_kewajiban = cur.fetchone()[0]

    # 2. Total pembayaran yang sudah dilakukan efektif
    q2 = """
        SELECT COALESCE(SUM(total_laku_terbayar), 0)
        FROM v_pembayaran_penitip_efektif
        WHERE status_efektif = 'NORMAL'
    """
    params2: List[Any] = []
    if penitip_id:
        q2 += " AND penitip_id = ?"
        params2.append(penitip_id)
    cur.execute(q2, params2)
    tot_terbayar = cur.fetchone()[0]

    return max(0, tot_kewajiban - tot_terbayar)


def selesaikan_setoran_penitip(
    conn: sqlite3.Connection,
    penitip_id: int,
    tanggal: str,
    rincian_penyelesaian: List[Dict[str, Any]],
    nominal_bayar: int,
    keterangan: Optional[str] = None
) -> int:
    """
    Eksekusi Setoran Sore Hari Penitip:
    rincian_penyelesaian: [
        {
            "penitipan_baris_id": int,
            "lot_id": int,
            "qty_terjual": int,
            "harga_titip": int,
            "sisa_aksi": "retur" | "tinggal"  # kembalikan sisa ke penitip atau tetap tinggal di toko
        }, ...
    ]
    Proses:
    1. Catat pembayaran_penitip (total_laku_terbayar = nominal_bayar).
    2. Jika nominal_bayar > 0, potong kas toko (keluar, sumber='bayar_penitip'). Kas boleh minus dengan konfirmasi di UI.
    3. Untuk setiap baris:
       - Jika sisa_aksi == 'retur' dan qty_sisa > 0:
         Catat mutasi retur_penitip, kosongkan lot (qty_sisa = 0, biaya_sisa = 0), kurangi cache barang.stok_saat_ini.
       - Tandai penitipan_baris selesai = 1 jika semua tuntas diselesaikan.
    4. Simpan ke penyelesaian_titipan_baris untuk audit.
    Mengembalikan pembayaran_penitip_id.
    """
    if nominal_bayar < 0:
        raise ValueError("Nominal bayar tidak boleh negatif.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Transaksi tidak dapat disimpan.")

    cur = conn.cursor()
    cur.execute("SELECT nama FROM penitip WHERE id = ?;", (penitip_id,))
    row_pen = cur.fetchone()
    nama_penitip = row_pen[0] if row_pen else f"ID {penitip_id}"

    with conn:
        # 1. Buat pembayaran_penitip
        cur_bayar = conn.execute(
            """
            INSERT INTO pembayaran_penitip (penitip_id, tanggal, total_laku_terbayar, keterangan, periode)
            VALUES (?, ?, ?, ?, ?);
            """,
            (penitip_id, tanggal, nominal_bayar, keterangan.strip() if keterangan else f"Setoran sore {nama_penitip}", periode)
        )
        pembayaran_id = cur_bayar.lastrowid

        # 2. Catat kas toko jika ada uang keluar
        if nominal_bayar > 0:
            tambah_kas_toko(
                conn=conn,
                tanggal=tanggal,
                keterangan=f"Bayar laku barang titipan ke {nama_penitip}",
                masuk=0,
                keluar=nominal_bayar,
                sumber="bayar_penitip",
                ref_tabel="pembayaran_penitip",
                ref_id=pembayaran_id
            )

        # 3. Proses baris-baris penyelesaian
        for item in rincian_penyelesaian:
            pb_id = item["penitipan_baris_id"]
            lot_id = item["lot_id"]
            qty_terjual = item["qty_terjual"]
            hrg_titip = item["harga_titip"]
            sisa_aksi = item.get("sisa_aksi", "retur")

            cur.execute("SELECT barang_id, qty_sisa, biaya_sisa FROM lot_stok WHERE id = ?;", (lot_id,))
            lot_info = cur.fetchone()
            if not lot_info:
                continue

            barang_id, qty_sisa, biaya_sisa = lot_info[0], lot_info[1], lot_info[2]

            qty_retur = 0
            qty_tinggal = 0

            if sisa_aksi == "retur" and qty_sisa > 0:
                qty_retur = qty_sisa
                # Catat mutasi retur_penitip (qty negatif)
                conn.execute(
                    """
                    INSERT INTO mutasi_stok (
                        barang_id, lot_id, tanggal, jenis, qty, biaya,
                        ref_tabel, ref_id, periode
                    ) VALUES (?, ?, ?, 'retur_penitip', ?, ?, 'pembayaran_penitip', ?, ?);
                    """,
                    (barang_id, lot_id, tanggal, -qty_retur, biaya_sisa, pembayaran_id, periode)
                )
                # Kosongkan lot
                conn.execute("UPDATE lot_stok SET qty_sisa = 0, biaya_sisa = 0 WHERE id = ?;", (lot_id,))
                # Kurangi cache stok
                conn.execute("UPDATE barang SET stok_saat_ini = stok_saat_ini - ? WHERE id = ?;", (qty_retur, barang_id))
            else:
                qty_tinggal = qty_sisa

            # Catat penyelesaian baris
            subtotal_laku = qty_terjual * hrg_titip
            conn.execute(
                """
                INSERT INTO penyelesaian_titipan_baris (
                    pembayaran_penitip_id, penitipan_baris_id, lot_id,
                    qty_terjual, harga_titip, subtotal_bayar,
                    qty_sisa_retur, qty_sisa_tinggal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (pembayaran_id, pb_id, lot_id, qty_terjual, hrg_titip, subtotal_laku, qty_retur, qty_tinggal)
            )

            # Tandai baris selesai jika barang sudah tidak aktif atau laku/diretur semua
            if sisa_aksi == "retur" or qty_sisa == 0:
                conn.execute("UPDATE penitipan_baris SET selesai = 1 WHERE id = ?;", (pb_id,))

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "pembayaran_penitip", pembayaran_id, f"Penyelesaian setoran {nama_penitip} Rp {nominal_bayar:,}".replace(",", "."))
        )

    kirim_sinyal("penitipan_berubah")
    kirim_sinyal("stok_berubah")
    kirim_sinyal("kas_toko_berubah")
    return pembayaran_id
