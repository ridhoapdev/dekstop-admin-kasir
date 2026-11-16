"""
app/db/repo_opname_toko.py — Repositori Penyesuaian Stok Manual dan Stock Opname Toko:
1. Penyesuaian Manual: rusak, hilang, kedaluwarsa (mengurangi stok via FIFO, dicatat sebagai kerugian persediaan)
2. Sesi Stock Opname: buat sesi draft, simpan input fisik per barang, hitung selisih & nilai
3. Finalisasi Stock Opname:
   - Selisih kurang: mengurangi lot FIFO terlama (dicatat sebagai rugi persediaan)
   - Selisih lebih: membuat lot baru (asal 'penyesuaian') dengan harga beli terakhir
   - Mengunci sesi opname (terkunci = 1, status = 'final')
   - Opname barang titipan: ditandai khusus untuk ditinjau tanpa otomatis menjadi hutang
"""
import sqlite3
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from app.db.repo_simpanan import cek_periode_terkunci
from app.layanan.layanan_stok import kurangi_stok_fifo, tambah_stok_masuk, ambil_stok_barang
from app.layanan.bus_sinyal import kirim_sinyal


def _ambil_pengaturan(conn: sqlite3.Connection, kunci: str, default: str = "") -> str:
    cur = conn.cursor()
    cur.execute("SELECT nilai FROM pengaturan WHERE kunci = ?;", (kunci,))
    row = cur.fetchone()
    return row[0] if row else default


def buat_kode_opname_baru(conn: sqlite3.Connection, tanggal: str) -> str:
    format_tpl = _ambil_pengaturan(conn, "format_kode_opname", "SO-{YYYY}{MM}{DD}-{NO}")
    tgl_dt = datetime.strptime(tanggal[:10], "%Y-%m-%d")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM opname_sesi WHERE tanggal = ?;", (tanggal,))
    urutan = cur.fetchone()[0] + 1
    hasil = format_tpl.replace("{YYYY}", str(tgl_dt.year))
    hasil = hasil.replace("{MM}", f"{tgl_dt.month:02d}")
    hasil = hasil.replace("{DD}", f"{tgl_dt.day:02d}")
    hasil = hasil.replace("{NO}", f"{urutan:04d}")
    return hasil


# ==========================================================
# 1. PENYESUAIAN MANUAL (RUSAK, HILANG, KEDALUWARSA)
# ==========================================================

def catat_penyesuaian_manual(
    conn: sqlite3.Connection,
    barang_id: int,
    tanggal: str,
    jenis: str,  # 'rusak', 'hilang', 'kedaluwarsa'
    jumlah_dasar: int,
    catatan: str
) -> List[Dict[str, Any]]:
    """
    Mencatat penyesuaian stok manual (rusak / hilang / kedaluwarsa).
    Mengurangi stok lewat FIFO (lot terlama dulu) dan dicatat sebagai kerugian persediaan.
    """
    if jenis not in ("rusak", "hilang", "kedaluwarsa"):
        raise ValueError("Jenis penyesuaian harus salah satu dari: rusak, hilang, kedaluwarsa.")
    if jumlah_dasar <= 0:
        raise ValueError("Jumlah penyesuaian harus lebih besar dari nol.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing).")

    with conn:
        hasil = kurangi_stok_fifo(
            conn=conn,
            barang_id=barang_id,
            qty_diminta=jumlah_dasar,
            jenis_mutasi=jenis,
            ref_tabel="penyesuaian_manual",
            ref_id=0,
            tanggal=tanggal
        )
        total_biaya = sum(h["biaya"] for h in hasil)
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            (
                "tambah", "mutasi_stok", barang_id,
                f"Penyesuaian {jenis} sebanyak {jumlah_dasar} unit (rugi Rp {total_biaya:,}): {catatan}".replace(",", ".")
            )
        )

    kirim_sinyal("stok_berubah")
    return hasil


# ==========================================================
# 2. STOCK OPNAME BERKALA / BULANAN
# ==========================================================

def buat_sesi_opname(conn: sqlite3.Connection, tanggal: str, catatan: Optional[str] = None) -> Tuple[int, str]:
    """Membuat sesi baru stock opname berstatus 'draft'."""
    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing).")

    kode = buat_kode_opname_baru(conn, tanggal)
    with conn:
        cur = conn.execute(
            """
            INSERT INTO opname_sesi (kode_opname, tanggal, status, catatan, periode)
            VALUES (?, ?, 'draft', ?, ?);
            """,
            (kode, tanggal, catatan, periode)
        )
        sesi_id = cur.lastrowid
    return sesi_id, kode


def simpan_baris_opname_draft(
    conn: sqlite3.Connection,
    sesi_id: int,
    daftar_input_fisik: List[Dict[str, Any]]
) -> None:
    """
    Menyimpan atau memperbarui data fisik opname per barang (draft auto-save).
    daftar_input_fisik: [
        {
            "barang_id": int,
            "stok_fisik": int,
            "catatan": Optional[str]
        }, ...
    ]
    """
    cur = conn.cursor()
    cur.execute("SELECT status, periode FROM opname_sesi WHERE id = ?;", (sesi_id,))
    row_sesi = cur.fetchone()
    if not row_sesi:
        raise ValueError("Sesi opname tidak ditemukan.")
    if row_sesi["status"] != "draft":
        raise ValueError("Sesi opname sudah difinalkan dan terkunci.")

    with conn:
        for item in daftar_input_fisik:
            b_id = item["barang_id"]
            fisik = item["stok_fisik"]
            catatan = item.get("catatan", "")

            # Ambil stok sistem saat ini
            cur.execute("SELECT stok_saat_ini, jenis_kepemilikan FROM barang WHERE id = ?;", (b_id,))
            row_b = cur.fetchone()
            stok_sistem = row_b["stok_saat_ini"] if row_b else 0
            selisih_qty = fisik - stok_sistem

            # Cari harga satuan dasar patokan (harga beli terakhir atau harga jual)
            cur.execute(
                """
                SELECT (pd.harga_per_satuan_input / pd.isi_per_satuan) AS hrg_beli
                FROM pembelian_detail pd
                JOIN pembelian_faktur pf ON pd.faktur_id = pf.id
                WHERE pd.barang_id = ?
                ORDER BY pf.tanggal DESC, pf.id DESC LIMIT 1;
                """,
                (b_id,)
            )
            row_hrg = cur.fetchone()
            hrg_patokan = row_hrg[0] if (row_hrg and row_hrg[0]) else 0

            selisih_nilai = selisih_qty * hrg_patokan

            cur.execute(
                """
                INSERT INTO opname_barang (
                    opname_sesi_id, barang_id, stok_sistem, stok_fisik,
                    selisih_qty, harga_satuan_dasar, selisih_nilai, catatan
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(opname_sesi_id, barang_id) DO UPDATE SET
                    stok_sistem = excluded.stok_sistem,
                    stok_fisik = excluded.stok_fisik,
                    selisih_qty = excluded.selisih_qty,
                    harga_satuan_dasar = excluded.harga_satuan_dasar,
                    selisih_nilai = excluded.selisih_nilai,
                    catatan = excluded.catatan;
                """,
                (sesi_id, b_id, stok_sistem, fisik, selisih_qty, hrg_patokan, selisih_nilai, catatan)
            )


def ambil_daftar_opname_barang(conn: sqlite3.Connection, sesi_id: int) -> List[Dict[str, Any]]:
    """Mengambil rincian barang dalam satu sesi opname."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ob.*, b.kode, b.nama, b.satuan_dasar, b.jenis_kepemilikan, p.nama AS nama_penitip
        FROM opname_barang ob
        JOIN barang b ON ob.barang_id = b.id
        LEFT JOIN penitip p ON b.penitip_id = p.id
        WHERE ob.opname_sesi_id = ?
        ORDER BY b.nama ASC;
        """,
        (sesi_id,)
    )
    return [dict(r) for r in cur.fetchall()]


def finalisasi_sesi_opname(conn: sqlite3.Connection, sesi_id: int) -> Dict[str, Any]:
    """
    Eksekusi finalisasi stock opname:
    1. Selisih kurang (< 0): Mengurangi lot FIFO terlama (kerugian persediaan).
    2. Selisih lebih (> 0): Membuat lot baru (asal 'penyesuaian') dengan harga patokan.
    3. Update total ringkasan sesi dan kunci sesi (status='final', terkunci=1).
    """
    cur = conn.cursor()
    cur.execute("SELECT * FROM opname_sesi WHERE id = ?;", (sesi_id,))
    sesi = cur.fetchone()
    if not sesi:
        raise ValueError("Sesi opname tidak ditemukan.")
    if sesi["status"] == "final":
        raise ValueError("Sesi opname ini sudah difinalkan sebelumnya.")

    periode = sesi["periode"]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing).")

    daftar_opname = ambil_daftar_opname_barang(conn, sesi_id)
    if not daftar_opname:
        raise ValueError("Sesi opname belum memiliki barang yang diinput.")

    tot_kurang_qty = 0
    tot_kurang_nilai = 0
    tot_lebih_qty = 0
    tot_lebih_nilai = 0

    with conn:
        for ob in daftar_opname:
            b_id = ob["barang_id"]
            selisih_qty = ob["selisih_qty"]
            tgl = sesi["tanggal"]

            if selisih_qty < 0:
                # Selisih kurang: kurangi stok lot FIFO terlama
                qty_hilang = abs(selisih_qty)
                hasil = kurangi_stok_fifo(
                    conn=conn,
                    barang_id=b_id,
                    qty_diminta=qty_hilang,
                    jenis_mutasi="penyesuaian_opname",
                    ref_tabel="opname",
                    ref_id=sesi_id,
                    tanggal=tgl
                )
                nilai_hilang = sum(h["biaya"] for h in hasil)
                tot_kurang_qty += qty_hilang
                tot_kurang_nilai += nilai_hilang

            elif selisih_qty > 0:
                # Selisih lebih: buat lot stok baru
                hrg_dasar = ob["harga_satuan_dasar"]
                total_biaya_lebih = selisih_qty * hrg_dasar
                tambah_stok_masuk(
                    conn=conn,
                    barang_id=b_id,
                    qty_masuk=selisih_qty,
                    total_biaya=total_biaya_lebih,
                    asal="penyesuaian",
                    ref_tabel="opname",
                    ref_id=sesi_id,
                    tanggal=tgl,
                    catatan=f"Opname #{sesi['kode_opname']}: {ob['catatan'] or 'Selisih lebih fisik'}"
                )
                tot_lebih_qty += selisih_qty
                tot_lebih_nilai += total_biaya_lebih

        # Kunci dan update sesi opname
        conn.execute(
            """
            UPDATE opname_sesi
            SET status = 'final', terkunci = 1,
                total_selisih_kurang_qty = ?, total_selisih_kurang_nilai = ?,
                total_selisih_lebih_qty = ?, total_selisih_lebih_nilai = ?
            WHERE id = ?;
            """,
            (tot_kurang_qty, tot_kurang_nilai, tot_lebih_qty, tot_lebih_nilai, sesi_id)
        )

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            (
                "tutup", "opname_sesi", sesi_id,
                f"Finalisasi opname #{sesi['kode_opname']} (kurang {tot_kurang_qty} unit / Rp {tot_kurang_nilai:,}, lebih {tot_lebih_qty} unit / Rp {tot_lebih_nilai:,})".replace(",", ".")
            )
        )

    kirim_sinyal("stok_berubah")
    return {
        "sesi_id": sesi_id,
        "kode_opname": sesi["kode_opname"],
        "total_kurang_qty": tot_kurang_qty,
        "total_kurang_nilai": tot_kurang_nilai,
        "total_lebih_qty": tot_lebih_qty,
        "total_lebih_nilai": tot_lebih_nilai
    }
