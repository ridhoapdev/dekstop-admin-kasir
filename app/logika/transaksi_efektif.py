"""
app/logika/transaksi_efektif.py — Satu Sumber Kebenaran (Single Source of Truth)
untuk Klasifikasi dan Kalkulasi Transaksi Efektif & Pembalik.

Aturan Bisnis:
1. Setiap transaksi diklasifikasikan menjadi:
   - 'NORMAL': Transaksi biasa dan belum pernah dibatalkan.
   - 'DIBATALKAN': Transaksi asli yang sudah memiliki transaksi pembalik.
   - 'PEMBALIK': Transaksi koreksi yang membalik transaksi sebelumnya (membalik_id IS NOT NULL).
2. Penjumlahan Bersih Periode (Rentang Tanggal / Periode Closing):
   - Jika transaksi asli DAN transaksi pembaliknya KEDUANYA berada dalam rentang yang dihitung,
     maka KEDUANYA DIKELUARKAN dari total masuk/keluar (saling meniadakan).
   - Kasus Lintas Periode: Jika transaksi asli berada di luar rentang (misal di periode yang sudah closing)
     dan transaksi pembaliknya berada di dalam rentang ini, maka transaksi pembalik TIDAK dikeluarkan,
     melainkan dicatat sebagai pos 'Koreksi/Pembatalan' tersendiri agar saldo kas periode baru akurat
     dan periode lama tetap utuh.
   - Hal yang sama berlaku jika transaksi asli di dalam rentang tetapi pembaliknya di luar rentang:
     transaksi asli tetap dihitung di periode ini sampai pembalik di periode mendatang meniadakannya.
"""

from typing import Dict, List, Any, Optional, Set, Tuple
import sqlite3


def klasifikasikan_transaksi_simpanan(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Mengembalikan metadata ID transaksi simpanan:
    - id_dibatalkan: set ID transaksi asal yang sudah dibalik
    - map_pembalik_ke_asli: dict {pembalik_id: asli_id}
    - map_asli_ke_pembalik: dict {asli_id: pembalik_id}
    """
    cur = conn.cursor()
    cur.execute("SELECT id, membalik_id FROM simpanan_transaksi WHERE membalik_id IS NOT NULL;")
    rows = cur.fetchall()
    id_dibatalkan = set()
    map_pembalik_ke_asli = {}
    map_asli_ke_pembalik = {}
    for r in rows:
        pembalik_id = r[0]
        asli_id = r[1]
        id_dibatalkan.add(asli_id)
        map_pembalik_ke_asli[pembalik_id] = asli_id
        map_asli_ke_pembalik[asli_id] = pembalik_id
    return {
        "id_dibatalkan": id_dibatalkan,
        "map_pembalik_ke_asli": map_pembalik_ke_asli,
        "map_asli_ke_pembalik": map_asli_ke_pembalik
    }


def klasifikasikan_transaksi_kas(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Mengembalikan relasi pembalik di tabel kas_transaksi.
    - Untuk sumber='manual': membalik_id dicatat di kas_transaksi.membalik_id
    - Untuk sumber='simpanan': kas pembalik merujuk ref_id = simpanan_transaksi pembalik_id
    - Untuk sumber='angsuran': kas pembalik merujuk ref_id = pembayaran_angsuran pembalik_id
    """
    cur = conn.cursor()
    
    # 1. Kas Manual (pembalik kas manual menyimpan ref_id = kas_asli.id)
    cur.execute("SELECT id, ref_id FROM kas_transaksi WHERE sumber = 'manual' AND ref_id IS NOT NULL;")
    kas_manual_pembalik = {r[0]: r[1] for r in cur.fetchall()}
    kas_manual_dibatalkan = set(kas_manual_pembalik.values())

    # 2. Simpanan -> Kas
    cur.execute("SELECT id, membalik_id FROM simpanan_transaksi WHERE membalik_id IS NOT NULL;")
    simp_pembalik_map = {r[0]: r[1] for r in cur.fetchall()}  # pembalik_st_id -> asli_st_id

    # Ambil kas transaksi yang berelasi dengan simpanan
    cur.execute("SELECT id, ref_id FROM kas_transaksi WHERE sumber = 'simpanan';")
    kas_simp_rows = cur.fetchall()
    kas_id_by_st_id = {r[1]: r[0] for r in kas_simp_rows if r[1] is not None}

    kas_simp_pembalik: Dict[int, int] = {}
    for st_pembalik_id, st_asli_id in simp_pembalik_map.items():
        k_pembalik = kas_id_by_st_id.get(st_pembalik_id)
        k_asli = kas_id_by_st_id.get(st_asli_id)
        if k_pembalik and k_asli:
            kas_simp_pembalik[k_pembalik] = k_asli

    # 3. Angsuran -> Kas
    cur.execute("SELECT id, membalik_id FROM pembayaran_angsuran WHERE membalik_id IS NOT NULL;")
    angs_pembalik_map = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("SELECT id, ref_id FROM kas_transaksi WHERE sumber = 'angsuran';")
    kas_angs_rows = cur.fetchall()
    kas_id_by_pa_id = {r[1]: r[0] for r in kas_angs_rows if r[1] is not None}

    kas_angs_pembalik: Dict[int, int] = {}
    for pa_pembalik_id, pa_asli_id in angs_pembalik_map.items():
        k_pembalik = kas_id_by_pa_id.get(pa_pembalik_id)
        k_asli = kas_id_by_pa_id.get(pa_asli_id)
        if k_pembalik and k_asli:
            kas_angs_pembalik[k_pembalik] = k_asli

    semua_pembalik_ke_asli = {}
    semua_pembalik_ke_asli.update(kas_manual_pembalik)
    semua_pembalik_ke_asli.update(kas_simp_pembalik)
    semua_pembalik_ke_asli.update(kas_angs_pembalik)

    semua_dibatalkan = set(semua_pembalik_ke_asli.values())
    semua_pembalik = set(semua_pembalik_ke_asli.keys())

    return {
        "pembalik_ke_asli": semua_pembalik_ke_asli,
        "asli_ke_pembalik": {v: k for k, v in semua_pembalik_ke_asli.items()},
        "id_dibatalkan": semua_dibatalkan,
        "id_pembalik": semua_pembalik
    }


def klasifikasikan_pembayaran_angsuran(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Mengembalikan metadata ID pembayaran angsuran:
    - id_dibatalkan: set ID pembayaran asal yang sudah dibalik
    - map_pembalik_ke_asli: dict {pembalik_id: asli_id}
    """
    cur = conn.cursor()
    cur.execute("SELECT id, membalik_id FROM pembayaran_angsuran WHERE membalik_id IS NOT NULL;")
    rows = cur.fetchall()
    id_dibatalkan = set()
    map_pembalik_ke_asli = {}
    for r in rows:
        pembalik_id = r[0]
        asli_id = r[1]
        id_dibatalkan.add(asli_id)
        map_pembalik_ke_asli[pembalik_id] = asli_id
    return {
        "id_dibatalkan": id_dibatalkan,
        "map_pembalik_ke_asli": map_pembalik_ke_asli,
        "asli_ke_pembalik": {v: k for k, v in map_pembalik_ke_asli.items()}
    }


def hitung_rekap_kas_bersih_rentang(
    conn: sqlite3.Connection,
    tanggal_awal: Optional[str] = None,
    tanggal_akhir: Optional[str] = None,
    periode: Optional[str] = None
) -> Dict[str, Any]:
    """
    Menghitung rekap arus kas dan komponen simpanan, angsuran, pencairan, admin, manual secara BERSIH.
    
    Aturan:
    - Pasangan transaksi asli & pembalik yang KEDUANYA berada dalam rentang: DIKELUARKAN dari total masuk/keluar.
    - Pembalik lintas periode (asli di luar rentang, pembalik di dalam rentang): dimasukkan ke pos 'koreksi'.
    - Transaksi asli yang dibalik lintas periode (asli di dalam, pembalik di luar rentang): tetap dihitung.
    - Saldo kas awal dan saldo kas akhir tetap rekonsiliasi matematis 100%.
    """
    cur = conn.cursor()
    meta_kas = klasifikasikan_transaksi_kas(conn)
    pembalik_ke_asli = meta_kas["pembalik_ke_asli"]
    asli_ke_pembalik = meta_kas["asli_ke_pembalik"]

    # Ambil seluruh baris kas transaksi dalam rentang
    query = "SELECT * FROM kas_transaksi WHERE 1=1"
    params: List[Any] = []
    if periode:
        query += " AND periode = ?"
        params.append(periode)
    else:
        if tanggal_awal:
            query += " AND tanggal >= ?"
            params.append(tanggal_awal)
        if tanggal_akhir:
            query += " AND tanggal <= ?"
            params.append(tanggal_akhir)
    query += " ORDER BY tanggal ASC, id ASC;"

    cur.execute(query, params)
    baris_rentang = cur.fetchall()
    id_dalam_rentang = {r["id"] for r in baris_rentang}

    # Saldo Kas Awal (sebelum batas awal)
    if periode:
        cur.execute(
            "SELECT COALESCE(SUM(masuk), 0) - COALESCE(SUM(keluar), 0) FROM kas_transaksi WHERE periode < ?;",
            (periode,)
        )
    elif tanggal_awal:
        cur.execute(
            "SELECT COALESCE(SUM(masuk), 0) - COALESCE(SUM(keluar), 0) FROM kas_transaksi WHERE tanggal < ?;",
            (tanggal_awal,)
        )
    else:
        cur.execute("SELECT 0;")
    saldo_kas_awal = cur.fetchone()[0]

    # Inisialisasi akumulator bersih
    total_kas_masuk = 0
    total_kas_keluar = 0
    
    simpanan_setor_bersih = 0
    simpanan_tarik_bersih = 0
    angsuran_pokok_bersih = 0
    angsuran_jasa_bersih = 0
    angsuran_denda_bersih = 0
    pencairan_pinjaman_bersih = 0
    biaya_admin_bersih = 0
    kas_manual_masuk_bersih = 0
    kas_manual_keluar_bersih = 0

    koreksi_masuk_lintas = 0
    koreksi_keluar_lintas = 0
    jumlah_koreksi_lintas = 0

    daftar_ditiadakan_pasangan = set()  # ID yang ditiadakan karena kedua pasangan dalam rentang
    for r in baris_rentang:
        r_id = r["id"]
        # Jika r adalah pembalik dan aslinya ada di rentang ini juga -> tiadakan keduanya
        if r_id in pembalik_ke_asli:
            asli_id = pembalik_ke_asli[r_id]
            if asli_id in id_dalam_rentang:
                daftar_ditiadakan_pasangan.add(r_id)
                daftar_ditiadakan_pasangan.add(asli_id)
        # Jika r adalah asli dan pembaliknya ada di rentang ini juga -> tiadakan keduanya
        elif r_id in asli_ke_pembalik:
            pembalik_id = asli_ke_pembalik[r_id]
            if pembalik_id in id_dalam_rentang:
                daftar_ditiadakan_pasangan.add(r_id)
                daftar_ditiadakan_pasangan.add(pembalik_id)

    # Ambil rincian detail pembayaran angsuran untuk alokasi pokok vs jasa
    cur.execute("SELECT id, bayar_pokok, bayar_jasa, denda, membalik_id FROM pembayaran_angsuran;")
    pa_rows = {r[0]: r for r in cur.fetchall()}

    # Proses setiap transaksi kas dalam rentang
    for r in baris_rentang:
        r_id = r["id"]
        masuk = r["masuk"]
        keluar = r["keluar"]
        sumber = r["sumber"]
        ref_id = r["ref_id"]

        # 1. Jika termasuk pasangan yang ditiadakan dalam rentang yang sama -> lewati
        if r_id in daftar_ditiadakan_pasangan:
            continue

        # 2. Jika merupakan pembalik lintas periode (aslinya di luar rentang)
        if r_id in pembalik_ke_asli:
            jumlah_koreksi_lintas += 1
            if masuk > 0:
                koreksi_masuk_lintas += masuk
                total_kas_masuk += masuk
            else:
                koreksi_keluar_lintas += keluar
                total_kas_keluar += keluar
            continue

        # 3. Transaksi normal atau asli
        if masuk > 0:
            total_kas_masuk += masuk
        else:
            total_kas_keluar += keluar

        if sumber == "simpanan":
            if masuk > 0:
                simpanan_setor_bersih += masuk
            else:
                simpanan_tarik_bersih += keluar
        elif sumber == "pencairan":
            pencairan_pinjaman_bersih += keluar
        elif sumber == "biaya_admin":
            biaya_admin_bersih += masuk
        elif sumber == "angsuran":
            # Alokasikan pokok, jasa, denda dari referensi pembayaran_angsuran
            pa = pa_rows.get(ref_id)
            if pa:
                angsuran_pokok_bersih += pa["bayar_pokok"]
                angsuran_jasa_bersih += pa["bayar_jasa"]
                angsuran_denda_bersih += pa["denda"]
            else:
                angsuran_pokok_bersih += masuk
        elif sumber == "manual":
            if masuk > 0:
                kas_manual_masuk_bersih += masuk
            else:
                kas_manual_keluar_bersih += keluar

    saldo_kas_akhir = saldo_kas_awal + total_kas_masuk - total_kas_keluar

    return {
        "saldo_kas_awal": saldo_kas_awal,
        "total_kas_masuk": total_kas_masuk,
        "total_kas_keluar": total_kas_keluar,
        "saldo_kas_akhir": saldo_kas_akhir,
        "simpanan_setor": simpanan_setor_bersih,
        "simpanan_tarik": simpanan_tarik_bersih,
        "angsuran_pokok": angsuran_pokok_bersih,
        "angsuran_jasa": angsuran_jasa_bersih,
        "angsuran_denda": angsuran_denda_bersih,
        "angsuran_total": angsuran_pokok_bersih + angsuran_jasa_bersih + angsuran_denda_bersih,
        "pencairan_pinjaman": pencairan_pinjaman_bersih,
        "biaya_admin": biaya_admin_bersih,
        "kas_manual_masuk": kas_manual_masuk_bersih,
        "kas_manual_keluar": kas_manual_keluar_bersih,
        "koreksi_masuk_lintas": koreksi_masuk_lintas,
        "koreksi_keluar_lintas": koreksi_keluar_lintas,
        "jumlah_koreksi_lintas": jumlah_koreksi_lintas,
        "id_ditiadakan_pasangan": daftar_ditiadakan_pasangan
    }


def ambil_daftar_transaksi_kas_lengkap(
    conn: sqlite3.Connection,
    tanggal_awal: Optional[str] = None,
    tanggal_akhir: Optional[str] = None,
    periode: Optional[str] = None,
    sembunyikan_dibatalkan: bool = False
) -> List[Dict[str, Any]]:
    """
    Mengambil daftar transaksi buku kas dengan label status 'NORMAL', 'DIBATALKAN', atau 'KOREKSI'.
    Jika sembunyikan_dibatalkan = True, maka pasangan yang saling meniadakan tidak ditampilkan.
    """
    cur = conn.cursor()
    meta_kas = klasifikasikan_transaksi_kas(conn)
    pembalik_ke_asli = meta_kas["pembalik_ke_asli"]
    asli_ke_pembalik = meta_kas["asli_ke_pembalik"]

    query = "SELECT * FROM kas_transaksi WHERE 1=1"
    params: List[Any] = []
    if periode:
        query += " AND periode = ?"
        params.append(periode)
    else:
        if tanggal_awal:
            query += " AND tanggal >= ?"
            params.append(tanggal_awal)
        if tanggal_akhir:
            query += " AND tanggal <= ?"
            params.append(tanggal_akhir)
    query += " ORDER BY tanggal DESC, id DESC;"

    cur.execute(query, params)
    semua_baris = [dict(r) for r in cur.fetchall()]
    id_dalam_rentang = {r["id"] for r in semua_baris}

    hasil: List[Dict[str, Any]] = []
    for r in semua_baris:
        r_id = r["id"]
        is_dibatalkan = r_id in asli_ke_pembalik
        is_pembalik = r_id in pembalik_ke_asli

        if is_dibatalkan:
            pembalik_id = asli_ke_pembalik[r_id]
            status_klasifikasi = "DIBATALKAN"
            if sembunyikan_dibatalkan and (pembalik_id in id_dalam_rentang):
                continue
        elif is_pembalik:
            asli_id = pembalik_ke_asli[r_id]
            status_klasifikasi = "KOREKSI"
            if sembunyikan_dibatalkan and (asli_id in id_dalam_rentang):
                continue
        else:
            status_klasifikasi = "NORMAL"

        r["status_klasifikasi"] = status_klasifikasi
        hasil.append(r)

    return hasil
