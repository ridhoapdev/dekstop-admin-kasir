"""
app/db/repo_laporan_toko.py — Sumber Kebenaran Tunggal Seluruh Laporan Unit Toko:
1. Rekapitulasi per Barang (stok awal dinamis dari SUM mutasi sebelum tgl awal, masuk, keluar, penyesuaian, stok akhir, penjualan, HPP, laba, margin)
2. Rincian Transaksi Toko (faktur, nota jual, retur, penerimaan titipan, alokasi FIFO, status bayar)
3. Ringkasan Keuangan Periode (penjualan tunai/kredit, HPP, laba kotor, rugi persediaan, arus kas toko, piutang, hutang supplier/penitip, nilai persediaan)
4. Laporan Tahunan Toko (tabel 12 bulan, perbandingan snapshot closing vs sementara, 10 barang terlaris & 10 barang laba tertinggi)
5. Laporan Analisis & Pendukung:
   - Stok hampir habis / di bawah minimum
   - Barang tidak bergerak / mati (> N hari tanpa penjualan)
   - Umur piutang pembeli & daftar hutang
"""
import sqlite3
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal


def ambil_rekap_per_barang_periode(
    conn: sqlite3.Connection,
    tgl_awal: str,
    tgl_akhir: str,
    barang_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    TAMPILAN 1: Rekap per Barang.
    Menghitung:
    - Stok Awal = SUM(qty) mutasi_stok efektif SEBELUM tgl_awal
    - Masuk = SUM(qty) mutasi masuk (pembelian, titipan, retur penjualan) dalam periode
    - Keluar = SUM(qty) mutasi keluar_jual dalam periode
    - Penyesuaian = SUM(qty) mutasi rusak, hilang, kedaluwarsa, opname, retur supplier
    - Stok Akhir = Stok Awal + Masuk - Keluar + Penyesuaian
    - Penjualan, HPP, Laba, Margin %
    """
    cur = conn.cursor()

    q_barang = "SELECT id, kode, nama, satuan_dasar, jenis_kepemilikan FROM barang WHERE aktif = 1"
    params_b: List[Any] = []
    if barang_id:
        q_barang += " AND id = ?"
        params_b.append(barang_id)
    q_barang += " ORDER BY nama ASC;"

    cur.execute(q_barang, params_b)
    daftar_barang = [dict(r) for r in cur.fetchall()]

    hasil = []
    for b in daftar_barang:
        bid = b["id"]

        # 1. Stok Awal (SUM mutasi sebelum tgl_awal)
        cur.execute(
            """
            SELECT COALESCE(SUM(qty), 0)
            FROM v_mutasi_stok_efektif
            WHERE barang_id = ? AND tanggal < ? AND status_efektif = 'NORMAL';
            """,
            (bid, tgl_awal)
        )
        stok_awal = cur.fetchone()[0]

        # 2. Mutasi Masuk dalam rentang periode
        cur.execute(
            """
            SELECT COALESCE(SUM(qty), 0)
            FROM v_mutasi_stok_efektif
            WHERE barang_id = ? AND tanggal BETWEEN ? AND ? 
              AND status_efektif = 'NORMAL' AND jenis = 'masuk';
            """,
            (bid, tgl_awal, tgl_akhir)
        )
        masuk = cur.fetchone()[0]

        # 3. Mutasi Keluar Jual dalam rentang periode
        cur.execute(
            """
            SELECT COALESCE(SUM(ABS(qty)), 0)
            FROM v_mutasi_stok_efektif
            WHERE barang_id = ? AND tanggal BETWEEN ? AND ? 
              AND status_efektif = 'NORMAL' AND jenis = 'keluar_jual';
            """,
            (bid, tgl_awal, tgl_akhir)
        )
        keluar = cur.fetchone()[0]

        # 4. Mutasi Penyesuaian & Retur Lainnya
        cur.execute(
            """
            SELECT COALESCE(SUM(qty), 0)
            FROM v_mutasi_stok_efektif
            WHERE barang_id = ? AND tanggal BETWEEN ? AND ? 
              AND status_efektif = 'NORMAL' AND jenis NOT IN ('masuk', 'keluar_jual');
            """,
            (bid, tgl_awal, tgl_akhir)
        )
        penyesuaian = cur.fetchone()[0]

        # Stok Akhir periode
        stok_akhir = stok_awal + masuk - keluar + penyesuaian

        # 5. Penjualan, HPP, dan Laba dari penjualan_baris efektif
        cur.execute(
            """
            SELECT 
                COALESCE(SUM(pb.total_baris), 0) AS total_penjualan,
                COALESCE(SUM(pb.hpp_total), 0) AS total_hpp,
                COALESCE(SUM(pb.laba), 0) AS total_laba
            FROM penjualan_baris pb
            JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id
            WHERE pb.barang_id = ? AND pj.tanggal BETWEEN ? AND ? AND pj.status_efektif = 'NORMAL';
            """,
            (bid, tgl_awal, tgl_akhir)
        )
        row_penj = cur.fetchone()
        tot_jual = row_penj["total_penjualan"]
        tot_hpp = row_penj["total_hpp"]
        tot_laba = row_penj["total_laba"]

        margin_persen = Decimal("0.00")
        if tot_jual > 0:
            margin_persen = (Decimal(tot_laba) / Decimal(tot_jual) * 100).quantize(Decimal("0.01"))

        hasil.append({
            "barang_id": bid,
            "kode": b["kode"],
            "nama": b["nama"],
            "satuan_dasar": b["satuan_dasar"],
            "jenis_kepemilikan": b["jenis_kepemilikan"],
            "stok_awal": stok_awal,
            "masuk": masuk,
            "keluar": keluar,
            "penyesuaian": penyesuaian,
            "stok_akhir": stok_akhir,
            "total_penjualan": tot_jual,
            "total_hpp": tot_hpp,
            "laba": tot_laba,
            "margin_persen": float(margin_persen)
        })

    return hasil


def ambil_rincian_transaksi_toko(
    conn: sqlite3.Connection,
    tgl_awal: str,
    tgl_akhir: str,
    filter_barang_id: Optional[int] = None,
    filter_pembeli_id: Optional[int] = None,
    filter_supplier_id: Optional[int] = None,
    filter_penitip_id: Optional[int] = None,
    filter_metode: Optional[str] = None,  # 'tunai' atau 'kredit'
    sembunyikan_batal: bool = True
) -> List[Dict[str, Any]]:
    """
    TAMPILAN 2: Rincian Transaksi Toko.
    Menampilkan per baris transaksi penjualan dan retur yang transparan.
    """
    cur = conn.cursor()
    query = """
        SELECT 
            pj.tanggal,
            pj.no_nota,
            COALESCE(p.nama, 'Umum') AS nama_pembeli,
            b.nama AS nama_barang,
            pb.jumlah_input,
            pb.satuan_input,
            pb.jumlah_dasar,
            b.satuan_dasar,
            (pb.hpp_total / pb.jumlah_dasar) AS hpp_satuan_dasar,
            pb.harga_jual_satuan_dasar,
            pb.total_baris,
            pb.hpp_total,
            pb.laba,
            pj.metode_bayar AS metode,
            pj.status_efektif,
            CASE 
              WHEN b.jenis_kepemilikan = 'titipan' THEN pen.nama
              ELSE COALESCE(s.nama, 'Koperasi')
            END AS pihak_asal
        FROM penjualan_baris pb
        JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id
        JOIN barang b ON pb.barang_id = b.id
        LEFT JOIN pembeli p ON pj.pembeli_id = p.id
        LEFT JOIN penitip pen ON b.penitip_id = pen.id
        LEFT JOIN lot_stok l ON (SELECT lot_id FROM penjualan_lot WHERE penjualan_baris_id = pb.id LIMIT 1) = l.id
        LEFT JOIN supplier s ON l.supplier_id = s.id
        WHERE pj.tanggal BETWEEN ? AND ?
    """
    params: List[Any] = [tgl_awal, tgl_akhir]

    if sembunyikan_batal:
        query += " AND pj.status_efektif = 'NORMAL'"
    if filter_barang_id:
        query += " AND pb.barang_id = ?"
        params.append(filter_barang_id)
    if filter_pembeli_id:
        query += " AND pj.pembeli_id = ?"
        params.append(filter_pembeli_id)
    if filter_penitip_id:
        query += " AND b.penitip_id = ?"
        params.append(filter_penitip_id)
    if filter_metode in ("tunai", "kredit"):
        query += " AND pj.metode_bayar = ?"
        params.append(filter_metode)

    query += " ORDER BY pj.tanggal DESC, pj.id DESC;"
    cur.execute(query, params)
    return [dict(r) for r in cur.fetchall()]


def hitung_ringkasan_keuangan_toko(
    conn: sqlite3.Connection,
    tgl_awal: str,
    tgl_akhir: str
) -> Dict[str, Any]:
    """
    Ringkasan keuangan bersih toko untuk header laporan dan closing:
    - Penjualan tunai & kredit
    - Total HPP & Laba kotor
    - Kerugian persediaan (rusak, hilang, kedaluwarsa, opname kurang)
    - Kas toko: saldo awal, masuk, keluar, saldo akhir
    - Piutang awal & akhir
    - Hutang supplier akhir
    - Hutang penitip akhir
    - Nilai persediaan akhir
    - Setoran penitip periode ini
    """
    cur = conn.cursor()

    # 1. Penjualan Tunai vs Kredit & HPP & Laba
    cur.execute(
        """
        SELECT 
            COALESCE(SUM(CASE WHEN metode_bayar = 'tunai' THEN total ELSE 0 END), 0) AS total_tunai,
            COALESCE(SUM(CASE WHEN metode_bayar = 'kredit' THEN total ELSE 0 END), 0) AS total_kredit,
            COALESCE(SUM(total), 0) AS total_penjualan
        FROM v_penjualan_efektif
        WHERE tanggal BETWEEN ? AND ? AND status_efektif = 'NORMAL';
        """,
        (tgl_awal, tgl_akhir)
    )
    r_pj = cur.fetchone()
    tot_tunai = r_pj["total_tunai"]
    tot_kredit = r_pj["total_kredit"]
    tot_penjualan = r_pj["total_penjualan"]

    cur.execute(
        """
        SELECT 
            COALESCE(SUM(pb.hpp_total), 0) AS total_hpp,
            COALESCE(SUM(pb.laba), 0) AS total_laba
        FROM penjualan_baris pb
        JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id
        WHERE pj.tanggal BETWEEN ? AND ? AND pj.status_efektif = 'NORMAL';
        """,
        (tgl_awal, tgl_akhir)
    )
    r_hpp = cur.fetchone()
    tot_hpp = r_hpp["total_hpp"]
    laba_kotor = r_hpp["total_laba"]

    # 2. Kerugian Persediaan (rusak, hilang, kedaluwarsa, opname selisih kurang)
    cur.execute(
        """
        SELECT COALESCE(SUM(biaya), 0)
        FROM v_mutasi_stok_efektif
        WHERE tanggal BETWEEN ? AND ? AND status_efektif = 'NORMAL'
          AND jenis IN ('rusak', 'hilang', 'kedaluwarsa', 'penyesuaian_opname') AND qty < 0;
        """,
        (tgl_awal, tgl_akhir)
    )
    rugi_persediaan = cur.fetchone()[0]

    # 3. Arus Kas Toko (Saldo Awal, Masuk, Keluar, Saldo Akhir)
    cur.execute(
        """
        SELECT COALESCE(SUM(masuk - keluar), 0)
        FROM v_kas_toko_efektif
        WHERE tanggal < ? AND status_efektif = 'NORMAL';
        """,
        (tgl_awal,)
    )
    kas_awal = cur.fetchone()[0]

    cur.execute(
        """
        SELECT 
            COALESCE(SUM(masuk), 0) AS total_masuk,
            COALESCE(SUM(keluar), 0) AS total_keluar
        FROM v_kas_toko_efektif
        WHERE tanggal BETWEEN ? AND ? AND status_efektif = 'NORMAL';
        """,
        (tgl_awal, tgl_akhir)
    )
    r_kas = cur.fetchone()
    kas_masuk = r_kas["total_masuk"]
    kas_keluar = r_kas["total_keluar"]
    kas_akhir = kas_awal + kas_masuk - kas_keluar

    # 4. Nilai Persediaan Akhir (dari lot_stok aktif per tgl_akhir)
    cur.execute("SELECT COALESCE(SUM(biaya_sisa), 0) FROM lot_stok WHERE qty_sisa > 0;")
    nilai_persediaan_akhir = cur.fetchone()[0]

    # 5. Total Piutang Pembeli Terkini
    from app.db.repo_piutang import hitung_total_piutang_semua_pembeli
    total_piutang_akhir = hitung_total_piutang_semua_pembeli(conn)

    # 6. Total Hutang ke Supplier Terkini
    cur.execute(
        """
        SELECT COALESCE(SUM(
            f.total_biaya - COALESCE((SELECT SUM(jumlah_bayar) FROM pembayaran_hutang_supplier WHERE faktur_id = f.id), 0)
        ), 0)
        FROM v_pembelian_faktur_efektif f
        WHERE f.status_bayar = 'belum_dibayar' AND f.status_efektif = 'NORMAL';
        """
    )
    total_hutang_supplier_akhir = cur.fetchone()[0]

    # 7. Total Hutang ke Penitip Terkini
    from app.db.repo_penitipan import hitung_total_hutang_penitip_terkini
    total_hutang_penitip_akhir = hitung_total_hutang_penitip_terkini(conn)

    # 8. Setoran Penitip Periode Ini
    cur.execute(
        """
        SELECT COALESCE(SUM(total_laku_terbayar), 0)
        FROM v_pembayaran_penitip_efektif
        WHERE tanggal BETWEEN ? AND ? AND status_efektif = 'NORMAL';
        """,
        (tgl_awal, tgl_akhir)
    )
    setoran_penitip_periode = cur.fetchone()[0]

    return {
        "tgl_awal": tgl_awal,
        "tgl_akhir": tgl_akhir,
        "penjualan_tunai": tot_tunai,
        "penjualan_kredit": tot_kredit,
        "total_penjualan": tot_penjualan,
        "total_hpp": tot_hpp,
        "laba_kotor": laba_kotor,
        "kerugian_persediaan": rugi_persediaan,
        "laba_bersih_operasional": laba_kotor - rugi_persediaan,
        "kas_toko_awal": kas_awal,
        "kas_toko_masuk": kas_masuk,
        "kas_toko_keluar": kas_keluar,
        "kas_toko_akhir": kas_akhir,
        "total_piutang": total_piutang_akhir,
        "total_hutang_supplier": total_hutang_supplier_akhir,
        "total_hutang_penitip": total_hutang_penitip_akhir,
        "nilai_persediaan": nilai_persediaan_akhir,
        "setoran_penitip_periode": setoran_penitip_periode
    }


def ambil_laporan_tahunan_toko(conn: sqlite3.Connection, tahun: int) -> Dict[str, Any]:
    """
    Laporan Tahunan Toko:
    - Rangkaian 12 Bulan (Januari s.d. Desember)
    - Jika bulan sudah di-closing, ambil angka dari snapshot `closing_toko`
    - Jika belum closing, hitung real-time dan beri label 'SEMENTARA'
    - 10 Barang Terlaris & 10 Barang Laba Terbesar
    """
    cur = conn.cursor()
    daftar_bulan = []

    total_tahun = {
        "penjualan": 0, "hpp": 0, "laba": 0, "kas_masuk": 0,
        "kas_keluar": 0, "kerugian_persediaan": 0
    }

    import calendar
    for bln in range(1, 13):
        periode_str = f"{tahun:04d}-{bln:02d}"
        nama_bulan = calendar.month_name[bln]
        maks_hari = calendar.monthrange(tahun, bln)[1]
        tgl_awal_bln = f"{periode_str}-01"
        tgl_akhir_bln = f"{periode_str}-{maks_hari:02d}"

        # Periksa apakah sudah ada closing resmi
        cur.execute("SELECT * FROM closing_toko WHERE periode = ? AND status = 'closed';", (periode_str,))
        row_c = cur.fetchone()

        if row_c:
            item_bln = {
                "periode": periode_str,
                "nama_bulan": nama_bulan,
                "status": "FINAL (Closing)",
                "penjualan": row_c["total_penjualan"],
                "hpp": row_c["total_hpp"],
                "laba": row_c["laba_kotor"],
                "kerugian_persediaan": row_c["kerugian_persediaan"],
                "kas_akhir": row_c["kas_toko_akhir"],
                "nilai_persediaan": row_c["nilai_persediaan"],
                "piutang_akhir": row_c["total_piutang"],
                "is_closing": True
            }
        else:
            ringk = hitung_ringkasan_keuangan_toko(conn, tgl_awal_bln, tgl_akhir_bln)
            item_bln = {
                "periode": periode_str,
                "nama_bulan": nama_bulan,
                "status": "SEMENTARA",
                "penjualan": ringk["total_penjualan"],
                "hpp": ringk["total_hpp"],
                "laba": ringk["laba_kotor"],
                "kerugian_persediaan": ringk["kerugian_persediaan"],
                "kas_akhir": ringk["kas_toko_akhir"],
                "nilai_persediaan": ringk["nilai_persediaan"],
                "piutang_akhir": ringk["total_piutang"],
                "is_closing": False
            }

        daftar_bulan.append(item_bln)
        total_tahun["penjualan"] += item_bln["penjualan"]
        total_tahun["hpp"] += item_bln["hpp"]
        total_tahun["laba"] += item_bln["laba"]
        total_tahun["kerugian_persediaan"] += item_bln["kerugian_persediaan"]

    # 10 Barang Terlaris (Qty)
    tgl_awal_thn = f"{tahun:04d}-01-01"
    tgl_akhir_thn = f"{tahun:04d}-12-31"
    cur.execute(
        """
        SELECT b.nama, SUM(pb.jumlah_dasar) AS total_qty, b.satuan_dasar, SUM(pb.total_baris) AS total_rupiah
        FROM penjualan_baris pb
        JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id
        JOIN barang b ON pb.barang_id = b.id
        WHERE pj.tanggal BETWEEN ? AND ? AND pj.status_efektif = 'NORMAL'
        GROUP BY b.id
        ORDER BY total_qty DESC LIMIT 10;
        """,
        (tgl_awal_thn, tgl_akhir_thn)
    )
    terlaris = [dict(r) for r in cur.fetchall()]

    # 10 Barang Laba Terbesar (Rupiah)
    cur.execute(
        """
        SELECT b.nama, SUM(pb.laba) AS total_laba, SUM(pb.total_baris) AS total_rupiah
        FROM penjualan_baris pb
        JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id
        JOIN barang b ON pb.barang_id = b.id
        WHERE pj.tanggal BETWEEN ? AND ? AND pj.status_efektif = 'NORMAL'
        GROUP BY b.id
        ORDER BY total_laba DESC LIMIT 10;
        """,
        (tgl_awal_thn, tgl_akhir_thn)
    )
    laba_terbesar = [dict(r) for r in cur.fetchall()]

    return {
        "tahun": tahun,
        "daftar_bulan": daftar_bulan,
        "total_tahun": total_tahun,
        "terlaris": terlaris,
        "laba_terbesar": laba_terbesar
    }


def ambil_laporan_barang_tidak_bergerak(conn: sqlite3.Connection, hari_ambang: int = 30) -> List[Dict[str, Any]]:
    """Mencari barang yang memiliki stok > 0 tetapi tidak pernah terjual dalam N hari terakhir."""
    cur = conn.cursor()
    tgl_batas = (date.today() - timedelta(days=hari_ambang)).isoformat()
    cur.execute(
        """
        SELECT b.id, b.kode, b.nama, b.stok_saat_ini, b.satuan_dasar, b.harga_jual,
               COALESCE((SELECT MAX(pj.tanggal) FROM penjualan_baris pb 
                         JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id 
                         WHERE pb.barang_id = b.id AND pj.status_efektif = 'NORMAL'), 'Belum pernah') AS transaksi_terakhir
        FROM barang b
        WHERE b.aktif = 1 AND b.stok_saat_ini > 0
          AND b.id NOT IN (
              SELECT DISTINCT pb.barang_id 
              FROM penjualan_baris pb
              JOIN v_penjualan_efektif pj ON pb.penjualan_id = pj.id
              WHERE pj.tanggal >= ? AND pj.status_efektif = 'NORMAL'
          )
        ORDER BY b.stok_saat_ini DESC;
        """,
        (tgl_batas,)
    )
    return [dict(r) for r in cur.fetchall()]


def ambil_laporan_stok_menipis(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Mencari barang yang stok_saat_ini <= stok_minimum."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, kode, nama, stok_saat_ini, stok_minimum, satuan_dasar, harga_jual
        FROM barang
        WHERE aktif = 1 AND stok_saat_ini <= stok_minimum
        ORDER BY stok_saat_ini ASC;
        """
    )
    return [dict(r) for r in cur.fetchall()]
