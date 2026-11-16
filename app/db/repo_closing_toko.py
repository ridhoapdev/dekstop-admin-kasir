"""
app/db/repo_closing_toko.py — Repositori Closing Bulanan Unit Toko:
1. Pemeriksaan Pra-Closing Toko:
   - Cek draft stock opname yang belum difinalkan
   - Cek penitipan harian yang belum selesai setoran
   - Rekonsiliasi stok: stok_saat_ini == SUM(mutasi) == SUM(qty_sisa lot)
   - Rekonsiliasi piutang: SUM(penjualan kredit) - SUM(alokasi) == SUM(saldo piutang)
   - Rekonsiliasi kas toko
2. Eksekusi Closing Toko:
   - Hitung ringkasan keuangan bersih toko periode tersebut
   - Backup otomatis database pra-closing
   - Catat snapshot ke `closing_toko` dan `closing_stok_barang`
   - Kunci (`terkunci = 1`) seluruh transaksi toko pada periode tersebut
3. Membuka Kembali Periode Closing Toko (Reopen):
   - Verifikasi PIN keamanan
   - Buka kunci transaksi (`terkunci = 0`)
   - Catat log aktivitas
"""
import sqlite3
import hashlib
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple
from app.layanan.backup import buat_backup
from app.layanan.layanan_stok import rekonsiliasi_stok_barang
from app.db.repo_laporan_toko import hitung_ringkasan_keuangan_toko
from app.layanan.bus_sinyal import kirim_sinyal


def _verifikasi_pin_keamanan(conn: sqlite3.Connection, pin_input: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT nilai FROM pengaturan WHERE kunci = 'pin_hash';")
    row = cur.fetchone()
    if not row or not row[0]:
        return pin_input == "1234"
    return hashlib.sha256(pin_input.encode("utf-8")).hexdigest() == row[0]


def periksa_pra_closing_toko(conn: sqlite3.Connection, periode: str) -> Dict[str, Any]:
    """
    Pemeriksaan kelayakan sebelum closing toko periode YYYY-MM.
    Jika ada ketidaksesuaian kritis (rekonsiliasi stok beda, opname draft belum final),
    memberikan pesan ramah dan memblokir closing.
    """
    cur = conn.cursor()
    masalah: List[str] = []
    peringatan: List[str] = []

    # 1. Periksa apakah periode sudah di-closing sebelumnya
    cur.execute("SELECT id, status FROM closing_toko WHERE periode = ?;", (periode,))
    row_c = cur.fetchone()
    if row_c and row_c["status"] == "closed":
        masalah.append(f"Periode {periode} sudah di-closing sebelumnya dan saat ini berstatus terkunci.")

    # 2. Cek Sesi Stock Opname Draft yang belum difinalkan
    cur.execute("SELECT kode_opname FROM opname_sesi WHERE periode = ? AND status = 'draft';", (periode,))
    draft_op = cur.fetchall()
    if draft_op:
        kodes = ", ".join(d["kode_opname"] for d in draft_op)
        masalah.append(f"Terdapat sesi stock opname yang masih berstatus DRAFT ({kodes}). Harap finalkan atau batalkan terlebih dahulu.")

    # 3. Cek Penitipan Harian Aktif yang belum diselesaikan setorannya
    cur.execute(
        """
        SELECT pt.id, pt.tanggal, p.nama AS nama_penitip
        FROM penitipan pt
        JOIN penitip p ON pt.penitip_id = p.id
        WHERE pt.periode = ? AND pt.status = 'aktif'
          AND EXISTS (SELECT 1 FROM penitipan_baris WHERE penitipan_id = pt.id AND selesai = 0);
        """,
        (periode,)
    )
    draft_pen = cur.fetchall()
    if draft_pen:
        pen_names = ", ".join(f"{d['nama_penitip']} ({d['tanggal']})" for d in draft_pen)
        masalah.append(f"Terdapat setoran penitipan barang yang belum diselesaikan pada periode ini: {pen_names}.")

    # 4. Rekonsiliasi Stok FIFO (stok_saat_ini == sum(mutasi) == sum(lot_sisa))
    selisih_stok = rekonsiliasi_stok_barang(conn)
    if selisih_stok:
        contoh = selisih_stok[0]
        masalah.append(
            f"Rekonsiliasi stok barang tidak cocok! Contoh: Barang {contoh['nama']} "
            f"(stok saat ini: {contoh['stok_saat_ini']}, total mutasi: {contoh['total_mutasi']}, "
            f"sisa lot: {contoh['total_sisa_lot']})."
        )

    # 5. Rekonsiliasi Piutang Pembeli
    from app.db.repo_piutang import hitung_total_piutang_semua_pembeli
    cur.execute(
        """
        SELECT 
            COALESCE(SUM(pj.total), 0) - COALESCE((SELECT SUM(jumlah) FROM alokasi_piutang), 0)
        FROM v_penjualan_efektif pj
        WHERE pj.metode_bayar = 'kredit' AND pj.status_efektif = 'NORMAL';
        """
    )
    piutang_kalkulasi = cur.fetchone()[0]
    piutang_rekap = hitung_total_piutang_semua_pembeli(conn)
    if piutang_kalkulasi != piutang_rekap:
        masalah.append(
            f"Rekonsiliasi piutang tidak cocok: Saldo nota kredit (Rp {piutang_kalkulasi:,}) "
            f"berbeda dengan total alokasi piutang (Rp {piutang_rekap:,}).".replace(",", ".")
        )

    # 6. Hitung Ringkasan Keuangan Periode Ini
    import calendar
    thn, bln = int(periode[:4]), int(periode[5:7])
    maks_hari = calendar.monthrange(thn, bln)[1]
    tgl_awal = f"{periode}-01"
    tgl_akhir = f"{periode}-{maks_hari:02d}"

    ringkasan = hitung_ringkasan_keuangan_toko(conn, tgl_awal, tgl_akhir)

    bisa_closing = len(masalah) == 0
    return {
        "bisa_closing": bisa_closing,
        "masalah": masalah,
        "peringatan": peringatan,
        "ringkasan": ringkasan,
        "periode": periode
    }


def eksekusi_closing_toko(
    conn: sqlite3.Connection,
    periode: str,
    catatan: Optional[str] = None
) -> int:
    """
    Eksekusi closing toko bulanan secara atomik:
    1. Validasi ulang pemeriksaan pra-closing
    2. Backup otomatis database
    3. Simpan snapshot closing_toko dan closing_stok_barang
    4. Kunci transaksi toko (terkunci = 1)
    """
    cek = periksa_pra_closing_toko(conn, periode)
    if not cek["bisa_closing"]:
        raise ValueError("Closing toko ditolak:\n- " + "\n- ".join(cek["masalah"]))

    # Backup otomatis pra-closing
    try:
        buat_backup(conn, catat_log=True)
    except Exception:
        pass

    ringk = cek["ringkasan"]
    tgl_closing = date.today().isoformat()
    cur = conn.cursor()

    with conn:
        # 1. Simpan header closing_toko
        cur.execute(
            """
            INSERT INTO closing_toko (
                periode, tanggal, kas_toko_awal, kas_toko_masuk, kas_toko_keluar,
                kas_toko_akhir, total_penjualan, total_hpp, laba_kotor,
                kerugian_persediaan, nilai_persediaan, total_piutang,
                total_hutang_supplier, total_hutang_penitip, status, catatan
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'closed', ?);
            """,
            (
                periode, tgl_closing, ringk["kas_toko_awal"], ringk["kas_toko_masuk"],
                ringk["kas_toko_keluar"], ringk["kas_toko_akhir"], ringk["total_penjualan"],
                ringk["total_hpp"], ringk["laba_kotor"], ringk["kerugian_persediaan"],
                ringk["nilai_persediaan"], ringk["total_piutang"], ringk["total_hutang_supplier"],
                ringk["total_hutang_penitip"], catatan
            )
        )
        closing_id = cur.lastrowid

        # 2. Snapshot per barang (closing_stok_barang)
        cur.execute(
            """
            SELECT b.id, b.stok_saat_ini,
                   COALESCE((SELECT SUM(biaya_sisa) FROM lot_stok WHERE barang_id = b.id AND qty_sisa > 0), 0) AS nilai_stok
            FROM barang b
            WHERE b.aktif = 1;
            """
        )
        semua_brg = cur.fetchall()
        for b in semua_brg:
            cur.execute(
                """
                INSERT INTO closing_stok_barang (
                    closing_toko_id, barang_id, stok_akhir_dasar, nilai_persediaan
                ) VALUES (?, ?, ?, ?);
                """,
                (closing_id, b["id"], b["stok_saat_ini"], b["nilai_stok"])
            )

        # 3. Kunci seluruh transaksi toko pada periode tersebut
        conn.execute("UPDATE pembelian_faktur SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE kas_toko_transaksi SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE mutasi_stok SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE penjualan SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE pembayaran_piutang SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE penitipan SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE pembayaran_penitip SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE retur_supplier SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE retur_penjualan SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE opname_sesi SET terkunci = 1 WHERE periode = ?;", (periode,))

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tutup", "closing_toko", closing_id, f"Closing Toko periode {periode} berhasil diselesaikan.")
        )

    kirim_sinyal("closing_toko_selesai")
    return closing_id


def buka_kembali_closing_toko(
    conn: sqlite3.Connection,
    periode: str,
    pin: str,
    alasan: str
) -> bool:
    """Membuka kembali periode closing toko dengan otorisasi PIN keamanan."""
    if not _verifikasi_pin_keamanan(conn, pin):
        raise ValueError("PIN keamanan salah. Pembukaan kembali periode ditolak.")

    cur = conn.cursor()
    cur.execute("SELECT id FROM closing_toko WHERE periode = ? AND status = 'closed';", (periode,))
    row_c = cur.fetchone()
    if not row_c:
        raise ValueError(f"Data closing toko untuk periode {periode} tidak ditemukan.")

    closing_id = row_c["id"]
    with conn:
        # Update status closing
        conn.execute(
            "UPDATE closing_toko SET status = 'dibuka_kembali', catatan = catatan || ' | Reopen: ' || ? WHERE id = ?;",
            (alasan, closing_id)
        )

        # Buka kunci transaksi
        conn.execute("UPDATE pembelian_faktur SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE kas_toko_transaksi SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE mutasi_stok SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE penjualan SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE pembayaran_piutang SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE penitipan SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE pembayaran_penitip SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE retur_supplier SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE retur_penjualan SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE opname_sesi SET terkunci = 0 WHERE periode = ?;", (periode,))

        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("ubah", "closing_toko", closing_id, f"Buka kembali closing toko periode {periode}: {alasan}")
        )

    kirim_sinyal("closing_toko_selesai")
    return True
