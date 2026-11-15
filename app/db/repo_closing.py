"""
app/db/repo_closing.py — Repositori akses data Closing Bulanan dan Kunci Periode.
Murni operasi database tanpa dependensi UI. Sesuai SPEC.md 4.8, RULES.md, & DATABASE.md:
1. Pemeriksaan pra-closing:
   - Angsuran lewat jatuh tempo tapi belum lunas (peringatan/informasi)
   - Input draft belum selesai
   - Rekonsiliasi saldo kas vs transaksi
2. Perhitungan ringkasan closing:
   - Saldo kas awal, kas masuk, kas keluar, saldo kas akhir periode
   - Total seluruh simpanan anggota
   - Total sisa pokok pinjaman yang masih beredar
   - Total jasa pinjaman yang diterima
3. Backup otomatis database sebelum closing
4. Eksekusi closing atomik:
   - Insert ke tabel `closing`
   - Insert snapshot ke `closing_saldo_anggota` per anggota aktif
   - Kunci (`terkunci = 1`) pada tabel transaksi periode tersebut
   - Catat log aktivitas
5. Membuka kembali periode closing (reopen):
   - Verifikasi PIN keamanan
   - Ubah status closing menjadi 'dibuka_kembali'
   - Buka kunci transaksi (`terkunci = 0`)
   - Catat log aktivitas
"""
import hashlib
import sqlite3
from datetime import date, datetime
from typing import Dict, Any, List, Optional
from app.db.repo_simpanan import hitung_saldo_simpanan_anggota
from app.db.repo_angsuran import hitung_sisa_pokok_pinjaman, ambil_daftar_angsuran_dengan_status
from app.layanan.backup import buat_backup
from app.logika.transaksi_efektif import hitung_rekap_kas_bersih_rentang


def cek_pin_closing(conn: sqlite3.Connection, pin_input: str) -> bool:
    """
    Memeriksa PIN keamanan untuk aksi pembukaan kembali closing.
    Jika pengaturan pin_hash belum diatur, PIN default adalah '1234'.
    """
    cur = conn.cursor()
    cur.execute("SELECT nilai FROM pengaturan WHERE kunci = 'pin_hash';")
    row = cur.fetchone()
    if not row or not row[0]:
        # Default PIN jika belum diubah
        return pin_input == "1234"
    
    hash_input = hashlib.sha256(pin_input.encode("utf-8")).hexdigest()
    return hash_input == row[0]


def atur_pin_closing(conn: sqlite3.Connection, pin_baru: str) -> None:
    """Mengatur PIN keamanan baru."""
    if len(pin_baru) < 4:
        raise ValueError("PIN minimal 4 karakter.")
    hash_baru = hashlib.sha256(pin_baru.encode("utf-8")).hexdigest()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO pengaturan (kunci, nilai) VALUES ('pin_hash', ?);",
            (hash_baru,)
        )


def jalankan_pemeriksaan_pra_closing(
    conn: sqlite3.Connection, periode: str
) -> Dict[str, Any]:
    """
    Melakukan verifikasi sebelum closing:
    1. Apakah periode sudah pernah di-closing dan statusnya 'tertutup'?
    2. Cek apakah ada draft input form yang belum disimpan
    3. Cek rekonsiliasi kas
    4. Cek daftar angsuran yang belum lunas dalam periode tersebut
    """
    cur = conn.cursor()

    # 1. Cek status closing periode
    cur.execute("SELECT status FROM closing WHERE periode = ?;", (periode,))
    row_c = cur.fetchone()
    sudah_closing = bool(row_c and row_c["status"] == "tertutup")

    # 2. Cek draft form jika tabel draft ada
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='draft';")
    ada_tabel_draft = cur.fetchone() is not None
    daftar_draft = []
    if ada_tabel_draft:
        cur.execute("SELECT jenis_form FROM draft;")
        daftar_draft = [r["jenis_form"] for r in cur.fetchall()]

    # 3. Cek angsuran yang jatuh tempo pada bulan periode ini namun belum lunas
    tgl_awal = f"{periode}-01"
    # Akhir bulan: ambil sampai tanggal 31
    tgl_akhir = f"{periode}-31"
    cur.execute(
        """
        SELECT a.id, a.pinjaman_id, a.angsuran_ke, a.jatuh_tempo, p.no_pinjaman,
               ang.nama AS nama_anggota, a.pokok, a.jasa
        FROM angsuran a
        JOIN pinjaman p ON a.pinjaman_id = p.id
        JOIN anggota ang ON p.anggota_id = ang.id
        WHERE p.status = 'aktif' AND a.jatuh_tempo >= ? AND a.jatuh_tempo <= ?;
        """,
        (tgl_awal, tgl_akhir)
    )
    angsuran_terlewat = []
    for r in cur.fetchall():
        daftar = ambil_daftar_angsuran_dengan_status(conn, r["pinjaman_id"])
        c_status = next((c for c in daftar if c["id"] == r["id"]), None)
        if c_status and c_status["status"] in ("belum", "sebagian", "telat"):
            angsuran_terlewat.append({
                "no_pinjaman": r["no_pinjaman"],
                "nama_anggota": r["nama_anggota"],
                "angsuran_ke": r["angsuran_ke"],
                "jatuh_tempo": r["jatuh_tempo"],
                "sisa_tagihan": c_status["total_sisa_tagihan"]
            })

    # 4. Rekonsiliasi kas BERSIH terpusat (meniadakan pembalik dalam periode yang sama)
    rekap_bersih = hitung_rekap_kas_bersih_rentang(conn, periode=periode)
    kas_awal = rekap_bersih["saldo_kas_awal"]
    kas_masuk = rekap_bersih["total_kas_masuk"]
    kas_keluar = rekap_bersih["total_kas_keluar"]
    kas_akhir = rekap_bersih["saldo_kas_akhir"]

    # Validasi rekonsiliasi matematis ketat
    cur.execute("SELECT COALESCE(SUM(masuk), 0) - COALESCE(SUM(keluar), 0) FROM kas_transaksi WHERE periode <= ?;", (periode,))
    saldo_kas_kumulatif = cur.fetchone()[0]
    rekonsiliasi_cocok = (kas_awal + kas_masuk - kas_keluar == kas_akhir == saldo_kas_kumulatif)

    return {
        "periode": periode,
        "sudah_closing": sudah_closing,
        "daftar_draft": daftar_draft,
        "angsuran_terlewat": angsuran_terlewat,
        "kas_awal": kas_awal,
        "kas_masuk": kas_masuk,
        "kas_keluar": kas_keluar,
        "kas_akhir": kas_akhir,
        "rekonsiliasi_cocok": rekonsiliasi_cocok,
        "rekap_bersih": rekap_bersih
    }


def hitung_ringkasan_closing(
    conn: sqlite3.Connection, periode: str
) -> Dict[str, Any]:
    """
    Menghitung metrik lengkap snapshot per akhir bulan:
    - Saldo kas awal & akhir
    - Total seluruh simpanan anggota per akhir periode
    - Total sisa pokok pinjaman yang masih beredar
    - Total jasa diterima selama periode bulan tersebut
    - Snapshot detail per anggota (simpanan pokok, wajib, sukarela, sisa pokok pinjaman)
    """
    cur = conn.cursor()
    pra = jalankan_pemeriksaan_pra_closing(conn, periode)

    # 1. Total jasa bersih diterima dalam periode ini
    total_jasa_diterima = pra["rekap_bersih"]["angsuran_jasa"]

    # 2. Snapshot per anggota (anggota aktif atau yang memiliki saldo/pinjaman)
    cur.execute("SELECT id, no_anggota, nama FROM anggota ORDER BY id ASC;")
    semua_anggota = cur.fetchall()

    snapshot_anggota: List[Dict[str, Any]] = []
    total_seluruh_simpanan = 0
    total_seluruh_sisa_pokok = 0

    for ang in semua_anggota:
        ang_id = ang["id"]
        saldo_simp = hitung_saldo_simpanan_anggota(conn, ang_id)
        
        # Sisa pokok pinjaman aktif anggota ini
        cur.execute(
            "SELECT id FROM pinjaman WHERE anggota_id = ? AND status = 'aktif';",
            (ang_id,)
        )
        pinj_rows = cur.fetchall()
        sisa_pokok_ang = sum(hitung_sisa_pokok_pinjaman(conn, p["id"]) for p in pinj_rows)

        tot_simp_ang = saldo_simp["total"]
        if tot_simp_ang > 0 or sisa_pokok_ang > 0:
            total_seluruh_simpanan += tot_simp_ang
            total_seluruh_sisa_pokok += sisa_pokok_ang

            snapshot_anggota.append({
                "anggota_id": ang_id,
                "no_anggota": ang["no_anggota"],
                "nama": ang["nama"],
                "saldo_pokok": saldo_simp["pokok"],
                "saldo_wajib": saldo_simp["wajib"],
                "saldo_sukarela": saldo_simp["sukarela"],
                "total_simpanan": tot_simp_ang,
                "sisa_pokok_pinjaman": sisa_pokok_ang
            })

    return {
        "periode": periode,
        "saldo_kas_awal": pra["kas_awal"],
        "total_kas_masuk": pra["kas_masuk"],
        "total_kas_keluar": pra["kas_keluar"],
        "saldo_kas_akhir": pra["kas_akhir"],
        "total_simpanan": total_seluruh_simpanan,
        "total_sisa_pokok_pinjaman": total_seluruh_sisa_pokok,
        "total_jasa_diterima": total_jasa_diterima,
        "snapshot_anggota": snapshot_anggota
    }


def eksekusi_closing_bulanan(
    conn: sqlite3.Connection,
    periode: str,
    catatan: Optional[str] = None,
    backup_dulu: bool = True
) -> int:
    """
    Mengeksekusi closing akhir bulan:
    1. Backup otomatis database sebelum closing
    2. Hitung snapshot & ringkasan
    3. Simpan ke tabel `closing`
    4. Simpan ke tabel `closing_saldo_anggota`
    5. Kunci transaksi pada periode tersebut (`terkunci = 1`)
    6. Catat log_aktivitas
    """
    pra = jalankan_pemeriksaan_pra_closing(conn, periode)
    if pra["sudah_closing"]:
        raise ValueError(f"Periode {periode} sudah di-closing sebelumnya.")

    # Validasi rekonsiliasi pra-closing ketat
    if not pra.get("rekonsiliasi_cocok", True):
        raise ValueError("Gagal closing: Rekonsiliasi saldo kas tidak cocok dengan buku transaksi kas.")

    # 1. Backup otomatis sebelum closing (RULES.md Bab 4.6 & SPEC.md 4.8)
    if backup_dulu:
        buat_backup(conn, catat_log=True)

    # 2. Hitung ringkasan dan snapshot
    ringkasan = hitung_ringkasan_closing(conn, periode)
    tgl_closing_hari_ini = date.today().strftime("%Y-%m-%d")

    with conn:
        # 3. Simpan baris closing
        cur = conn.execute(
            """
            INSERT OR REPLACE INTO closing 
            (periode, tanggal_closing, saldo_kas_awal, total_kas_masuk, total_kas_keluar,
             saldo_kas_akhir, total_simpanan, total_sisa_pokok_pinjaman, total_jasa_diterima,
             status, catatan)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'tertutup', ?);
            """,
            (
                periode,
                tgl_closing_hari_ini,
                ringkasan["saldo_kas_awal"],
                ringkasan["total_kas_masuk"],
                ringkasan["total_kas_keluar"],
                ringkasan["saldo_kas_akhir"],
                ringkasan["total_simpanan"],
                ringkasan["total_sisa_pokok_pinjaman"],
                ringkasan["total_jasa_diterima"],
                catatan.strip() if catatan else None
            )
        )
        closing_id = cur.lastrowid

        # 4. Simpan snapshot per anggota
        for sa in ringkasan["snapshot_anggota"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO closing_saldo_anggota
                (closing_id, anggota_id, saldo_pokok, saldo_wajib, saldo_sukarela, sisa_pokok_pinjaman)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    closing_id,
                    sa["anggota_id"],
                    sa["saldo_pokok"],
                    sa["saldo_wajib"],
                    sa["saldo_sukarela"],
                    sa["sisa_pokok_pinjaman"]
                )
            )

        # 5. Kunci semua transaksi periode tersebut (terkunci = 1)
        conn.execute("UPDATE simpanan_transaksi SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE pembayaran_angsuran SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE pinjaman SET terkunci = 1 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE kas_transaksi SET terkunci = 1 WHERE periode = ?;", (periode,))

        # 6. Catat log aktivitas
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            (
                "closing",
                "closing",
                closing_id,
                f"Closing bulanan periode {periode} berhasil. Kas Akhir: Rp {ringkasan['saldo_kas_akhir']:,}".replace(",", ".")
            )
        )

    return closing_id


def buka_kembali_closing(
    conn: sqlite3.Connection,
    periode: str,
    pin: str,
    alasan: str
) -> bool:
    """
    Membuka kembali periode closing yang terkunci (SPEC.md 4.8).
    Wajib menggunakan PIN keamanan dan alasan tercatat di log aktivitas.
    """
    if not cek_pin_closing(conn, pin):
        raise ValueError("PIN otorisasi pembukaan closing salah.")
    if not alasan.strip():
        raise ValueError("Alasan pembukaan closing wajib diisi.")

    cur = conn.cursor()
    cur.execute("SELECT id, status FROM closing WHERE periode = ?;", (periode,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Data closing untuk periode {periode} tidak ditemukan.")
    if row["status"] != "tertutup":
        raise ValueError(f"Periode {periode} sudah berstatus '{row['status']}'.")

    closing_id = row["id"]

    # Backup pengaman sebelum membuka kunci
    buat_backup(conn, catat_log=True)

    with conn:
        # Ubah status closing
        conn.execute(
            "UPDATE closing SET status = 'dibuka_kembali', catatan = ? WHERE id = ?;",
            (f"Dibuka kembali: {alasan.strip()}", closing_id)
        )
        # Buka kunci transaksi
        conn.execute("UPDATE simpanan_transaksi SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE pembayaran_angsuran SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE pinjaman SET terkunci = 0 WHERE periode = ?;", (periode,))
        conn.execute("UPDATE kas_transaksi SET terkunci = 0 WHERE periode = ?;", (periode,))

        # Catat log aktivitas penting
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            (
                "buka_closing",
                "closing",
                closing_id,
                f"Closing periode {periode} dibuka kembali oleh pengguna. Alasan: {alasan.strip()}"
            )
        )

    return True


def ambil_daftar_riwayat_closing(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    """Mengambil daftar riwayat closing bulanan urut dari periode terbaru."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM closing ORDER BY periode DESC;")
    return cur.fetchall()

