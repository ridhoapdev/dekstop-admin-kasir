"""
app/db/repo_kartu_anggota.py — Repositori akses data lengkap untuk Kartu Anggota dan Pencarian Global.
Murni operasi database tanpa dependensi UI. Sesuai SPEC.md 4.6:
- Pencarian global cepat (nama, no_anggota, no_pinjaman, nik_karyawan)
- Ringkasan profil lengkap anggota
- Ringkasan saldo simpanan per jenis & total
- Daftar pinjaman aktif anggota beserta status, sisa pokok, angsuran ke-berapa, jatuh tempo berikutnya, dan tunggakan
- Riwayat seluruh transaksi anggota (gabungan simpanan dan pembayaran angsuran) urut tanggal
"""
import sqlite3
from datetime import date
from typing import List, Dict, Optional, Any
from app.db.repo_simpanan import hitung_saldo_simpanan_anggota
from app.db.repo_angsuran import (
    hitung_sisa_pokok_pinjaman,
    ambil_daftar_angsuran_dengan_status,
    ambil_angsuran_berikutnya_yang_harus_dibayar
)


def cari_global(conn: sqlite3.Connection, kata_kunci: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Mencari entitas (anggota dan pinjaman) berdasarkan kata kunci.
    Tidak peka huruf besar-kecil (case-insensitive).
    Mengembalikan daftar ringkas untuk popup pencarian global.
    """
    k = kata_kunci.strip()
    if not k:
        return []

    cur = conn.cursor()
    like_param = f"%{k}%"

    # 1. Cari anggota berdasarkan nama, no_anggota, nik_karyawan, unit
    cur.execute(
        """
        SELECT id, no_anggota, nama, unit, status
        FROM anggota
        WHERE nama LIKE ? OR no_anggota LIKE ? OR nik_karyawan LIKE ? OR unit LIKE ?
        ORDER BY id DESC LIMIT ?;
        """,
        (like_param, like_param, like_param, like_param, limit)
    )
    hasil: List[Dict[str, Any]] = []
    for r in cur.fetchall():
        hasil.append({
            "tipe": "anggota",
            "id": r["id"],
            "judul": f"{r['no_anggota']} - {r['nama']}",
            "subjudul": f"Unit: {r['unit'] or '-'} | Status: {r['status'].capitalize()}",
            "anggota_id": r["id"]
        })

    # 2. Cari pinjaman berdasarkan no_pinjaman
    cur.execute(
        """
        SELECT p.id, p.no_pinjaman, p.plafon, p.status, p.anggota_id, a.nama AS nama_anggota
        FROM pinjaman p
        JOIN anggota a ON p.anggota_id = a.id
        WHERE p.no_pinjaman LIKE ?
        ORDER BY p.id DESC LIMIT ?;
        """,
        (like_param, limit)
    )
    for r in cur.fetchall():
        hasil.append({
            "tipe": "pinjaman",
            "id": r["id"],
            "judul": f"Pinjaman {r['no_pinjaman']} ({r['nama_anggota']})",
            "subjudul": f"Plafon: Rp {r['plafon']:,} | Status: {r['status'].capitalize()}".replace(",", "."),
            "anggota_id": r["anggota_id"]
        })

    return hasil


def ambil_data_kartu_anggota(
    conn: sqlite3.Connection,
    anggota_id: int,
    filter_jenis_transaksi: str = "semua"
) -> Optional[Dict[str, Any]]:
    """
    Mengambil data lengkap untuk Kartu Anggota:
    - Data diri anggota
    - Saldo simpanan per jenis (pokok, wajib, sukarela, total)
    - Daftar pinjaman aktif beserta: sisa pokok, angsuran ke-berapa, jatuh tempo berikutnya, dan total tunggakan
    - Riwayat seluruh transaksi urut tanggal
    """
    cur = conn.cursor()
    cur.execute("SELECT * FROM anggota WHERE id = ?;", (anggota_id,))
    anggota = cur.fetchone()
    if not anggota:
        return None

    # 1. Saldo Simpanan
    saldo_simpanan = hitung_saldo_simpanan_anggota(conn, anggota_id)

    # 2. Pinjaman Aktif & Analisis Tunggakan
    cur.execute(
        """
        SELECT p.*, pr.nama AS nama_produk
        FROM pinjaman p
        LEFT JOIN produk_pinjaman pr ON p.produk_id = pr.id
        WHERE p.anggota_id = ? AND p.status = 'aktif'
        ORDER BY p.id DESC;
        """,
        (anggota_id,)
    )
    daftar_pinjaman_aktif = []
    tgl_hari_ini = date.today().strftime("%Y-%m-%d")

    for pinj in cur.fetchall():
        pinj_id = pinj["id"]
        sisa_pokok = hitung_sisa_pokok_pinjaman(conn, pinj_id)
        
        # Analisis cicilan & tunggakan
        semua_angsuran = ambil_daftar_angsuran_dengan_status(conn, pinj_id, tanggal_patokan=tgl_hari_ini)
        
        # Angsuran berikutnya yang harus dibayar
        next_angsuran = ambil_angsuran_berikutnya_yang_harus_dibayar(conn, pinj_id)
        
        # Hitung tunggakan: cicilan berstatus 'telat'
        total_tunggakan = sum(
            c["total_sisa_tagihan"] for c in semua_angsuran if c["status"] == "telat"
        )
        jumlah_cicilan_telat = sum(1 for c in semua_angsuran if c["status"] == "telat")

        daftar_pinjaman_aktif.append({
            "pinjaman_id": pinj_id,
            "no_pinjaman": pinj["no_pinjaman"],
            "nama_produk": pinj["nama_produk"] or "Pinjaman",
            "plafon": pinj["plafon"],
            "tenor": pinj["tenor"],
            "jasa_persen": pinj["jasa_persen_per_bulan"],
            "tanggal_cair": pinj["tanggal_cair"],
            "sisa_pokok": sisa_pokok,
            "angsuran_ke_berikutnya": next_angsuran["angsuran_ke"] if next_angsuran else None,
            "jatuh_tempo_berikutnya": next_angsuran["jatuh_tempo"] if next_angsuran else None,
            "total_tunggakan": total_tunggakan,
            "jumlah_cicilan_telat": jumlah_cicilan_telat
        })

    # 3. Riwayat Seluruh Transaksi Anggota (Simpanan + Pembayaran Angsuran)
    riwayat_transaksi: List[Dict[str, Any]] = []

    # Ambil Simpanan
    if filter_jenis_transaksi in ("semua", "simpanan"):
        cur.execute(
            """
            SELECT id, tanggal, jenis, arah, jumlah, keterangan, membalik_id
            FROM simpanan_transaksi
            WHERE anggota_id = ?
            ORDER BY tanggal DESC, id DESC;
            """,
            (anggota_id,)
        )
        for s in cur.fetchall():
            riwayat_transaksi.append({
                "tanggal": s["tanggal"],
                "tipe": "Simpanan",
                "rincian": f"Simpanan {s['jenis'].capitalize()} ({s['arah'].upper()})",
                "masuk": s["jumlah"] if s["arah"] == "setor" else 0,
                "keluar": s["jumlah"] if s["arah"] == "tarik" else 0,
                "keterangan": s["keterangan"] or "-",
                "is_pembalik": bool(s["membalik_id"])
            })

    # Ambil Pembayaran Angsuran
    if filter_jenis_transaksi in ("semua", "angsuran"):
        cur.execute(
            """
            SELECT pa.id, pa.tanggal, pa.bayar_pokok, pa.bayar_jasa, pa.denda,
                   pa.keterangan, pa.membalik_id, p.no_pinjaman, ang.angsuran_ke
            FROM pembayaran_angsuran pa
            JOIN pinjaman p ON pa.pinjaman_id = p.id
            LEFT JOIN angsuran ang ON pa.angsuran_id = ang.id
            WHERE p.anggota_id = ?
            ORDER BY pa.tanggal DESC, pa.id DESC;
            """,
            (anggota_id,)
        )
        for a in cur.fetchall():
            tot = a["bayar_pokok"] + a["bayar_jasa"] + a["denda"]
            angs_ke = f"Ke-{a['angsuran_ke']}" if a["angsuran_ke"] else "Pelunasan"
            riwayat_transaksi.append({
                "tanggal": a["tanggal"],
                "tipe": "Angsuran",
                "rincian": f"Angsuran {a['no_pinjaman']} ({angs_ke})",
                "masuk": tot if tot > 0 else 0,
                "keluar": abs(tot) if tot < 0 else 0,
                "keterangan": a["keterangan"] or "-",
                "is_pembalik": bool(a["membalik_id"])
            })

    # Urutkan riwayat gabungan dari tanggal terbaru ke terlama
    riwayat_transaksi.sort(key=lambda x: x["tanggal"], reverse=True)

    return {
        "anggota": dict(anggota),
        "saldo_simpanan": saldo_simpanan,
        "pinjaman_aktif": daftar_pinjaman_aktif,
        "riwayat_transaksi": riwayat_transaksi
    }


def ambil_transaksi_filter_cepat(
    conn: sqlite3.Connection,
    mode_filter: str,
    tanggal_spesifik: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    SPEC.md 4.6 C: Tombol filter cepat:
    - 'hari_ini': transaksi hari ini
    - 'minggu_ini': transaksi 7 hari terakhir / minggu berjalan
    - 'bulan_ini': transaksi bulan ini (YYYY-MM)
    - 'pilih_tanggal': transaksi pada tanggal_spesifik (YYYY-MM-DD)
    - 'pinjaman_aktif': daftar seluruh pinjaman yang sedang aktif
    - 'menunggak': daftar pinjaman / anggota yang sedang menunggak cicilan
    """
    cur = conn.cursor()
    tgl_hari_ini = date.today().strftime("%Y-%m-%d")
    hasil: List[Dict[str, Any]] = []

    if mode_filter == "pinjaman_aktif":
        cur.execute(
            """
            SELECT p.id, p.no_pinjaman, p.plafon, p.tenor, p.tanggal_cair,
                   a.id AS anggota_id, a.nama AS nama_anggota, a.no_anggota, a.unit
            FROM pinjaman p
            JOIN anggota a ON p.anggota_id = a.id
            WHERE p.status = 'aktif'
            ORDER BY p.tanggal_cair DESC;
            """
        )
        for r in cur.fetchall():
            sisa = hitung_sisa_pokok_pinjaman(conn, r["id"])
            next_a = ambil_angsuran_berikutnya_yang_harus_dibayar(conn, r["id"])
            hasil.append({
                "id": r["id"],
                "tanggal": r["tanggal_cair"],
                "entitas": f"{r['nama_anggota']} ({r['no_anggota']})",
                "rincian": f"Pinjaman {r['no_pinjaman']} (Plafon: {r['plafon']:,})".replace(",", "."),
                "nominal": sisa,
                "status_info": f"Angsuran Ke-{next_a['angsuran_ke'] if next_a else '-'}",
                "anggota_id": r["anggota_id"]
            })
        return hasil

    if mode_filter == "menunggak":
        # Ambil semua angsuran aktif yang lewat jatuh tempo dan belum lunas
        cur.execute(
            """
            SELECT p.id AS pinjaman_id, p.no_pinjaman, a.id AS anggota_id,
                   a.nama AS nama_anggota, a.no_anggota, a.no_hp
            FROM pinjaman p
            JOIN anggota a ON p.anggota_id = a.id
            WHERE p.status = 'aktif';
            """
        )
        for r in cur.fetchall():
            semua_angs = ambil_daftar_angsuran_dengan_status(conn, r["pinjaman_id"], tanggal_patokan=tgl_hari_ini)
            tunggakan_cicilan = [c for c in semua_angs if c["status"] == "telat"]
            if tunggakan_cicilan:
                tot_tunggakan = sum(c["total_sisa_tagihan"] for c in tunggakan_cicilan)
                angs_list_str = ", ".join(str(c["angsuran_ke"]) for c in tunggakan_cicilan)
                hasil.append({
                    "id": r["pinjaman_id"],
                    "tanggal": tunggakan_cicilan[0]["jatuh_tempo"],
                    "entitas": f"{r['nama_anggota']} ({r['no_anggota']})",
                    "rincian": f"Pinjaman {r['no_pinjaman']} - Cicilan Ke-{angs_list_str}",
                    "nominal": tot_tunggakan,
                    "status_info": f"Menunggak {len(tunggakan_cicilan)} cicilan",
                    "anggota_id": r["anggota_id"]
                })
        return hasil

    # Filter berdasarkan tanggal transaksi (simpanan + pembayaran angsuran)
    where_klausa_s = ""
    where_klausa_a = ""
    params: List[Any] = []

    if mode_filter == "hari_ini":
        where_klausa_s = "WHERE st.tanggal = ?"
        where_klausa_a = "WHERE pa.tanggal = ?"
        params = [tgl_hari_ini]
    elif mode_filter == "bulan_ini":
        bln = tgl_hari_ini[:7]
        where_klausa_s = "WHERE st.periode = ?"
        where_klausa_a = "WHERE pa.periode = ?"
        params = [bln]
    elif mode_filter == "pilih_tanggal" and tanggal_spesifik:
        where_klausa_s = "WHERE st.tanggal = ?"
        where_klausa_a = "WHERE pa.tanggal = ?"
        params = [tanggal_spesifik]
    else:  # minggu_ini: 7 hari terakhir
        where_klausa_s = "WHERE st.tanggal >= date('now', 'localtime', '-6 days')"
        where_klausa_a = "WHERE pa.tanggal >= date('now', 'localtime', '-6 days')"
        params = []

    # Transaksi Simpanan Efektif (hanya NORMAL yang tampil di filter cepat)
    cur.execute(
        f"""
        SELECT st.id, st.tanggal, a.nama AS nama_anggota, a.no_anggota, a.id AS anggota_id,
               st.jenis, st.arah, st.jumlah, st.keterangan
        FROM v_simpanan_efektif st
        JOIN anggota a ON st.anggota_id = a.id
        {where_klausa_s} {'AND' if where_klausa_s else 'WHERE'} st.status_efektif = 'NORMAL'
        ORDER BY st.tanggal DESC, st.id DESC;
        """,
        params
    )
    for s in cur.fetchall():
        hasil.append({
            "id": s["id"],
            "tanggal": s["tanggal"],
            "entitas": f"{s['nama_anggota']} ({s['no_anggota']})",
            "rincian": f"Simpanan {s['jenis'].capitalize()} ({s['arah'].upper()})",
            "nominal": s["jumlah"],
            "status_info": s["keterangan"] or "-",
            "anggota_id": s["anggota_id"]
        })

    # Pembayaran Angsuran Efektif (hanya NORMAL yang tampil di filter cepat)
    cur.execute(
        f"""
        SELECT pa.id, pa.tanggal, a.nama AS nama_anggota, a.no_anggota, a.id AS anggota_id,
               p.no_pinjaman, (pa.bayar_pokok + pa.bayar_jasa + pa.denda) AS total_bayar,
               pa.keterangan
        FROM v_pembayaran_angsuran_efektif pa
        JOIN pinjaman p ON pa.pinjaman_id = p.id
        JOIN anggota a ON p.anggota_id = a.id
        {where_klausa_a} {'AND' if where_klausa_a else 'WHERE'} pa.status_efektif = 'NORMAL'
        ORDER BY pa.tanggal DESC, pa.id DESC;
        """,
        params
    )
    for p in cur.fetchall():
        hasil.append({
            "id": p["id"],
            "tanggal": p["tanggal"],
            "entitas": f"{p['nama_anggota']} ({p['no_anggota']})",
            "rincian": f"Angsuran Pinjaman {p['no_pinjaman']}",
            "nominal": p["total_bayar"],
            "status_info": p["keterangan"] or "-",
            "anggota_id": p["anggota_id"]
        })

    hasil.sort(key=lambda x: (x["tanggal"], x["id"]), reverse=True)
    return hasil

