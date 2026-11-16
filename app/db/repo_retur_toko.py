"""
app/db/repo_retur_toko.py — Repositori Transaksi Retur Unit Toko:
1. Retur ke Supplier (retur barang sisa lot -> mengurangi hutang atau menambah kas toko)
2. Retur ke Penitip di luar setoran harian (barang rusak milik titipan -> mutasi retur_penitip)
3. Retur Penjualan (pembeli mengembalikan barang -> stok kembali ke lot asal FIFO dengan biaya sama, kembali kas atau potong piutang)
4. Pembatalan Transaksi Retur (mekanisme transaksi pembalik membalik_id)
"""
import sqlite3
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from app.db.repo_simpanan import cek_periode_terkunci
from app.layanan.layanan_stok import kurangi_stok_fifo, tambah_stok_masuk, ambil_stok_barang
from app.db.repo_kas_toko import tambah_kas_toko
from app.layanan.bus_sinyal import kirim_sinyal


def _ambil_pengaturan(conn: sqlite3.Connection, kunci: str, default: str = "") -> str:
    cur = conn.cursor()
    cur.execute("SELECT nilai FROM pengaturan WHERE kunci = ?;", (kunci,))
    row = cur.fetchone()
    return row[0] if row else default


def buat_nomor_retur_supplier(conn: sqlite3.Connection, tanggal: str) -> str:
    format_tpl = _ambil_pengaturan(conn, "format_no_retur_supplier", "RS-{YYYY}{MM}{DD}-{NO}")
    tgl_dt = datetime.strptime(tanggal[:10], "%Y-%m-%d")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM retur_supplier WHERE tanggal = ?;", (tanggal,))
    urutan = cur.fetchone()[0] + 1
    hasil = format_tpl.replace("{YYYY}", str(tgl_dt.year))
    hasil = hasil.replace("{MM}", f"{tgl_dt.month:02d}")
    hasil = hasil.replace("{DD}", f"{tgl_dt.day:02d}")
    hasil = hasil.replace("{NO}", f"{urutan:04d}")
    return hasil


def buat_nomor_retur_penjualan(conn: sqlite3.Connection, tanggal: str) -> str:
    format_tpl = _ambil_pengaturan(conn, "format_no_retur_penjualan", "RJ-{YYYY}{MM}{DD}-{NO}")
    tgl_dt = datetime.strptime(tanggal[:10], "%Y-%m-%d")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM retur_penjualan WHERE tanggal = ?;", (tanggal,))
    urutan = cur.fetchone()[0] + 1
    hasil = format_tpl.replace("{YYYY}", str(tgl_dt.year))
    hasil = hasil.replace("{MM}", f"{tgl_dt.month:02d}")
    hasil = hasil.replace("{DD}", f"{tgl_dt.day:02d}")
    hasil = hasil.replace("{NO}", f"{urutan:04d}")
    return hasil


# ==========================================================
# 1. RETUR KE SUPPLIER
# ==========================================================

def catat_retur_supplier(
    conn: sqlite3.Connection,
    supplier_id: int,
    tanggal: str,
    jenis_kompensasi: str,  # 'potong_hutang' atau 'kas_masuk'
    daftar_item: List[Dict[str, Any]],
    pembelian_faktur_id: Optional[int] = None,
    alasan: Optional[str] = None
) -> Tuple[int, str]:
    """
    Mencatat retur barang ke supplier secara atomik:
    daftar_item: [
        {
            "barang_id": int,
            "lot_id": int,
            "jumlah_dasar": int,
            "biaya_per_satuan_dasar": int
        }, ...
    ]
    Syarat: jumlah_dasar tidak boleh melebihi sisa stok di lot_id tersebut!
    """
    if not daftar_item:
        raise ValueError("Item retur supplier tidak boleh kosong.")
    if jenis_kompensasi not in ("potong_hutang", "kas_masuk"):
        raise ValueError("Jenis kompensasi harus 'potong_hutang' atau 'kas_masuk'.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Retur tidak dapat disimpan.")

    cur = conn.cursor()

    # Validasi lot stok
    total_retur = 0
    for it in daftar_item:
        lot_id = it["lot_id"]
        qty_retur = it["jumlah_dasar"]
        if qty_retur <= 0:
            raise ValueError("Jumlah retur harus lebih besar dari nol.")

        cur.execute("SELECT barang_id, qty_sisa, biaya_sisa FROM lot_stok WHERE id = ?;", (lot_id,))
        row_lot = cur.fetchone()
        if not row_lot:
            raise ValueError(f"Lot stok #{lot_id} tidak ditemukan.")
        if row_lot["qty_sisa"] < qty_retur:
            raise ValueError(
                f"Jumlah retur ({qty_retur}) melebihi sisa lot stok ({row_lot['qty_sisa']})."
            )

        biaya_per_unit = it.get("biaya_per_satuan_dasar")
        if not biaya_per_unit:
            biaya_per_unit = row_lot["biaya_sisa"] // row_lot["qty_sisa"] if row_lot["qty_sisa"] > 0 else 0
            it["biaya_per_satuan_dasar"] = biaya_per_unit

        subtotal = qty_retur * biaya_per_unit
        it["total_biaya"] = subtotal
        total_retur += subtotal

    no_retur = buat_nomor_retur_supplier(conn, tanggal)

    with conn:
        # Catat header retur_supplier
        cur.execute(
            """
            INSERT INTO retur_supplier (
                no_retur, tanggal, pembelian_faktur_id, supplier_id, total_retur,
                jenis_kompensasi, alasan, periode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                no_retur, tanggal, pembelian_faktur_id, supplier_id, total_retur,
                jenis_kompensasi, alasan, periode
            )
        )
        retur_id = cur.lastrowid

        # Simpan baris & update lot_stok & mutasi_stok
        for it in daftar_item:
            cur.execute(
                """
                INSERT INTO retur_supplier_baris (
                    retur_supplier_id, barang_id, lot_id, jumlah_dasar,
                    biaya_per_satuan_dasar, total_biaya
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    retur_id, it["barang_id"], it["lot_id"], it["jumlah_dasar"],
                    it["biaya_per_satuan_dasar"], it["total_biaya"]
                )
            )

            # Potong lot_stok
            cur.execute(
                """
                UPDATE lot_stok 
                SET qty_sisa = qty_sisa - ?, biaya_sisa = biaya_sisa - ?
                WHERE id = ?;
                """,
                (it["jumlah_dasar"], it["total_biaya"], it["lot_id"])
            )

            # Catat mutasi stok keluar (retur_supplier)
            cur.execute(
                """
                INSERT INTO mutasi_stok (
                    barang_id, lot_id, tanggal, jenis, qty, biaya,
                    ref_tabel, ref_id, periode
                ) VALUES (?, ?, ?, 'retur_supplier', ?, ?, 'retur_supplier', ?, ?);
                """,
                (
                    it["barang_id"], it["lot_id"], tanggal, -it["jumlah_dasar"],
                    it["total_biaya"], retur_id, periode
                )
            )

            # Kurangi cache stok barang
            cur.execute(
                "UPDATE barang SET stok_saat_ini = stok_saat_ini - ? WHERE id = ?;",
                (it["jumlah_dasar"], it["barang_id"])
            )

        # Kompensasi keuangan
        if jenis_kompensasi == "kas_masuk":
            # Kas toko masuk dari pengembalian uang supplier
            kas_id = tambah_kas_toko(
                conn=conn,
                tanggal=tanggal,
                keterangan=f"Pengembalian uang retur supplier {no_retur}",
                masuk=total_retur,
                keluar=0,
                sumber="manual",
                ref_tabel="retur_supplier",
                ref_id=retur_id
            )
            cur.execute(
                "UPDATE retur_supplier SET kas_toko_transaksi_id = ? WHERE id = ?;",
                (kas_id, retur_id)
            )
        elif jenis_kompensasi == "potong_hutang" and pembelian_faktur_id:
            # Dicatat di log / otomatis mengurangi sisa faktur melalui query efektif
            pass

        # Catat log
        cur.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "retur_supplier", retur_id, f"Retur supplier #{no_retur} senilai {total_retur}")
        )

    kirim_sinyal("stok_berubah")
    kirim_sinyal("kas_toko_berubah")
    return retur_id, no_retur


# ==========================================================
# 2. RETUR KE PENITIP DI LUAR SETORAN HARIAN
# ==========================================================

def catat_retur_penitip_insidental(
    conn: sqlite3.Connection,
    penitip_id: int,
    tanggal: str,
    barang_id: int,
    lot_id: int,
    jumlah_dasar: int,
    alasan: str
) -> int:
    """
    Retur insidental barang titipan (misal rusak/basi sebelum sore).
    Mengurangi sisa lot titipan dan stok barang.
    """
    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing).")

    cur = conn.cursor()
    cur.execute("SELECT qty_sisa, biaya_sisa FROM lot_stok WHERE id = ? AND asal = 'titipan';", (lot_id,))
    row_lot = cur.fetchone()
    if not row_lot or row_lot["qty_sisa"] < jumlah_dasar:
        raise ValueError("Jumlah retur melebihi sisa stok titipan di lot tersebut.")

    biaya_retur = (row_lot["biaya_sisa"] // row_lot["qty_sisa"]) * jumlah_dasar if row_lot["qty_sisa"] > 0 else 0

    with conn:
        cur.execute(
            "UPDATE lot_stok SET qty_sisa = qty_sisa - ?, biaya_sisa = biaya_sisa - ? WHERE id = ?;",
            (jumlah_dasar, biaya_retur, lot_id)
        )
        cur.execute(
            """
            INSERT INTO mutasi_stok (
                barang_id, lot_id, tanggal, jenis, qty, biaya,
                ref_tabel, ref_id, periode
            ) VALUES (?, ?, ?, 'retur_penitip', ?, ?, 'retur_penitip', ?, ?);
            """,
            (barang_id, lot_id, tanggal, -jumlah_dasar, biaya_retur, penitip_id, periode)
        )
        cur.execute("UPDATE barang SET stok_saat_ini = stok_saat_ini - ? WHERE id = ?;", (jumlah_dasar, barang_id))
        cur.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "lot_stok", lot_id, f"Retur insidental {jumlah_dasar} unit ke penitip #{penitip_id}: {alasan}")
        )

    kirim_sinyal("stok_berubah")
    kirim_sinyal("penitipan_berubah")
    return lot_id


# ==========================================================
# 3. RETUR PENJUALAN (KONSUMEN MENGEMBALIKAN BARANG)
# ==========================================================

def catat_retur_penjualan(
    conn: sqlite3.Connection,
    penjualan_id: int,
    tanggal: str,
    jenis_kompensasi: str,  # 'kembali_kas' atau 'potong_piutang'
    daftar_item: List[Dict[str, Any]],
    alasan: Optional[str] = None
) -> Tuple[int, str]:
    """
    Retur penjualan:
    daftar_item: [
        {
            "penjualan_baris_id": int,
            "jumlah_dasar": int
        }, ...
    ]
    Mekanisme:
    1. Cek penjualan_baris dan penjualan_lot terkait untuk mengembalikan stok ke LOT ASAL dengan biaya yang sama persis.
    2. Jumlah retur tidak boleh melebihi jumlah yang dijual di baris nota tersebut.
    3. Jika kembali_kas: uang kas toko keluar.
    4. Jika potong_piutang: mengurangi saldo piutang nota tersebut.
    """
    if not daftar_item:
        raise ValueError("Item retur penjualan tidak boleh kosong.")
    if jenis_kompensasi not in ("kembali_kas", "potong_piutang"):
        raise ValueError("Jenis kompensasi harus 'kembali_kas' atau 'potong_piutang'.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Retur tidak dapat disimpan.")

    cur = conn.cursor()
    cur.execute("SELECT id, no_nota, pembeli_id, metode_bayar AS metode, total FROM penjualan WHERE id = ?;", (penjualan_id,))
    row_pj = cur.fetchone()
    if not row_pj:
        raise ValueError(f"Nota penjualan #{penjualan_id} tidak ditemukan.")

    pembeli_id = row_pj["pembeli_id"]
    total_nilai_retur = 0

    item_lengkap = []
    for it in daftar_item:
        baris_id = it["penjualan_baris_id"]
        qty_retur = it["jumlah_dasar"]
        if qty_retur <= 0:
            raise ValueError("Jumlah retur harus lebih besar dari nol.")

        cur.execute(
            """
            SELECT pb.id, pb.barang_id, pb.jumlah_dasar, pb.harga_jual_satuan_dasar,
                   COALESCE((SELECT SUM(rpb.jumlah_dasar) FROM retur_penjualan_baris rpb 
                             JOIN v_retur_penjualan_efektif vrp ON rpb.retur_penjualan_id = vrp.id
                             WHERE rpb.penjualan_baris_id = pb.id AND vrp.status_efektif = 'NORMAL'), 0) AS sudah_diretur
            FROM penjualan_baris pb
            WHERE pb.id = ? AND pb.penjualan_id = ?;
            """,
            (baris_id, penjualan_id)
        )
        row_baris = cur.fetchone()
        if not row_baris:
            raise ValueError(f"Baris nota #{baris_id} tidak valid untuk penjualan ini.")

        sisa_bisa_retur = row_baris["jumlah_dasar"] - row_baris["sudah_diretur"]
        if qty_retur > sisa_bisa_retur:
            raise ValueError(
                f"Jumlah retur ({qty_retur}) melebihi jumlah barang yang dapat diretur ({sisa_bisa_retur})."
            )

        hrg_jual_sat = row_baris["harga_jual_satuan_dasar"]
        subtotal_retur = qty_retur * hrg_jual_sat
        total_nilai_retur += subtotal_retur

        # Ambil lot asal dari penjualan_lot
        cur.execute(
            """
            SELECT lot_id, qty, biaya
            FROM penjualan_lot
            WHERE penjualan_baris_id = ?
            ORDER BY id ASC;
            """,
            (baris_id,)
        )
        lots = [dict(r) for r in cur.fetchall()]
        if not lots:
            raise ValueError(f"Data lot asal untuk baris #{baris_id} tidak ditemukan.")

        # Alokasikan pengembalian qty ke lot asal
        qty_sisa_alok = qty_retur
        for l in lots:
            if qty_sisa_alok <= 0:
                break
            kembali_ke_lot = min(qty_sisa_alok, l["qty"])
            biaya_per_unit = l["biaya"] // l["qty"] if l["qty"] > 0 else 0
            hpp_kembali = kembali_ke_lot * biaya_per_unit

            item_lengkap.append({
                "penjualan_baris_id": baris_id,
                "barang_id": row_baris["barang_id"],
                "lot_id": l["lot_id"],
                "jumlah_dasar": kembali_ke_lot,
                "harga_jual_satuan_dasar": hrg_jual_sat,
                "total_harga": kembali_ke_lot * hrg_jual_sat,
                "hpp_satuan_dasar": biaya_per_unit,
                "hpp_total": hpp_kembali
            })
            qty_sisa_alok -= kembali_ke_lot

    no_retur = buat_nomor_retur_penjualan(conn, tanggal)

    with conn:
        cur.execute(
            """
            INSERT INTO retur_penjualan (
                no_retur, tanggal, penjualan_id, pembeli_id, total_retur,
                jenis_kompensasi, alasan, periode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                no_retur, tanggal, penjualan_id, pembeli_id, total_nilai_retur,
                jenis_kompensasi, alasan, periode
            )
        )
        retur_id = cur.lastrowid

        for it in item_lengkap:
            cur.execute(
                """
                INSERT INTO retur_penjualan_baris (
                    retur_penjualan_id, penjualan_baris_id, barang_id, lot_id,
                    jumlah_dasar, harga_jual_satuan_dasar, total_harga,
                    hpp_satuan_dasar, hpp_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    retur_id, it["penjualan_baris_id"], it["barang_id"], it["lot_id"],
                    it["jumlah_dasar"], it["harga_jual_satuan_dasar"], it["total_harga"],
                    it["hpp_satuan_dasar"], it["hpp_total"]
                )
            )

            # Kembalikan stok ke lot_stok asal
            cur.execute(
                """
                UPDATE lot_stok
                SET qty_sisa = qty_sisa + ?, biaya_sisa = biaya_sisa + ?
                WHERE id = ?;
                """,
                (it["jumlah_dasar"], it["hpp_total"], it["lot_id"])
            )

            # Catat mutasi stok masuk (retur_penjualan)
            cur.execute(
                """
                INSERT INTO mutasi_stok (
                    barang_id, lot_id, tanggal, jenis, qty, biaya,
                    ref_tabel, ref_id, periode
                ) VALUES (?, ?, ?, 'masuk', ?, ?, 'retur_penjualan', ?, ?);
                """,
                (
                    it["barang_id"], it["lot_id"], tanggal, it["jumlah_dasar"],
                    it["hpp_total"], retur_id, periode
                )
            )

            # Tambahkan cache stok barang
            cur.execute(
                "UPDATE barang SET stok_saat_ini = stok_saat_ini + ? WHERE id = ?;",
                (it["jumlah_dasar"], it["barang_id"])
            )

        # Kompensasi keuangan
        if jenis_kompensasi == "kembali_kas":
            kas_id = tambah_kas_toko(
                conn=conn,
                tanggal=tanggal,
                keterangan=f"Pengembalian kas retur penjualan nota {row_pj['no_nota']}",
                masuk=0,
                keluar=total_nilai_retur,
                sumber="manual",
                ref_tabel="retur_penjualan",
                ref_id=retur_id
            )
            cur.execute(
                "UPDATE retur_penjualan SET kas_toko_transaksi_id = ? WHERE id = ?;",
                (kas_id, retur_id)
            )

        cur.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "retur_penjualan", retur_id, f"Retur penjualan nota #{row_pj['no_nota']} senilai {total_nilai_retur}")
        )

    kirim_sinyal("stok_berubah")
    kirim_sinyal("penjualan_berubah")
    kirim_sinyal("kas_toko_berubah")
    kirim_sinyal("piutang_berubah")
    return retur_id, no_retur
