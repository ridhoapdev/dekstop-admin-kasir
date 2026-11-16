"""
app/db/repo_pembelian.py — Repositori Pembelian (Barang Masuk) Toko.
Mendukung:
- Satu faktur banyak baris detail barang
- Snapshot konversi per baris (jumlah_input, satuan_input, isi_per_satuan, jumlah_dasar, harga_per_satuan_input, total_biaya)
- Penguncian satuan_barang yang dipakai
- Integrasi ke layanan_stok (tambah_stok_masuk) untuk pembuatan lot_stok FIFO & mutasi_stok
- Integrasi status bayar:
  * tunai: potong kas toko langsung (kas_toko_transaksi keluar, sumber='pembelian')
  * belum_dibayar: hutang dagang supplier
- Pembayaran hutang supplier (bisa sebagian atau lunas) via kas toko
- Pembalik faktur pembelian:
  * Membatalkan lot dan mutasi HANYA JIKA lot belum terpakai!
  * Jika lot sudah terpakai sebagian, tolak dengan pesan jelas dan sarankan retur/penyesuaian
  * Membalik arus kas toko jika dulu dibayar tunai
  * Membalik pembayaran hutang terkait jika ada
"""
import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from app.db.repo_simpanan import cek_periode_terkunci
from app.db.repo_barang import kunci_satuan_barang_jika_dipakai
from app.layanan.layanan_stok import tambah_stok_masuk
from app.db.repo_kas_toko import tambah_kas_toko
from app.layanan.bus_sinyal import kirim_sinyal


def buat_faktur_pembelian(
    conn: sqlite3.Connection,
    no_faktur: str,
    supplier_id: int,
    tanggal: str,
    status_bayar: str,  # 'tunai' atau 'belum_dibayar'
    items: List[Dict[str, Any]],
    keterangan: Optional[str] = None
) -> int:
    """
    Membuat faktur pembelian baru secara atomik:
    items format:
    [
        {
            "barang_id": int,
            "jumlah_input": int,
            "satuan_input": str,
            "isi_per_satuan": int,
            "harga_per_satuan_input": int
        }, ...
    ]
    """
    no_fak_clean = no_faktur.strip()
    if not no_fak_clean:
        raise ValueError("Nomor faktur tidak boleh kosong.")
    if not items:
        raise ValueError("Faktur harus memiliki minimal satu baris barang.")
    if status_bayar not in ("tunai", "belum_dibayar"):
        raise ValueError("Status bayar harus 'tunai' atau 'belum_dibayar'.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Faktur tidak dapat disimpan.")

    # Cek duplikasi no faktur
    cur = conn.cursor()
    cur.execute("SELECT id FROM pembelian_faktur WHERE no_faktur = ?;", (no_fak_clean,))
    if cur.fetchone():
        raise ValueError(f"Nomor faktur '{no_fak_clean}' sudah pernah digunakan.")

    # Hitung total biaya keseluruhan
    total_faktur = 0
    validated_items = []
    for it in items:
        b_id = int(it["barang_id"])
        jml_input = int(it["jumlah_input"])
        sat_input = str(it["satuan_input"]).strip()
        isi_per_satuan = int(it["isi_per_satuan"])
        harga_input = int(it["harga_per_satuan_input"])

        if jml_input <= 0:
            raise ValueError(f"Jumlah input barang ID {b_id} harus > 0.")
        if isi_per_satuan <= 0:
            raise ValueError(f"Isi konversi satuan barang ID {b_id} harus > 0.")
        if harga_input < 0:
            raise ValueError(f"Harga satuan barang ID {b_id} tidak boleh negatif.")

        jml_dasar = jml_input * isi_per_satuan
        total_baris = jml_input * harga_input
        total_faktur += total_baris

        validated_items.append({
            "barang_id": b_id,
            "jumlah_input": jml_input,
            "satuan_input": sat_input,
            "isi_per_satuan": isi_per_satuan,
            "jumlah_dasar": jml_dasar,
            "harga_per_satuan_input": harga_input,
            "total_biaya": total_baris
        })

    with conn:
        # 1. Simpan pembelian_faktur
        cur_f = conn.execute(
            """
            INSERT INTO pembelian_faktur (
                no_faktur, supplier_id, tanggal, status_bayar,
                total_biaya, keterangan, periode
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                no_fak_clean, supplier_id, tanggal, status_bayar,
                total_faktur, keterangan.strip() if keterangan else None, periode
            )
        )
        faktur_id = cur_f.lastrowid

        # 2. Simpan pembelian_detail, buat lot_stok, mutasi_stok, dan kunci satuan
        for vit in validated_items:
            cur_d = conn.execute(
                """
                INSERT INTO pembelian_detail (
                    faktur_id, barang_id, jumlah_input, satuan_input,
                    isi_per_satuan, jumlah_dasar, harga_per_satuan_input,
                    total_biaya
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    faktur_id, vit["barang_id"], vit["jumlah_input"],
                    vit["satuan_input"], vit["isi_per_satuan"],
                    vit["jumlah_dasar"], vit["harga_per_satuan_input"],
                    vit["total_biaya"]
                )
            )
            detail_id = cur_d.lastrowid

            # Kunci satuan barang jika belum terkunci
            kunci_satuan_barang_jika_dipakai(conn, vit["barang_id"], vit["satuan_input"])

            # Tambah ke inventori stok FIFO real-time
            tambah_stok_masuk(
                conn=conn,
                barang_id=vit["barang_id"],
                qty=vit["jumlah_dasar"],
                total_biaya=vit["total_biaya"],
                asal="pembelian",
                ref_tabel="pembelian_detail",
                ref_id=detail_id,
                tanggal=tanggal,
                supplier_id=supplier_id
            )

        # 3. Jika status_bayar == 'tunai', potong kas toko
        if status_bayar == "tunai" and total_faktur > 0:
            tambah_kas_toko(
                conn=conn,
                tanggal=tanggal,
                keterangan=f"Pembelian tunai faktur {no_fak_clean}",
                masuk=0,
                keluar=total_faktur,
                sumber="pembelian",
                ref_tabel="pembelian_faktur",
                ref_id=faktur_id
            )

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "pembelian_faktur", faktur_id, f"Faktur beli {no_fak_clean} Total Rp {total_faktur:,}".replace(",", "."))
        )

    kirim_sinyal("pembelian_berubah")
    return faktur_id


def bayar_hutang_pembelian(
    conn: sqlite3.Connection,
    faktur_id: int,
    tanggal: str,
    jumlah_bayar: int,
    keterangan: Optional[str] = None
) -> int:
    """Membayar hutang pembelian ke supplier menggunakan kas toko."""
    if jumlah_bayar <= 0:
        raise ValueError("Jumlah pembayaran hutang harus > 0.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Pembayaran hutang tidak dapat disimpan.")

    cur = conn.cursor()
    cur.execute("SELECT no_faktur, total_biaya, status_bayar FROM pembelian_faktur WHERE id = ?;", (faktur_id,))
    f_row = cur.fetchone()
    if not f_row:
        raise ValueError("Faktur pembelian tidak ditemukan.")

    no_faktur, total_biaya, status_bayar = f_row[0], f_row[1], f_row[2]

    # Hitung total sudah dibayar efektif
    cur.execute(
        """
        SELECT COALESCE(SUM(jumlah_bayar), 0)
        FROM pembayaran_hutang_supplier
        WHERE faktur_id = ? AND id NOT IN (
            SELECT membalik_id FROM pembayaran_hutang_supplier WHERE membalik_id IS NOT NULL
        ) AND membalik_id IS NULL;
        """,
        (faktur_id,)
    )
    total_sdh_bayar = cur.fetchone()[0]
    sisa_hutang = total_biaya - total_sdh_bayar

    if jumlah_bayar > sisa_hutang:
        raise ValueError(
            f"Jumlah bayar (Rp {jumlah_bayar:,}) melebihi sisa hutang faktur {no_faktur} (Rp {sisa_hutang:,}).".replace(",", ".")
        )

    with conn:
        cur_b = conn.execute(
            """
            INSERT INTO pembayaran_hutang_supplier (
                faktur_id, tanggal, jumlah_bayar, keterangan, periode
            ) VALUES (?, ?, ?, ?, ?);
            """,
            (faktur_id, tanggal, jumlah_bayar, keterangan.strip() if keterangan else None, periode)
        )
        bayar_id = cur_b.lastrowid

        # Catat kas toko keluar
        tambah_kas_toko(
            conn=conn,
            tanggal=tanggal,
            keterangan=f"Bayar hutang supplier faktur {no_faktur}",
            masuk=0,
            keluar=jumlah_bayar,
            sumber="bayar_hutang",
            ref_tabel="pembayaran_hutang_supplier",
            ref_id=bayar_id
        )

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "pembayaran_hutang_supplier", bayar_id, f"Bayar hutang faktur {no_faktur} Rp {jumlah_bayar:,}".replace(",", "."))
        )

    kirim_sinyal("pembelian_berubah")
    return bayar_id


def balik_faktur_pembelian(
    conn: sqlite3.Connection,
    faktur_id: int,
    tanggal_balik: str,
    keterangan: str = "Pembatalan faktur pembelian"
) -> int:
    """
    Pembalik faktur pembelian:
    - Membatalkan lot HANYA JIKA lot belum terpakai.
    - Jika sudah terpakai sebagian, tolak dengan pesan jelas dan sarankan retur/penyesuaian.
    - Balikkan mutasi stok, kas toko tunai, dan pembayaran hutang (jika ada).
    """
    periode_balik = tanggal_balik[:7]
    if cek_periode_terkunci(conn, periode_balik):
        raise ValueError(f"Periode {periode_balik} sudah ditutup (closing). Pembatalan faktur tidak dapat disimpan.")

    cur = conn.cursor()
    cur.execute("SELECT * FROM pembelian_faktur WHERE id = ?;", (faktur_id,))
    row_f = cur.fetchone()
    if not row_f:
        raise ValueError("Faktur pembelian tidak ditemukan.")

    fak = dict(row_f)
    if fak["membalik_id"] is not None:
        raise ValueError("Faktur ini adalah faktur pembalik dan tidak dapat dibatalkan lagi.")

    cur.execute("SELECT id FROM pembelian_faktur WHERE membalik_id = ?;", (faktur_id,))
    if cur.fetchone():
        raise ValueError("Faktur pembelian ini sudah pernah dibatalkan sebelumnya.")

    # Ambil semua detail barang
    cur.execute("SELECT * FROM pembelian_detail WHERE faktur_id = ?;", (faktur_id,))
    details = [dict(r) for r in cur.fetchall()]

    # Periksa seluruh lot_stok yang berasal dari detail pembelian faktur ini
    lots_to_cancel = []
    for det in details:
        cur.execute(
            """
            SELECT l.id, l.qty_awal, l.qty_sisa, b.nama
            FROM lot_stok l
            JOIN barang b ON l.barang_id = b.id
            WHERE l.ref_tabel = 'pembelian_detail' AND l.ref_id = ?;
            """,
            (det["id"],)
        )
        row_lot = cur.fetchone()
        if row_lot:
            lot_id, qty_awal, qty_sisa, nama_b = row_lot[0], row_lot[1], row_lot[2], row_lot[3]
            if qty_sisa < qty_awal:
                terpakai = qty_awal - qty_sisa
                raise ValueError(
                    f"Lot stok untuk barang '{nama_b}' sudah terpakai sebanyak {terpakai} unit. "
                    "Faktur pembelian tidak dapat dibatalkan secara penuh. "
                    "Silakan gunakan mekanisme retur pembelian atau penyesuaian stok opname."
                )
            lots_to_cancel.append((lot_id, det["barang_id"], qty_awal, det["total_biaya"]))

    with conn:
        # 1. Batalkan lot dan mutasi stok
        for lot_id, barang_id, qty_awal, total_biaya in lots_to_cancel:
            # Kosongkan lot
            conn.execute("UPDATE lot_stok SET qty_sisa = 0, biaya_sisa = 0 WHERE id = ?;", (lot_id,))

            # Tambahkan mutasi pembalik (koreksi)
            conn.execute(
                """
                INSERT INTO mutasi_stok (
                    barang_id, lot_id, tanggal, jenis, qty, biaya,
                    ref_tabel, ref_id, membalik_id, periode
                ) VALUES (?, ?, ?, 'koreksi', ?, ?, 'pembelian_faktur', ?, NULL, ?);
                """,
                (barang_id, lot_id, tanggal_balik, -qty_awal, -total_biaya, faktur_id, periode_balik)
            )

            # Kurangi cache stok barang
            conn.execute(
                "UPDATE barang SET stok_saat_ini = stok_saat_ini - ? WHERE id = ?;",
                (qty_awal, barang_id)
            )

        # 2. Balikkan kas toko jika tunai
        if fak["status_bayar"] == "tunai" and fak["total_biaya"] > 0:
            cur.execute(
                """
                SELECT id FROM kas_toko_transaksi 
                WHERE ref_tabel = 'pembelian_faktur' AND ref_id = ? AND keluar > 0;
                """,
                (faktur_id,)
            )
            r_k = cur.fetchone()
            if r_k:
                kas_asli_id = r_k[0]
                tambah_kas_toko(
                    conn=conn,
                    tanggal=tanggal_balik,
                    keterangan=f"[PEMBALIK #{kas_asli_id}] Pembatalan beli faktur {fak['no_faktur']}",
                    masuk=fak["total_biaya"],
                    keluar=0,
                    sumber="pembelian",
                    ref_tabel="pembelian_faktur",
                    ref_id=faktur_id
                )

        # 3. Balikkan pembayaran hutang yang sudah terjadi (jika ada)
        cur.execute(
            """
            SELECT id, jumlah_bayar FROM pembayaran_hutang_supplier
            WHERE faktur_id = ? AND membalik_id IS NULL;
            """,
            (faktur_id,)
        )
        for r_b in cur.fetchall():
            b_id, jml_b = r_b[0], r_b[1]
            conn.execute(
                """
                INSERT INTO pembayaran_hutang_supplier (
                    faktur_id, tanggal, jumlah_bayar, keterangan, membalik_id, periode
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    faktur_id, tanggal_balik, -jml_b,
                    f"[PEMBALIK #{b_id}] Pembatalan faktur", b_id, periode_balik
                )
            )
            # Kembalikan kas keluar pembayaran hutang
            tambah_kas_toko(
                conn=conn,
                tanggal=tanggal_balik,
                keterangan=f"Pengembalian kas bayar hutang faktur {fak['no_faktur']}",
                masuk=jml_b,
                keluar=0,
                sumber="bayar_hutang",
                ref_tabel="pembelian_faktur",
                ref_id=faktur_id
            )

        # 4. Buat record pembalik faktur
        cur_pf = conn.execute(
            """
            INSERT INTO pembelian_faktur (
                no_faktur, supplier_id, tanggal, status_bayar,
                total_biaya, keterangan, membalik_id, periode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                f"PEMBALIK-{fak['no_faktur']}", fak["supplier_id"],
                tanggal_balik, fak["status_bayar"], -fak["total_biaya"],
                f"[PEMBALIK #{faktur_id}] {keterangan}", faktur_id, periode_balik
            )
        )
        pembalik_faktur_id = cur_pf.lastrowid

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("balik", "pembelian_faktur", pembalik_faktur_id, f"Balik faktur {fak['no_faktur']}")
        )

    kirim_sinyal("pembelian_berubah")
    kirim_sinyal("stok_berubah")
    return pembalik_faktur_id


def ambil_daftar_faktur_pembelian(
    conn: sqlite3.Connection,
    kata_kunci: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Mengambil riwayat faktur pembelian beserta info supplier & sisa hutang."""
    cur = conn.cursor()
    query = """
        SELECT 
            pf.*,
            s.nama AS nama_supplier,
            COALESCE((
                SELECT SUM(phs.jumlah_bayar) 
                FROM pembayaran_hutang_supplier phs
                WHERE phs.faktur_id = pf.id 
                  AND phs.id NOT IN (SELECT membalik_id FROM pembayaran_hutang_supplier WHERE membalik_id IS NOT NULL)
                  AND phs.membalik_id IS NULL
            ), 0) AS total_sudah_dibayar
        FROM v_pembelian_faktur_efektif pf
        JOIN supplier s ON pf.supplier_id = s.id
        WHERE 1=1
    """
    params: List[Any] = []
    if kata_kunci:
        k = f"%{kata_kunci.strip()}%"
        query += " AND (pf.no_faktur LIKE ? OR s.nama LIKE ?)"
        params.extend([k, k])

    query += " ORDER BY pf.tanggal DESC, pf.id DESC LIMIT ?;"
    params.append(limit)

    cur.execute(query, params)
    rows = cur.fetchall()

    hasil = []
    for r in rows:
        d = dict(r)
        if d["status_bayar"] == "tunai":
            d["sisa_hutang"] = 0
            d["status_lunas"] = "Lunas (Tunai)"
        else:
            sisa = d["total_biaya"] - d["total_sudah_dibayar"]
            d["sisa_hutang"] = max(0, sisa)
            d["status_lunas"] = "Lunas" if sisa <= 0 else f"Belum Lunas (Sisa: {sisa:,})".replace(",", ".")
        hasil.append(d)

    return hasil


def ambil_detail_faktur_pembelian(conn: sqlite3.Connection, faktur_id: int) -> Dict[str, Any]:
    """Mengambil faktur pembelian lengkap beserta baris-baris detail barangnya."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT pf.*, s.nama AS nama_supplier, s.no_hp AS hp_supplier
        FROM pembelian_faktur pf
        JOIN supplier s ON pf.supplier_id = s.id
        WHERE pf.id = ?;
        """,
        (faktur_id,)
    )
    row_f = cur.fetchone()
    if not row_f:
        raise ValueError("Faktur pembelian tidak ditemukan.")

    faktur = dict(row_f)

    cur.execute(
        """
        SELECT pd.*, b.kode AS kode_barang, b.nama AS nama_barang, b.satuan_dasar
        FROM pembelian_detail pd
        JOIN barang b ON pd.barang_id = b.id
        WHERE pd.faktur_id = ?
        ORDER BY pd.id ASC;
        """,
        (faktur_id,)
    )
    faktur["items"] = [dict(r) for r in cur.fetchall()]
    return faktur
