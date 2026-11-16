"""
app/db/repo_kartu_toko.py — Repositori akses data terpusat untuk:
1. Kartu Barang (info dasar, stok dasar + setara satuan besar, lot FIFO aktif, laba periode, riwayat kartu stok, supplier/pembeli teratas)
2. Kartu Supplier (hutang dagang berjalan, faktur belum lunas, riwayat pembelian & pembayaran)
3. Kartu Penitip (barang titipan, hutang hari ini, riwayat setoran, total laba koperasi dari titipannya)
4. Kartu Pembeli (total utang, nota belum lunas, status telat jatuh tempo, riwayat beli/bayar, barang favorit)
5. Ringkasan Utang Toko Anggota (untuk Kartu Anggota Simpan Pinjam, terpisah dari pinjaman)
6. Pencarian Cepat Global Toko (Barang, Supplier, Penitip, Pembeli)
"""
import sqlite3
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from app.util.format import format_rupiah, format_tanggal_indo


def cari_entitas_toko_global(conn: sqlite3.Connection, kata_kunci: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Pencarian cepat barang, supplier, penitip, pembeli untuk dropdown pencarian global.
    Case-insensitive, cocok sebagian kata nama/kode/kata_kunci.
    """
    k = kata_kunci.strip()
    if not k:
        return []

    cur = conn.cursor()
    like_param = f"%{k}%"
    hasil: List[Dict[str, Any]] = []

    # 1. Barang
    cur.execute(
        """
        SELECT id, kode, nama, satuan_dasar, stok_saat_ini, harga_jual, jenis_kepemilikan
        FROM barang
        WHERE aktif = 1 AND (nama LIKE ? OR kode LIKE ? OR kata_kunci LIKE ?)
        ORDER BY nama ASC LIMIT ?;
        """,
        (like_param, like_param, like_param, limit)
    )
    for r in cur.fetchall():
        hasil.append({
            "tipe": "barang",
            "id": r["id"],
            "judul": f"Barang: {r['kode']} - {r['nama']}",
            "subjudul": f"Stok: {r['stok_saat_ini']} {r['satuan_dasar']} | Harga: Rp {r['harga_jual']:,}".replace(",", "."),
            "barang_id": r["id"]
        })

    # 2. Supplier
    cur.execute(
        """
        SELECT id, nama, no_hp, alamat
        FROM supplier
        WHERE aktif = 1 AND (nama LIKE ? OR no_hp LIKE ? OR alamat LIKE ?)
        ORDER BY nama ASC LIMIT ?;
        """,
        (like_param, like_param, like_param, limit)
    )
    for r in cur.fetchall():
        hasil.append({
            "tipe": "supplier",
            "id": r["id"],
            "judul": f"Supplier: {r['nama']}",
            "subjudul": f"Telp: {r['no_hp'] or '-'} | Alamat: {r['alamat'] or '-'}",
            "supplier_id": r["id"]
        })

    # 3. Penitip
    cur.execute(
        """
        SELECT id, nama, no_hp, alamat
        FROM penitip
        WHERE aktif = 1 AND (nama LIKE ? OR no_hp LIKE ? OR alamat LIKE ?)
        ORDER BY nama ASC LIMIT ?;
        """,
        (like_param, like_param, like_param, limit)
    )
    for r in cur.fetchall():
        hasil.append({
            "tipe": "penitip",
            "id": r["id"],
            "judul": f"Penitip: {r['nama']}",
            "subjudul": f"Telp: {r['no_hp'] or '-'} | Alamat: {r['alamat'] or '-'}",
            "penitip_id": r["id"]
        })

    # 4. Pembeli
    cur.execute(
        """
        SELECT id, nama, no_hp, alamat, anggota_id
        FROM pembeli
        WHERE aktif = 1 AND (nama LIKE ? OR no_hp LIKE ? OR catatan LIKE ?)
        ORDER BY nama ASC LIMIT ?;
        """,
        (like_param, like_param, like_param, limit)
    )
    for r in cur.fetchall():
        ket_ang = " (Anggota SP)" if r["anggota_id"] else ""
        hasil.append({
            "tipe": "pembeli",
            "id": r["id"],
            "judul": f"Pembeli: {r['nama']}{ket_ang}",
            "subjudul": f"Telp: {r['no_hp'] or '-'} | Alamat: {r['alamat'] or '-'}",
            "pembeli_id": r["id"]
        })

    return hasil


def konversi_ke_satuan_besar(stok_dasar: int, satuan_dasar: str, daftar_satuan: List[Dict[str, Any]]) -> str:
    """
    Format representasi setara satuan besar, misal: '47 pcs = 2 dus + 7 pcs'.
    """
    if not daftar_satuan or stok_dasar <= 0:
        return f"{stok_dasar} {satuan_dasar}"

    # Cari satuan dengan isi terbesar
    sat_terbesar = max(daftar_satuan, key=lambda s: s["isi_dalam_satuan_dasar"])
    isi = sat_terbesar["isi_dalam_satuan_dasar"]
    nama_sat = sat_terbesar["nama_satuan"]

    if isi <= 1:
        return f"{stok_dasar} {satuan_dasar}"

    jml_besar = stok_dasar // isi
    sisa = stok_dasar % isi

    if jml_besar > 0:
        if sisa > 0:
            return f"{stok_dasar} {satuan_dasar} = {jml_besar} {nama_sat} + {sisa} {satuan_dasar}"
        else:
            return f"{stok_dasar} {satuan_dasar} = {jml_besar} {nama_sat}"
    return f"{stok_dasar} {satuan_dasar}"


def ambil_data_kartu_barang(
    conn: sqlite3.Connection,
    barang_id: int,
    filter_jenis: str = "semua",
    tgl_awal: Optional[str] = None,
    tgl_akhir: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Optional[Dict[str, Any]]:
    """Mengambil seluruh rincian terpadu untuk layar Kartu Barang."""
    cur = conn.cursor()

    # 1. Info Dasar Barang
    cur.execute(
        """
        SELECT b.*, p.nama AS nama_penitip
        FROM barang b
        LEFT JOIN penitip p ON b.penitip_id = p.id
        WHERE b.id = ?;
        """,
        (barang_id,)
    )
    row_b = cur.fetchone()
    if not row_b:
        return None

    info_barang = dict(row_b)

    # 2. Satuan Barang
    cur.execute(
        """
        SELECT id, nama_satuan, isi_dalam_satuan_dasar, terkunci
        FROM satuan_barang
        WHERE barang_id = ?
        ORDER BY isi_dalam_satuan_dasar DESC;
        """,
        (barang_id,)
    )
    daftar_satuan = [dict(r) for r in cur.fetchall()]

    # Status Stok
    stok_saat_ini = info_barang["stok_saat_ini"]
    stok_min = info_barang["stok_minimum"]
    if stok_saat_ini <= 0:
        status_stok = "habis"
    elif stok_saat_ini <= stok_min:
        status_stok = "hampir habis"
    else:
        status_stok = "aman"

    stok_representasi = konversi_ke_satuan_besar(
        stok_saat_ini, info_barang["satuan_dasar"], daftar_satuan
    )

    # 3. Lot FIFO Aktif
    cur.execute(
        """
        SELECT l.id, l.asal, l.ref_id, l.tanggal_masuk, l.qty_awal, l.qty_sisa,
               l.total_biaya_awal, l.biaya_sisa, l.harga_jual_satuan_dasar,
               s.nama AS nama_supplier, p.nama AS nama_penitip,
               CASE WHEN l.qty_sisa > 0 THEN l.biaya_sisa / l.qty_sisa ELSE 0 END AS harga_beli_per_unit
        FROM lot_stok l
        LEFT JOIN supplier s ON l.supplier_id = s.id
        LEFT JOIN penitip p ON l.penitip_id = p.id
        WHERE l.barang_id = ? AND l.qty_sisa > 0
        ORDER BY l.tanggal_masuk ASC, l.id ASC;
        """,
        (barang_id,)
    )
    lot_aktif = [dict(r) for r in cur.fetchall()]

    nilai_persediaan = sum(lot["biaya_sisa"] for lot in lot_aktif)

    # Laba per satuan dari lot FIFO berikutnya
    hrg_jual_skrg = info_barang["harga_jual"]
    hpp_berikutnya = lot_aktif[0]["harga_beli_per_unit"] if lot_aktif else 0
    laba_per_satuan_berikutnya = hrg_jual_skrg - hpp_berikutnya

    # 4. Akumulasi Laba Penjualan (Hari ini, Minggu ini, Bulan ini, Tahun ini, Total)
    hari_ini = date.today().isoformat()
    tgl_dt = date.today()
    senin_minggu_ini = (tgl_dt - timedelta(days=tgl_dt.weekday())).isoformat()
    awal_bulan_ini = tgl_dt.strftime("%Y-%m-01")
    awal_tahun_ini = tgl_dt.strftime("%Y-01-01")

    q_laba = """
        SELECT 
            COALESCE(SUM(CASE WHEN pj.tanggal = ? THEN pb.total_baris ELSE 0 END), 0) AS jual_hari_ini,
            COALESCE(SUM(CASE WHEN pj.tanggal = ? THEN pb.laba ELSE 0 END), 0) AS laba_hari_ini,
            COALESCE(SUM(CASE WHEN pj.tanggal >= ? THEN pb.total_baris ELSE 0 END), 0) AS jual_minggu_ini,
            COALESCE(SUM(CASE WHEN pj.tanggal >= ? THEN pb.laba ELSE 0 END), 0) AS laba_minggu_ini,
            COALESCE(SUM(CASE WHEN pj.tanggal >= ? THEN pb.total_baris ELSE 0 END), 0) AS jual_bulan_ini,
            COALESCE(SUM(CASE WHEN pj.tanggal >= ? THEN pb.laba ELSE 0 END), 0) AS laba_bulan_ini,
            COALESCE(SUM(CASE WHEN pj.tanggal >= ? THEN pb.total_baris ELSE 0 END), 0) AS jual_tahun_ini,
            COALESCE(SUM(CASE WHEN pj.tanggal >= ? THEN pb.laba ELSE 0 END), 0) AS laba_tahun_ini,
            COALESCE(SUM(pb.total_baris), 0) AS jual_total,
            COALESCE(SUM(pb.laba), 0) AS laba_total
        FROM penjualan_baris pb
        JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id
        WHERE pb.barang_id = ? AND pj.status_efektif = 'NORMAL';
    """
    cur.execute(
        q_laba,
        (
            hari_ini, hari_ini,
            senin_minggu_ini, senin_minggu_ini,
            awal_bulan_ini, awal_bulan_ini,
            awal_tahun_ini, awal_tahun_ini,
            barang_id
        )
    )
    row_laba = cur.fetchone()
    akumulasi_laba = dict(row_laba) if row_laba else {}

    # 5. Riwayat Kartu Stok (Mutasi Stok Efektif)
    # Menghitung saldo berjalan dengan query window atau kalkulasi urut
    q_mutasi = """
        SELECT m.id, m.tanggal, m.jenis, m.qty, m.biaya, m.ref_tabel, m.ref_id, m.membalik_id,
               CASE 
                 WHEN m.ref_tabel = 'pembelian' THEN 'Faktur Beli #' || COALESCE((SELECT no_faktur FROM pembelian_faktur WHERE id = m.ref_id), m.ref_id)
                 WHEN m.ref_tabel = 'penjualan' THEN 'Nota Jual #' || COALESCE((SELECT no_nota FROM penjualan WHERE id = m.ref_id), m.ref_id)
                 WHEN m.ref_tabel = 'titipan' THEN 'Penitipan Barang'
                 WHEN m.ref_tabel = 'retur_supplier' THEN 'Retur ke Supplier'
                 WHEN m.ref_tabel = 'retur_penjualan' THEN 'Retur dari Pembeli'
                 WHEN m.ref_tabel = 'opname' THEN 'Penyesuaian Opname'
                 ELSE COALESCE(m.ref_tabel, '-')
               END AS keterangan_ref
        FROM v_mutasi_stok_efektif m
        WHERE m.barang_id = ? AND m.status_efektif = 'NORMAL'
    """
    params_mut: List[Any] = [barang_id]

    if filter_jenis != "semua":
        q_mutasi += " AND m.jenis = ?"
        params_mut.append(filter_jenis)
    if tgl_awal:
        q_mutasi += " AND m.tanggal >= ?"
        params_mut.append(tgl_awal)
    if tgl_akhir:
        q_mutasi += " AND m.tanggal <= ?"
        params_mut.append(tgl_akhir)

    q_mutasi += " ORDER BY m.tanggal ASC, m.id ASC;"
    cur.execute(q_mutasi, params_mut)
    semua_mutasi = [dict(r) for r in cur.fetchall()]

    # Kalkulasi saldo berjalan
    saldo_kumulatif = 0
    for item in semua_mutasi:
        saldo_kumulatif += item["qty"]
        item["saldo_berjalan"] = saldo_kumulatif
        item["masuk"] = item["qty"] if item["qty"] > 0 else 0
        item["keluar"] = abs(item["qty"]) if item["qty"] < 0 else 0

    # Paginasi daftar mutasi (tampilkan terbaru dulu)
    semua_mutasi_reverse = list(reversed(semua_mutasi))
    total_mutasi_count = len(semua_mutasi_reverse)
    mutasi_paginasi = semua_mutasi_reverse[offset : offset + limit]

    # 6. Supplier Terakhir, Harga Beli Terakhir, Pembeli Terbanyak
    cur.execute(
        """
        SELECT s.nama AS nama_supplier, pd.harga_per_satuan_input / pd.isi_per_satuan AS harga_beli_satuan_dasar, pf.tanggal
        FROM pembelian_detail pd
        JOIN pembelian_faktur pf ON pd.faktur_id = pf.id
        JOIN supplier s ON pf.supplier_id = s.id
        WHERE pd.barang_id = ?
        ORDER BY pf.tanggal DESC, pf.id DESC LIMIT 1;
        """,
        (barang_id,)
    )
    row_supp = cur.fetchone()
    supplier_terakhir = dict(row_supp) if row_supp else None

    cur.execute(
        """
        SELECT p.nama AS nama_pembeli, SUM(pb.jumlah_dasar) AS total_qty_beli
        FROM penjualan_baris pb
        JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id
        JOIN pembeli p ON pj.pembeli_id = p.id
        WHERE pb.barang_id = ? AND pj.status_efektif = 'NORMAL' AND p.nama != 'Umum'
        GROUP BY p.id
        ORDER BY total_qty_beli DESC LIMIT 1;
        """,
        (barang_id,)
    )
    row_pembeli = cur.fetchone()
    pembeli_terbanyak = dict(row_pembeli) if row_pembeli else None

    return {
        "info": info_barang,
        "satuan": daftar_satuan,
        "stok_saat_ini": stok_saat_ini,
        "status_stok": status_stok,
        "stok_representasi": stok_representasi,
        "nilai_persediaan": nilai_persediaan,
        "laba_per_satuan_berikutnya": laba_per_satuan_berikutnya,
        "lot_aktif": lot_aktif,
        "laba": akumulasi_laba,
        "riwayat_mutasi": mutasi_paginasi,
        "total_mutasi_count": total_mutasi_count,
        "supplier_terakhir": supplier_terakhir,
        "pembeli_terbanyak": pembeli_terbanyak
    }


def ambil_data_kartu_supplier(conn: sqlite3.Connection, supplier_id: int) -> Optional[Dict[str, Any]]:
    """Mengambil data lengkap untuk Kartu Supplier."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM supplier WHERE id = ?;", (supplier_id,))
    row_s = cur.fetchone()
    if not row_s:
        return None

    # Faktur belum lunas & riwayat pembelian
    cur.execute(
        """
        SELECT f.id, f.no_faktur, f.tanggal, f.total_biaya AS total, f.status_bayar,
               COALESCE((SELECT SUM(jumlah_bayar) FROM pembayaran_hutang_supplier WHERE faktur_id = f.id), 0) AS terbayar
        FROM v_pembelian_faktur_efektif f
        WHERE f.supplier_id = ? AND f.status_efektif = 'NORMAL'
        ORDER BY f.tanggal DESC, f.id DESC;
        """,
        (supplier_id,)
    )
    semua_faktur = []
    faktur_belum_lunas = []
    total_hutang_berjalan = 0

    for r in cur.fetchall():
        d = dict(r)
        d["sisa_hutang"] = max(0, d["total"] - d["terbayar"])
        semua_faktur.append(d)
        if d["status_bayar"] == "belum_dibayar" and d["sisa_hutang"] > 0:
            faktur_belum_lunas.append(d)
            total_hutang_berjalan += d["sisa_hutang"]

    # Riwayat Pembayaran ke Supplier
    cur.execute(
        """
        SELECT p.id, p.tanggal, p.jumlah_bayar AS jumlah, p.keterangan, f.no_faktur
        FROM pembayaran_hutang_supplier p
        JOIN pembelian_faktur f ON p.faktur_id = f.id
        WHERE f.supplier_id = ?
        ORDER BY p.tanggal DESC, p.id DESC;
        """,
        (supplier_id,)
    )
    riwayat_bayar = [dict(r) for r in cur.fetchall()]

    return {
        "supplier": dict(row_s),
        "total_hutang_berjalan": total_hutang_berjalan,
        "faktur_belum_lunas": faktur_belum_lunas,
        "riwayat_pembelian": semua_faktur,
        "riwayat_pembayaran": riwayat_bayar
    }


def ambil_data_kartu_penitip(conn: sqlite3.Connection, penitip_id: int) -> Optional[Dict[str, Any]]:
    """Mengambil data lengkap untuk Kartu Penitip."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM penitip WHERE id = ?;", (penitip_id,))
    row_p = cur.fetchone()
    if not row_p:
        return None

    # Daftar Barang yang Dititipkan
    cur.execute("SELECT id, kode, nama, satuan_dasar, stok_saat_ini, harga_jual FROM barang WHERE penitip_id = ?;", (penitip_id,))
    daftar_barang = [dict(r) for r in cur.fetchall()]

    # Hutang Penitip Hari Ini
    from app.db.repo_penitipan import hitung_total_hutang_penitip_terkini
    hutang_hari_ini = hitung_total_hutang_penitip_terkini(conn, penitip_id)

    # Riwayat Setoran / Pembayaran
    cur.execute(
        """
        SELECT id, tanggal, total_laku_terbayar, keterangan
        FROM v_pembayaran_penitip_efektif
        WHERE penitip_id = ? AND status_efektif = 'NORMAL'
        ORDER BY tanggal DESC, id DESC;
        """,
        (penitip_id,)
    )
    riwayat_setoran = [dict(r) for r in cur.fetchall()]

    # Total Laba Koperasi dari Penitip Ini
    cur.execute(
        """
        SELECT COALESCE(SUM(pb.laba), 0)
        FROM penjualan_baris pb
        JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id
        JOIN barang b ON pb.barang_id = b.id
        WHERE b.penitip_id = ? AND pj.status_efektif = 'NORMAL';
        """,
        (penitip_id,)
    )
    total_laba = cur.fetchone()[0]

    return {
        "penitip": dict(row_p),
        "daftar_barang": daftar_barang,
        "hutang_hari_ini": hutang_hari_ini,
        "riwayat_setoran": riwayat_setoran,
        "total_laba_koperasi": total_laba
    }


def ambil_data_kartu_pembeli(conn: sqlite3.Connection, pembeli_id: int) -> Optional[Dict[str, Any]]:
    """Mengambil data lengkap untuk Kartu Pembeli."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.*, a.nama AS nama_anggota, a.no_anggota
        FROM pembeli p
        LEFT JOIN anggota a ON p.anggota_id = a.id
        WHERE p.id = ?;
        """,
        (pembeli_id,)
    )
    row_pb = cur.fetchone()
    if not row_pb:
        return None

    # Nota Belum Lunas & Status Jatuh Tempo
    cur.execute(
        """
        SELECT pj.id, pj.no_nota, pj.tanggal, pj.total, pj.jatuh_tempo,
               COALESCE((SELECT SUM(jumlah) FROM alokasi_piutang WHERE penjualan_id = pj.id), 0) AS terbayar
        FROM v_penjualan_efektif pj
        WHERE pj.pembeli_id = ? AND pj.metode_bayar = 'kredit' AND pj.status_efektif = 'NORMAL'
        ORDER BY pj.tanggal ASC, pj.id ASC;
        """,
        (pembeli_id,)
    )
    tgl_ini = date.today().isoformat()
    nota_belum_lunas = []
    total_utang = 0
    ada_lewat_jatuh_tempo = False

    for r in cur.fetchall():
        d = dict(r)
        sisa = max(0, d["total"] - d["terbayar"])
        if sisa > 0:
            d["sisa_utang"] = sisa
            d["lewat_jatuh_tempo"] = bool(d["jatuh_tempo"] and d["jatuh_tempo"] < tgl_ini)
            if d["lewat_jatuh_tempo"]:
                ada_lewat_jatuh_tempo = True
            total_utang += sisa
            nota_belum_lunas.append(d)

    # Riwayat Pembelian (Semua Nota)
    cur.execute(
        """
        SELECT id, no_nota, tanggal, metode_bayar AS metode, total
        FROM v_penjualan_efektif
        WHERE pembeli_id = ? AND status_efektif = 'NORMAL'
        ORDER BY tanggal DESC, id DESC;
        """,
        (pembeli_id,)
    )
    riwayat_beli = [dict(r) for r in cur.fetchall()]

    # Riwayat Pembayaran Piutang
    cur.execute(
        """
        SELECT pp.id, pp.tanggal, pp.jumlah, pp.keterangan
        FROM v_pembayaran_piutang_efektif pp
        WHERE pp.pembeli_id = ? AND pp.status_efektif = 'NORMAL'
        ORDER BY pp.tanggal DESC, pp.id DESC;
        """,
        (pembeli_id,)
    )
    riwayat_bayar = [dict(r) for r in cur.fetchall()]

    # Barang yang Sering Dibeli
    cur.execute(
        """
        SELECT b.nama, SUM(pb.jumlah_dasar) AS total_qty, b.satuan_dasar
        FROM penjualan_baris pb
        JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id
        JOIN barang b ON pb.barang_id = b.id
        WHERE pj.pembeli_id = ? AND pj.status_efektif = 'NORMAL'
        GROUP BY b.id
        ORDER BY total_qty DESC LIMIT 5;
        """,
        (pembeli_id,)
    )
    barang_favorit = [dict(r) for r in cur.fetchall()]

    return {
        "pembeli": dict(row_pb),
        "total_utang": total_utang,
        "ada_lewat_jatuh_tempo": ada_lewat_jatuh_tempo,
        "nota_belum_lunas": nota_belum_lunas,
        "riwayat_pembelian": riwayat_beli,
        "riwayat_pembayaran": riwayat_bayar,
        "barang_favorit": barang_favorit
    }


def ambil_ringkasan_piutang_anggota(conn: sqlite3.Connection, anggota_id: int) -> Optional[Dict[str, Any]]:
    """
    Mengambil ringkasan piutang toko anggota untuk disematkan di Kartu Anggota SP.
    TERPISAH dari pinjaman SP dan tidak digabung ke saldo SP.
    """
    cur = conn.cursor()
    cur.execute("SELECT id, nama FROM pembeli WHERE anggota_id = ? AND aktif = 1;", (anggota_id,))
    row_p = cur.fetchone()
    if not row_p:
        return None

    pembeli_id = row_p["id"]
    from app.db.repo_piutang import ambil_daftar_nota_kredit_pembeli
    daftar_nota = ambil_daftar_nota_kredit_pembeli(conn, pembeli_id)

    total_utang = sum(n["sisa_piutang"] for n in daftar_nota if n["sisa_piutang"] > 0)
    jumlah_nota = sum(1 for n in daftar_nota if n["sisa_piutang"] > 0)
    tgl_ini = date.today().isoformat()
    ada_telat = any(n["jatuh_tempo"] and n["jatuh_tempo"] < tgl_ini for n in daftar_nota if n["sisa_piutang"] > 0)

    return {
        "pembeli_id": pembeli_id,
        "total_utang_toko": total_utang,
        "jumlah_nota_belum_lunas": jumlah_nota,
        "ada_lewat_jatuh_tempo": ada_telat
    }
