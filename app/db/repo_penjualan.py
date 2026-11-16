"""
app/db/repo_penjualan.py — Repositori Penjualan Toko (Layar Kasir Cepat) & Pembalik Nota.
Aturan Bisnis:
- Penjualan dicatat satu per satu per pembeli (nota dengan banyak baris).
- Metode bayar: 'tunai' atau 'kredit'.
- Penjualan kredit mewajibkan pembeli terdaftar (bukan 'Umum').
- Jatuh tempo kredit diatur otomatis (default 1 bulan sejak tanggal nota, dapat diatur di tabel pengaturan).
- Pengurangan stok FIFO real-time menggunakan layanan_stok (kurangi_stok_fifo) dalam SATU transaksi database atomik:
  * Pembentukan nota (penjualan, penjualan_baris, penjualan_lot).
  * Pemotongan stok & mutasi mutasi_stok jenis='keluar_jual'.
  * Pencatatan kas_toko masuk jika tunai (kredit tidak menulis kas, melainkan membentuk piutang).
  * Catat hutang penitip jika ada lot titipan yang laku.
- Nomor nota otomatis dengan format dinamis (misal: NT-YYYYMMDD-0001).
- Pembalik / pembatalan nota:
  * Mengembalikan stok ke lot ASAL dengan biaya yang sama (dari data penjualan_lot).
  * Membalik arus kas toko jika tunai.
  * Menolak pembatalan jika nota kredit sudah pernah dibayar sebagian/lunas (diarahkan ke penyesuaian/retur).
"""
import sqlite3
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from app.db.repo_simpanan import cek_periode_terkunci
from app.layanan.layanan_stok import kurangi_stok_fifo, ambil_stok_barang
from app.db.repo_kas_toko import tambah_kas_toko
from app.layanan.bus_sinyal import kirim_sinyal


def ambil_konfigurasi_toko(conn: sqlite3.Connection, kunci: str, default: str = "") -> str:
    """Mengambil konfigurasi toko dari tabel pengaturan."""
    cur = conn.cursor()
    cur.execute("SELECT nilai FROM pengaturan WHERE kunci = ?;", (kunci,))
    row = cur.fetchone()
    return row[0] if row else default


def hitung_jatuh_tempo_kredit(conn: sqlite3.Connection, tanggal_nota: str) -> str:
    """Menghitung tanggal jatuh tempo kredit (default +1 bulan)."""
    try:
        bulan_offset = int(ambil_konfigurasi_toko(conn, "jatuh_tempo_kredit_bulan", "1"))
    except ValueError:
        bulan_offset = 1

    tgl = datetime.strptime(tanggal_nota[:10], "%Y-%m-%d")
    # Tambah n bulan
    thn = tgl.year + (tgl.month + bulan_offset - 1) // 12
    bln = (tgl.month + bulan_offset - 1) % 12 + 1
    # Handle tanggal akhir bulan (misal 31 Jan -> 28 Feb)
    import calendar
    maks_hari = calendar.monthrange(thn, bln)[1]
    hari = min(tgl.day, maks_hari)
    return date(thn, bln, hari).isoformat()


def buat_nomor_nota_baru(conn: sqlite3.Connection, tanggal: str) -> str:
    """Menghasilkan nomor nota otomatis berurutan per hari: NT-YYYYMMDD-0001."""
    format_tpl = ambil_konfigurasi_toko(conn, "format_no_nota", "NT-{YYYY}{MM}{DD}-{NO}")
    tgl_dt = datetime.strptime(tanggal[:10], "%Y-%m-%d")
    tgl_str = tgl_dt.strftime("%Y%m%d")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM penjualan WHERE tanggal = ?;", (tanggal,))
    urutan = cur.fetchone()[0] + 1

    hasil = format_tpl.replace("{YYYY}", str(tgl_dt.year))
    hasil = hasil.replace("{MM}", f"{tgl_dt.month:02d}")
    hasil = hasil.replace("{DD}", f"{tgl_dt.day:02d}")
    hasil = hasil.replace("{NO}", f"{urutan:04d}")
    return hasil


def ambil_harga_jual_default_barang(conn: sqlite3.Connection, barang_id: int) -> int:
    """
    Mengambil harga jual default:
    - Untuk barang koperasi: harga_jual dari tabel barang.
    - Untuk barang titipan: harga_jual dari lot FIFO teraktif yang akan terpakai.
    """
    cur = conn.cursor()
    cur.execute("SELECT jenis_kepemilikan, harga_jual FROM barang WHERE id = ?;", (barang_id,))
    row_b = cur.fetchone()
    if not row_b:
        return 0

    jenis_kep, hrg_def = row_b[0], row_b[1]
    if jenis_kep == "titipan":
        cur.execute(
            """
            SELECT harga_jual_satuan_dasar
            FROM lot_stok
            WHERE barang_id = ? AND qty_sisa > 0
            ORDER BY tanggal_masuk ASC, id ASC LIMIT 1;
            """,
            (barang_id,)
        )
        row_lot = cur.fetchone()
        if row_lot and row_lot[0] > 0:
            return row_lot[0]

    return hrg_def


def simpan_penjualan(
    conn: sqlite3.Connection,
    tanggal: str,
    pembeli_id: int,
    metode_bayar: str,  # 'tunai' atau 'kredit'
    items: List[Dict[str, Any]],
    no_nota: Optional[str] = None,
    nama_pembeli_nota: Optional[str] = None,
    keterangan: Optional[str] = None
) -> Tuple[int, str]:
    """
    Menyimpan transaksi kasir penjualan secara ATOMIK:
    items: [
        {
            "barang_id": int,
            "jumlah_input": int,
            "satuan_input": str,
            "isi_per_satuan": int,
            "harga_jual_satuan_dasar": int
        }, ...
    ]
    Proses:
    1. Validasi input dan pembeli kredit (bukan 'Umum').
    2. Kurangi stok FIFO real-time per barang, dapatkan alokasi lot dan HPP.
    3. Simpan penjualan, penjualan_baris, dan penjualan_lot.
    4. Jika tunai: catat kas_toko_transaksi (masuk, sumber='penjualan').
    5. Jika kredit: tentukan jatuh tempo dan buat record penjualan kredit (piutang).
    Gagal satu = batal semua (transaksi database).
    Mengembalikan (penjualan_id, no_nota).
    """
    if not items:
        raise ValueError("Keranjang belanja kosong. Masukkan minimal 1 barang.")
    if metode_bayar not in ("tunai", "kredit"):
        raise ValueError("Metode bayar harus 'tunai' atau 'kredit'.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Penjualan tidak dapat disimpan.")

    cur = conn.cursor()
    # Cek pembeli
    cur.execute("SELECT id, nama FROM pembeli WHERE id = ?;", (pembeli_id,))
    row_pem = cur.fetchone()
    if not row_pem:
        raise ValueError("Pembeli tidak ditemukan.")

    nama_pembeli = row_pem[1]
    if metode_bayar == "kredit" and nama_pembeli.strip().lower() == "umum":
        raise ValueError("Penjualan KREDIT (ngutang) mewajibkan memilih pembeli bernama (bukan 'Umum').")

    if not no_nota:
        no_nota = buat_nomor_nota_baru(conn, tanggal)

    # Hitung jatuh tempo jika kredit
    jatuh_tempo = hitung_jatuh_tempo_kredit(conn, tanggal) if metode_bayar == "kredit" else None

    with conn:
        # 1. Simpan header penjualan
        cur_pj = conn.execute(
            """
            INSERT INTO penjualan (
                no_nota, tanggal, pembeli_id, nama_pembeli_nota,
                metode_bayar, total, jatuh_tempo, status, keterangan, periode
            ) VALUES (?, ?, ?, ?, ?, 0, ?, 'selesai', ?, ?);
            """,
            (
                no_nota, tanggal, pembeli_id,
                nama_pembeli_nota.strip() if nama_pembeli_nota else None,
                metode_bayar, jatuh_tempo,
                keterangan.strip() if keterangan else None, periode
            )
        )
        penjualan_id = cur_pj.lastrowid

        total_nota = 0

        # 2. Proses tiap baris barang
        for it in items:
            b_id = int(it["barang_id"])
            jml_input = int(it["jumlah_input"])
            sat_input = str(it["satuan_input"]).strip()
            isi_per_satuan = int(it["isi_per_satuan"])
            hrg_jual_satuan = int(it["harga_jual_satuan_dasar"])

            if jml_input <= 0 or isi_per_satuan <= 0:
                raise ValueError(f"Jumlah dan konversi barang ID {b_id} harus > 0.")
            if hrg_jual_satuan < 0:
                raise ValueError(f"Harga jual barang ID {b_id} tidak boleh negatif.")

            jml_dasar = jml_input * isi_per_satuan
            subtotal_baris = jml_dasar * hrg_jual_satuan
            total_nota += subtotal_baris

            # Eksekusi pengurangan stok FIFO real-time via modul 13
            mutasi_fifo = kurangi_stok_fifo(
                conn=conn,
                barang_id=b_id,
                qty_diminta=jml_dasar,
                jenis_mutasi="keluar_jual",
                ref_tabel="penjualan_baris",
                ref_id=0,  # di-update setelah insert
                tanggal=tanggal
            )

            # Hitung HPP total dari alokasi lot
            hpp_total = sum(m["biaya"] for m in mutasi_fifo)
            laba_baris = subtotal_baris - hpp_total

            # Insert penjualan_baris
            cur_pb = conn.execute(
                """
                INSERT INTO penjualan_baris (
                    penjualan_id, barang_id, jumlah_input, satuan_input,
                    isi_per_satuan, jumlah_dasar, harga_jual_satuan_dasar,
                    total_baris, hpp_total, laba
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    penjualan_id, b_id, jml_input, sat_input,
                    isi_per_satuan, jml_dasar, hrg_jual_satuan,
                    subtotal_baris, hpp_total, laba_baris
                )
            )
            baris_id = cur_pb.lastrowid

            # Update ref_id mutasi_stok
            for m in mutasi_fifo:
                conn.execute(
                    "UPDATE mutasi_stok SET ref_id = ? WHERE id = ?;",
                    (baris_id, m["mutasi_id"])
                )
                # Simpan ke penjualan_lot untuk presisi pembalik & audit hutang penitip
                conn.execute(
                    """
                    INSERT INTO penjualan_lot (penjualan_baris_id, lot_id, qty, biaya, penitip_id)
                    VALUES (?, ?, ?, ?, ?);
                    """,
                    (baris_id, m["lot_id"], m["qty"], m["biaya"], m.get("penitip_id"))
                )

        # 3. Update total penjualan
        conn.execute("UPDATE penjualan SET total = ? WHERE id = ?;", (total_nota, penjualan_id))

        # 4. Arus Kas Toko jika Tunai
        if metode_bayar == "tunai" and total_nota > 0:
            tambah_kas_toko(
                conn=conn,
                tanggal=tanggal,
                keterangan=f"Penjualan tunai nota {no_nota} ({nama_pembeli})",
                masuk=total_nota,
                keluar=0,
                sumber="penjualan",
                ref_tabel="penjualan",
                ref_id=penjualan_id
            )

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "penjualan", penjualan_id, f"Nota {no_nota} ({metode_bayar.upper()}) Rp {total_nota:,}".replace(",", "."))
        )

    kirim_sinyal("penjualan_berubah")
    kirim_sinyal("stok_berubah")
    if metode_bayar == "kredit":
        kirim_sinyal("piutang_berubah")

    return penjualan_id, no_nota


def batalkan_nota_penjualan(
    conn: sqlite3.Connection,
    penjualan_id: int,
    tanggal_balik: str,
    keterangan: str = "Pembatalan nota penjualan"
) -> int:
    """
    Membatalkan nota penjualan secara bersih (transaksi pembalik):
    - Jika nota kredit sudah memiliki alokasi pembayaran piutang: TOLAK dengan pesan jelas!
    - Mengembalikan kuantitas dan biaya ke LOT ASAL (dari penjualan_lot).
    - Membalik mutasi_stok jenis='koreksi'.
    - Mengembalikan kas toko jika penjualan tunai.
    - Mencatat record pembalik di tabel penjualan.
    """
    periode_balik = tanggal_balik[:7]
    if cek_periode_terkunci(conn, periode_balik):
        raise ValueError(f"Periode {periode_balik} sudah ditutup (closing). Pembatalan tidak dapat diproses.")

    cur = conn.cursor()
    cur.execute("SELECT * FROM penjualan WHERE id = ?;", (penjualan_id,))
    row_pj = cur.fetchone()
    if not row_pj:
        raise ValueError("Nota penjualan tidak ditemukan.")

    pj = dict(row_pj)
    if pj["membalik_id"] is not None:
        raise ValueError("Nota ini adalah nota pembalik dan tidak dapat dibatalkan lagi.")

    cur.execute("SELECT id FROM penjualan WHERE membalik_id = ?;", (penjualan_id,))
    if cur.fetchone():
        raise ValueError("Nota penjualan ini sudah pernah dibatalkan sebelumnya.")

    # Cek apakah nota kredit ini sudah pernah dibayar sebagian/lunas
    if pj["metode_bayar"] == "kredit":
        cur.execute(
            """
            SELECT COALESCE(SUM(jumlah), 0)
            FROM alokasi_piutang
            WHERE penjualan_id = ? AND membalik_id IS NULL;
            """,
            (penjualan_id,)
        )
        total_dibayar = cur.fetchone()[0]
        if total_dibayar > 0:
            raise ValueError(
                f"Nota kredit {pj['no_nota']} sudah memiliki pembayaran piutang (sebesar Rp {total_dibayar:,}). "
                "Batalkan terlebih dahulu pembayaran piutang terkait sebelum membatalkan nota ini."
            )

    with conn:
        # 1. Ambil seluruh penjualan_baris dan penjualan_lot
        cur.execute("SELECT id, barang_id FROM penjualan_baris WHERE penjualan_id = ?;", (penjualan_id,))
        baris_list = [dict(r) for r in cur.fetchall()]

        for b in baris_list:
            cur.execute("SELECT lot_id, qty, biaya FROM penjualan_lot WHERE penjualan_baris_id = ?;", (b["id"],))
            lot_records = [dict(r) for r in cur.fetchall()]
            for lr in lot_records:
                lot_id = lr["lot_id"]
                qty = lr["qty"]
                biaya = lr["biaya"]

                # Kembalikan ke lot asal
                if lot_id:
                    conn.execute(
                        "UPDATE lot_stok SET qty_sisa = qty_sisa + ?, biaya_sisa = biaya_sisa + ? WHERE id = ?;",
                        (qty, biaya, lot_id)
                    )

                # Catat mutasi koreksi penambah stok
                conn.execute(
                    """
                    INSERT INTO mutasi_stok (
                        barang_id, lot_id, tanggal, jenis, qty, biaya,
                        ref_tabel, ref_id, membalik_id, periode
                    ) VALUES (?, ?, ?, 'koreksi', ?, ?, 'penjualan', ?, NULL, ?);
                    """,
                    (b["barang_id"], lot_id, tanggal_balik, qty, biaya, penjualan_id, periode_balik)
                )

                # Tambah cache stok barang
                conn.execute(
                    "UPDATE barang SET stok_saat_ini = stok_saat_ini + ? WHERE id = ?;",
                    (qty, b["barang_id"])
                )

        # 2. Balik kas jika tunai
        if pj["metode_bayar"] == "tunai" and pj["total"] > 0:
            tambah_kas_toko(
                conn=conn,
                tanggal=tanggal_balik,
                keterangan=f"[PEMBALIK #{penjualan_id}] Pembatalan penjualan nota {pj['no_nota']}",
                masuk=0,
                keluar=pj["total"],
                sumber="penjualan",
                ref_tabel="penjualan",
                ref_id=penjualan_id
            )

        # 3. Catat record pembalik penjualan
        cur_pf = conn.execute(
            """
            INSERT INTO penjualan (
                no_nota, tanggal, pembeli_id, nama_pembeli_nota,
                metode_bayar, total, jatuh_tempo, status, keterangan,
                membalik_id, periode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'dibatalkan', ?, ?, ?);
            """,
            (
                f"PEMBALIK-{pj['no_nota']}", tanggal_balik, pj["pembeli_id"],
                pj["nama_pembeli_nota"], pj["metode_bayar"], -pj["total"],
                pj["jatuh_tempo"], f"[PEMBALIK #{penjualan_id}] {keterangan}",
                penjualan_id, periode_balik
            )
        )
        pembalik_id = cur_pf.lastrowid

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("balik", "penjualan", pembalik_id, f"Balik nota penjualan {pj['no_nota']}")
        )

    kirim_sinyal("penjualan_berubah")
    kirim_sinyal("stok_berubah")
    kirim_sinyal("kas_toko_berubah")
    if pj["metode_bayar"] == "kredit":
        kirim_sinyal("piutang_berubah")

    return pembalik_id


def ambil_daftar_penjualan(
    conn: sqlite3.Connection,
    kata_kunci: Optional[str] = None,
    tanggal_spesifik: Optional[str] = None,
    limit: int = 150
) -> List[Dict[str, Any]]:
    """Mengambil daftar nota penjualan efektif."""
    cur = conn.cursor()
    query = """
        SELECT pj.*, p.nama AS nama_pembeli,
               COALESCE((
                   SELECT SUM(ap.jumlah)
                   FROM alokasi_piutang ap
                   WHERE ap.penjualan_id = pj.id AND ap.membalik_id IS NULL
               ), 0) AS total_piutang_terbayar
        FROM v_penjualan_efektif pj
        JOIN pembeli p ON pj.pembeli_id = p.id
        WHERE 1=1
    """
    params: List[Any] = []
    if tanggal_spesifik:
        query += " AND pj.tanggal = ?"
        params.append(tanggal_spesifik)
    if kata_kunci:
        k = f"%{kata_kunci.strip()}%"
        query += " AND (pj.no_nota LIKE ? OR p.nama LIKE ? OR COALESCE(pj.nama_pembeli_nota, '') LIKE ?)"
        params.extend([k, k, k])

    query += " ORDER BY pj.tanggal DESC, pj.id DESC LIMIT ?;"
    params.append(limit)

    cur.execute(query, params)
    rows = cur.fetchall()

    hasil = []
    for r in rows:
        d = dict(r)
        if d["metode_bayar"] == "tunai":
            d["status_bayar_info"] = "Tunai (Lunas)"
        else:
            sisa = d["total"] - d["total_piutang_terbayar"]
            d["sisa_piutang"] = max(0, sisa)
            if sisa <= 0:
                d["status_bayar_info"] = "Kredit (Lunas)"
            elif d["jatuh_tempo"] and d["jatuh_tempo"] < date.today().isoformat():
                d["status_bayar_info"] = f"Lewat Jatuh Tempo (Sisa: {sisa:,})".replace(",", ".")
            else:
                d["status_bayar_info"] = f"Kredit Belum Lunas (Sisa: {sisa:,})".replace(",", ".")
        hasil.append(d)
    return hasil
