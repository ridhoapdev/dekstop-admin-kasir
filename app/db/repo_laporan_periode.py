"""
app/db/repo_laporan_periode.py — Satu Sumber Kebenaran Data Laporan Bulanan dan Laporan Tahunan.
Memanfaatkan v_simpanan_efektif, v_pembayaran_angsuran_efektif, hitung_rekap_kas_bersih_rentang(),
snapshot closing jika sudah ditutup, atau kalkulasi real-time bertanda 'SEMENTARA' jika belum closing.
Menjamin rekonsiliasi matematis sempurna (saldo awal + masuk - keluar = saldo akhir).
"""
import calendar
import sqlite3
from datetime import date
from typing import Dict, List, Any, Optional, Tuple

from app.logika.transaksi_efektif import (
    hitung_rekap_kas_bersih_rentang,
    ambil_daftar_transaksi_kas_lengkap,
    klasifikasikan_transaksi_kas
)
from app.db.repo_angsuran import hitung_status_angsuran


NAMA_BULAN_INDO = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
]


def ambil_daftar_tahun_tersedia(conn: sqlite3.Connection) -> List[int]:
    """Mengambil daftar tahun unik dari data transaksi koperasi (default memuat tahun berjalan)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT SUBSTR(tanggal, 1, 4) AS thn FROM kas_transaksi WHERE tanggal IS NOT NULL
        UNION
        SELECT DISTINCT SUBSTR(tanggal_cair, 1, 4) AS thn FROM pinjaman WHERE tanggal_cair IS NOT NULL
        UNION
        SELECT DISTINCT SUBSTR(tanggal_masuk, 1, 4) AS thn FROM anggota WHERE tanggal_masuk IS NOT NULL
        ORDER BY thn DESC;
    """)
    thn_list = []
    for r in cur.fetchall():
        if r[0] and str(r[0]).isdigit():
            thn_list.append(int(r[0]))
    thn_sekarang = date.today().year
    if thn_sekarang not in thn_list:
        thn_list.insert(0, thn_sekarang)
    return sorted(list(set(thn_list)), reverse=True)


def ambil_data_laporan_bulanan(
    conn: sqlite3.Connection,
    tahun: int,
    bulan: int,
    sembunyikan_dibatalkan: bool = True
) -> Dict[str, Any]:
    """
    Mengambil data lengkap laporan bulanan:
    1. Status closing (apakah sudah closing atau SEMENTARA)
    2. Arus kas bersih (saldo kas awal, masuk, keluar, saldo kas akhir)
    3. Simpanan per jenis (pokok, wajib, sukarela): setor, tarik, saldo akhir
    4. Pinjaman: jumlah & nominal cair, angsuran pokok masuk, jasa diterima, biaya admin, sisa pokok akhir bulan, pinjaman aktif
    5. Anggota: baru, keluar, total aktif akhir bulan
    6. Tunggakan akhir bulan: jumlah anggota, total nominal, daftar rinci
    7. Koreksi / Pembatalan terpisah
    8. Perbandingan dengan bulan sebelumnya (rupiah & persen, aman dari division by zero)
    9. Daftar transaksi kas rinci
    10. Pemeriksaan rekonsiliasi kas (rekonsiliasi_cocok: bool, pesan_rekonsiliasi: str)
    """
    cur = conn.cursor()
    periode = f"{tahun:04d}-{bulan:02d}"
    _, akhir_hari = calendar.monthrange(tahun, bulan)
    tgl_awal = f"{periode}-01"
    tgl_akhir = f"{periode}-{akhir_hari:02d}"

    # Cek apakah periode ini sudah di-closing (status = 'tertutup')
    cur.execute(
        "SELECT * FROM closing WHERE periode = ? AND status = 'tertutup' LIMIT 1;",
        (periode,)
    )
    closing_row = cur.fetchone()
    sudah_closing = closing_row is not None

    # 1. Arus Kas Bersih (Satu Sumber Kebenaran)
    rekap_kas = hitung_rekap_kas_bersih_rentang(
        conn, tanggal_awal=tgl_awal, tanggal_akhir=tgl_akhir, periode=periode
    )

    saldo_kas_awal = rekap_kas["saldo_kas_awal"]
    total_kas_masuk = rekap_kas["total_kas_masuk"]
    total_kas_keluar = rekap_kas["total_kas_keluar"]
    saldo_kas_akhir = rekap_kas["saldo_kas_akhir"]

    # Validasi rekonsiliasi matematis
    selisih_rekonsiliasi = (saldo_kas_awal + total_kas_masuk - total_kas_keluar) - saldo_kas_akhir
    rekonsiliasi_cocok = (selisih_rekonsiliasi == 0)
    pesan_rekonsiliasi = ""
    if not rekonsiliasi_cocok:
        pesan_rekonsiliasi = (
            f"Perhatian: Terdapat selisih matematis kas sebesar Rp {abs(selisih_rekonsiliasi):,}. "
            "Harap periksa buku kas sebelum melakukan closing."
        ).replace(",", ".")

    # 2. Simpanan per Jenis (pokok, wajib, sukarela)
    # Mutasi setor & tarik dalam bulan ini
    cur.execute("""
        SELECT jenis,
               COALESCE(SUM(CASE WHEN arah = 'setor' THEN jumlah ELSE 0 END), 0) AS setor,
               COALESCE(SUM(CASE WHEN arah = 'tarik' THEN jumlah ELSE 0 END), 0) AS tarik
        FROM v_simpanan_efektif
        WHERE status_efektif = 'NORMAL' AND tanggal >= ? AND tanggal <= ?
        GROUP BY jenis;
    """, (tgl_awal, tgl_akhir))
    mutasi_simpanan = {r["jenis"]: {"setor": r["setor"], "tarik": r["tarik"]} for r in cur.fetchall()}

    # Saldo akumulatif per jenis simpanan per akhir bulan ini
    if sudah_closing:
        cur.execute("""
            SELECT COALESCE(SUM(saldo_pokok), 0) AS pokok,
                   COALESCE(SUM(saldo_wajib), 0) AS wajib,
                   COALESCE(SUM(saldo_sukarela), 0) AS sukarela
            FROM closing_saldo_anggota
            WHERE closing_id = ?;
        """, (closing_row["id"],))
        r_csa = cur.fetchone()
        saldo_akhir_pokok = r_csa["pokok"] if r_csa else 0
        saldo_akhir_wajib = r_csa["wajib"] if r_csa else 0
        saldo_akhir_sukarela = r_csa["sukarela"] if r_csa else 0
    else:
        cur.execute("""
            SELECT jenis,
                   COALESCE(SUM(CASE WHEN arah = 'setor' THEN jumlah ELSE -jumlah END), 0) AS saldo
            FROM v_simpanan_efektif
            WHERE status_efektif = 'NORMAL' AND tanggal <= ?
            GROUP BY jenis;
        """, (tgl_akhir,))
        s_map = {r["jenis"]: r["saldo"] for r in cur.fetchall()}
        saldo_akhir_pokok = s_map.get("pokok", 0)
        saldo_akhir_wajib = s_map.get("wajib", 0)
        saldo_akhir_sukarela = s_map.get("sukarela", 0)

    simpanan_rincian = {
        "pokok": {
            "setor": mutasi_simpanan.get("pokok", {}).get("setor", 0),
            "tarik": mutasi_simpanan.get("pokok", {}).get("tarik", 0),
            "saldo_akhir": saldo_akhir_pokok
        },
        "wajib": {
            "setor": mutasi_simpanan.get("wajib", {}).get("setor", 0),
            "tarik": mutasi_simpanan.get("wajib", {}).get("tarik", 0),
            "saldo_akhir": saldo_akhir_wajib
        },
        "sukarela": {
            "setor": mutasi_simpanan.get("sukarela", {}).get("setor", 0),
            "tarik": mutasi_simpanan.get("sukarela", {}).get("tarik", 0),
            "saldo_akhir": saldo_akhir_sukarela
        },
        "total": {
            "setor": (
                mutasi_simpanan.get("pokok", {}).get("setor", 0) +
                mutasi_simpanan.get("wajib", {}).get("setor", 0) +
                mutasi_simpanan.get("sukarela", {}).get("setor", 0)
            ),
            "tarik": (
                mutasi_simpanan.get("pokok", {}).get("tarik", 0) +
                mutasi_simpanan.get("wajib", {}).get("tarik", 0) +
                mutasi_simpanan.get("sukarela", {}).get("tarik", 0)
            ),
            "saldo_akhir": saldo_akhir_pokok + saldo_akhir_wajib + saldo_akhir_sukarela
        }
    }

    # 3. Pinjaman
    # a. Pinjaman yang dicairkan dalam bulan ini
    cur.execute("""
        SELECT COUNT(id) AS jml, COALESCE(SUM(plafon), 0) AS total_plafon, COALESCE(SUM(biaya_admin), 0) AS total_admin
        FROM pinjaman
        WHERE tanggal_cair >= ? AND tanggal_cair <= ? AND status IN ('aktif', 'lunas');
    """, (tgl_awal, tgl_akhir))
    r_cair = cur.fetchone()
    pinjaman_cair_jml = r_cair["jml"] if r_cair else 0
    pinjaman_cair_nominal = r_cair["total_plafon"] if r_cair else 0
    biaya_admin_bulan = r_cair["total_admin"] if r_cair else 0

    # b. Angsuran pokok & jasa yang masuk bulan ini (dari rekap kas terpusat)
    angsuran_pokok_masuk = rekap_kas["angsuran_pokok"]
    angsuran_jasa_masuk = rekap_kas["angsuran_jasa"]

    # c. Sisa pokok pinjaman akhir bulan dan pinjaman aktif
    if sudah_closing:
        cur.execute("""
            SELECT COALESCE(SUM(sisa_pokok_pinjaman), 0) AS sisa_pokok,
                   COUNT(CASE WHEN sisa_pokok_pinjaman > 0 THEN 1 END) AS jml_aktif
            FROM closing_saldo_anggota
            WHERE closing_id = ?;
        """, (closing_row["id"],))
        r_csp = cur.fetchone()
        sisa_pokok_akhir_bulan = r_csp["sisa_pokok"] if r_csp else 0
        pinjaman_aktif_jml = r_csp["jml_aktif"] if r_csp else 0
    else:
        # Hitung real-time dari pinjaman yang cair sebelum/pada akhir bulan
        cur.execute("""
            SELECT p.id, p.plafon,
                   COALESCE(SUM(pa.bayar_pokok), 0) AS total_bayar_pokok
            FROM pinjaman p
            LEFT JOIN v_pembayaran_angsuran_efektif pa ON p.id = pa.pinjaman_id
                 AND pa.status_efektif = 'NORMAL' AND pa.tanggal <= ?
            WHERE p.tanggal_cair <= ? AND p.status IN ('aktif', 'lunas')
            GROUP BY p.id;
        """, (tgl_akhir, tgl_akhir))
        sisa_pokok_akhir_bulan = 0
        pinjaman_aktif_jml = 0
        for r_p in cur.fetchall():
            sisa = max(0, r_p["plafon"] - r_p["total_bayar_pokok"])
            if sisa > 0:
                sisa_pokok_akhir_bulan += sisa
                pinjaman_aktif_jml += 1

    pinjaman_rincian = {
        "cair_jumlah": pinjaman_cair_jml,
        "cair_nominal": pinjaman_cair_nominal,
        "angsuran_pokok": angsuran_pokok_masuk,
        "jasa_diterima": angsuran_jasa_masuk,
        "biaya_admin": biaya_admin_bulan,
        "sisa_pokok_akhir": sisa_pokok_akhir_bulan,
        "pinjaman_aktif_jumlah": pinjaman_aktif_jml
    }

    # 4. Anggota
    cur.execute("""
        SELECT COUNT(id) FROM anggota
        WHERE tanggal_masuk >= ? AND tanggal_masuk <= ?;
    """, (tgl_awal, tgl_akhir))
    anggota_baru = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(id) FROM anggota
        WHERE tanggal_keluar >= ? AND tanggal_keluar <= ? AND status = 'keluar';
    """, (tgl_awal, tgl_akhir))
    anggota_keluar = cur.fetchone()[0]

    # Total anggota aktif pada akhir bulan
    cur.execute("""
        SELECT COUNT(id) FROM anggota
        WHERE tanggal_masuk <= ? AND (status = 'aktif' OR tanggal_keluar > ?);
    """, (tgl_akhir, tgl_akhir))
    anggota_aktif_akhir = cur.fetchone()[0]

    anggota_rincian = {
        "baru": anggota_baru,
        "keluar": anggota_keluar,
        "aktif_akhir": anggota_aktif_akhir
    }

    # 5. Tunggakan Akhir Bulan (jatuh tempo < akhir bulan, belum lunas)
    cur.execute("""
        SELECT a.id, a.pinjaman_id, a.angsuran_ke, a.jatuh_tempo, a.pokok, a.jasa,
               p.no_pinjaman, ang.id AS anggota_id, ang.nama AS nama_anggota, ang.no_anggota, ang.unit,
               COALESCE(SUM(pa.bayar_pokok), 0) AS terbayar_pokok,
               COALESCE(SUM(pa.bayar_jasa), 0) AS terbayar_jasa
        FROM angsuran a
        JOIN pinjaman p ON a.pinjaman_id = p.id
        JOIN anggota ang ON p.anggota_id = ang.id
        LEFT JOIN v_pembayaran_angsuran_efektif pa ON a.id = pa.angsuran_id
             AND pa.status_efektif = 'NORMAL' AND pa.tanggal <= ?
        WHERE p.tanggal_cair <= ? AND a.jatuh_tempo <= ?
        GROUP BY a.id;
    """, (tgl_akhir, tgl_akhir, tgl_akhir))

    tunggakan_dict: Dict[int, Dict[str, Any]] = {}
    for r in cur.fetchall():
        stat = hitung_status_angsuran(
            tagihan_pokok=r["pokok"],
            tagihan_jasa=r["jasa"],
            total_bayar_pokok=r["terbayar_pokok"],
            total_bayar_jasa=r["terbayar_jasa"],
            jatuh_tempo_iso=r["jatuh_tempo"],
            tanggal_patokan_iso=tgl_akhir
        )
        if stat == "telat":
            ang_id = r["anggota_id"]
            sisa_tagihan = (r["pokok"] - r["terbayar_pokok"]) + (r["jasa"] - r["terbayar_jasa"])
            if ang_id not in tunggakan_dict:
                tunggakan_dict[ang_id] = {
                    "anggota_id": ang_id,
                    "nama_anggota": r["nama_anggota"],
                    "no_anggota": r["no_anggota"],
                    "unit": r["unit"] or "-",
                    "jumlah_cicilan_telat": 1,
                    "total_tunggakan": sisa_tagihan,
                    "no_pinjaman": r["no_pinjaman"]
                }
            else:
                tunggakan_dict[ang_id]["jumlah_cicilan_telat"] += 1
                tunggakan_dict[ang_id]["total_tunggakan"] += sisa_tagihan

    daftar_tunggakan = list(tunggakan_dict.values())
    total_nominal_tunggakan = sum(item["total_tunggakan"] for item in daftar_tunggakan)

    tunggakan_rincian = {
        "jumlah_anggota": len(daftar_tunggakan),
        "total_nominal": total_nominal_tunggakan,
        "daftar": daftar_tunggakan
    }

    # 6. Koreksi / Pembatalan
    koreksi_rincian = {
        "jumlah": rekap_kas["jumlah_koreksi_lintas"],
        "masuk": rekap_kas["koreksi_masuk_lintas"],
        "keluar": rekap_kas["koreksi_keluar_lintas"]
    }

    # 7. Perbandingan dengan Bulan Sebelumnya
    thn_prev = tahun if bulan > 1 else tahun - 1
    bln_prev = bulan - 1 if bulan > 1 else 12
    periode_prev = f"{thn_prev:04d}-{bln_prev:02d}"
    _, akhir_hari_prev = calendar.monthrange(thn_prev, bln_prev)
    tgl_awal_prev = f"{periode_prev}-01"
    tgl_akhir_prev = f"{periode_prev}-{akhir_hari_prev:02d}"

    rekap_prev = hitung_rekap_kas_bersih_rentang(
        conn, tanggal_awal=tgl_awal_prev, tanggal_akhir=tgl_akhir_prev, periode=periode_prev
    )

    def hitung_perbandingan(kini: int, lalu: int) -> Dict[str, Any]:
        selisih = kini - lalu
        if lalu == 0:
            persen_str = "-"
        else:
            pct = (selisih / lalu) * 100.0
            persen_str = f"{pct:+.1f}%"
        return {"kini": kini, "lalu": lalu, "selisih": selisih, "persen_str": persen_str}

    perbandingan = {
        "kas_masuk": hitung_perbandingan(total_kas_masuk, rekap_prev["total_kas_masuk"]),
        "kas_keluar": hitung_perbandingan(total_kas_keluar, rekap_prev["total_kas_keluar"]),
        "simpanan": hitung_perbandingan(simpanan_rincian["total"]["setor"], rekap_prev["simpanan_setor"]),
        "pinjaman_cair": hitung_perbandingan(pinjaman_cair_nominal, rekap_prev["pencairan_pinjaman"]),
        "jasa_diterima": hitung_perbandingan(angsuran_jasa_masuk, rekap_prev["angsuran_jasa"])
    }

    # 8. Daftar Transaksi Kas Rinci
    transaksi_rinci = ambil_daftar_transaksi_kas_lengkap(
        conn, tanggal_awal=tgl_awal, tanggal_akhir=tgl_akhir, sembunyikan_dibatalkan=sembunyikan_dibatalkan
    )

    return {
        "tahun": tahun,
        "bulan": bulan,
        "periode": periode,
        "nama_bulan": NAMA_BULAN_INDO[bulan],
        "tanggal_awal": tgl_awal,
        "tanggal_akhir": tgl_akhir,
        "sudah_closing": sudah_closing,
        "status_label": "TUTUP BUKU (FINAL)" if sudah_closing else "SEMENTARA (belum closing)",
        "saldo_kas_awal": saldo_kas_awal,
        "total_kas_masuk": total_kas_masuk,
        "total_kas_keluar": total_kas_keluar,
        "saldo_kas_akhir": saldo_kas_akhir,
        "rekonsiliasi_cocok": rekonsiliasi_cocok,
        "pesan_rekonsiliasi": pesan_rekonsiliasi,
        "simpanan": simpanan_rincian,
        "pinjaman": pinjaman_rincian,
        "anggota": anggota_rincian,
        "tunggakan": tunggakan_rincian,
        "koreksi": koreksi_rincian,
        "perbandingan": perbandingan,
        "transaksi_rinci": transaksi_rinci
    }


def ambil_data_laporan_tahunan(
    conn: sqlite3.Connection,
    tahun: int
) -> Dict[str, Any]:
    """
    Mengambil data lengkap laporan tahunan:
    1. Tabel 12 bulan (Januari - Desember)
    2. Baris total setahun
    3. Posisi akhir tahun: total simpanan per jenis, pinjaman beredar, total tunggakan,
       anggota aktif akhir tahun, anggota baru dan keluar selama tahun tersebut
    4. Indikator bulan-bulan yang belum closing ("Ada X bulan belum closing: ...")
    5. Rekonsiliasi matematis konsisten (saldo akhir bulan N == saldo awal bulan N+1)
    """
    cur = conn.cursor()
    daftar_bulan_data: List[Dict[str, Any]] = []
    bulan_belum_closing: List[str] = []

    # Akumulator Tahunan
    tot_kas_masuk = 0
    tot_kas_keluar = 0
    tot_simpanan_masuk = 0
    tot_pinjaman_cair = 0
    tot_jasa_diterima = 0

    saldo_awal_tahun = 0
    saldo_akhir_tahun = 0

    for b in range(1, 13):
        bln_data = ambil_data_laporan_bulanan(conn, tahun, b, sembunyikan_dibatalkan=True)
        if b == 1:
            saldo_awal_tahun = bln_data["saldo_kas_awal"]
        if b == 12:
            saldo_akhir_tahun = bln_data["saldo_kas_akhir"]

        if not bln_data["sudah_closing"]:
            bulan_belum_closing.append(f"{NAMA_BULAN_INDO[b]} {tahun}")

        tot_kas_masuk += bln_data["total_kas_masuk"]
        tot_kas_keluar += bln_data["total_kas_keluar"]
        tot_simpanan_masuk += bln_data["simpanan"]["total"]["setor"]
        tot_pinjaman_cair += bln_data["pinjaman"]["cair_nominal"]
        tot_jasa_diterima += bln_data["pinjaman"]["jasa_diterima"]

        daftar_bulan_data.append({
            "bulan": b,
            "nama_bulan": NAMA_BULAN_INDO[b],
            "periode": bln_data["periode"],
            "sudah_closing": bln_data["sudah_closing"],
            "status_label": "Final" if bln_data["sudah_closing"] else "Sementara",
            "saldo_kas_awal": bln_data["saldo_kas_awal"],
            "kas_masuk": bln_data["total_kas_masuk"],
            "kas_keluar": bln_data["total_kas_keluar"],
            "saldo_kas_akhir": bln_data["saldo_kas_akhir"],
            "simpanan_masuk": bln_data["simpanan"]["total"]["setor"],
            "pinjaman_cair": bln_data["pinjaman"]["cair_nominal"],
            "jasa_diterima": bln_data["pinjaman"]["jasa_diterima"],
            "sisa_pokok": bln_data["pinjaman"]["sisa_pokok_akhir"]
        })

    # Cek konsistensi saldo awal bulan N+1 == saldo akhir bulan N
    rekonsiliasi_tahunan_cocok = True
    for i in range(11):
        if daftar_bulan_data[i]["saldo_kas_akhir"] != daftar_bulan_data[i + 1]["saldo_kas_awal"]:
            rekonsiliasi_tahunan_cocok = False
            break

    # Posisi Akhir Tahun (per 31 Desember tahun tersebut)
    data_desember = daftar_bulan_data[11]
    tgl_akhir_tahun = f"{tahun:04d}-12-31"
    tgl_awal_tahun = f"{tahun:04d}-01-01"

    # Total Simpanan per akhir tahun
    des_data = ambil_data_laporan_bulanan(conn, tahun, 12)
    posisi_simpanan = des_data["simpanan"]

    # Total Pinjaman Beredar (Sisa Pokok) & Tunggakan Akhir Tahun
    sisa_pokok_akhir_tahun = des_data["pinjaman"]["sisa_pokok_akhir"]
    tunggakan_akhir_tahun = des_data["tunggakan"]["total_nominal"]

    # Anggota selama tahun ini
    cur.execute("""
        SELECT COUNT(id) FROM anggota
        WHERE tanggal_masuk >= ? AND tanggal_masuk <= ?;
    """, (tgl_awal_tahun, tgl_akhir_tahun))
    anggota_baru_tahun = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(id) FROM anggota
        WHERE tanggal_keluar >= ? AND tanggal_keluar <= ? AND status = 'keluar';
    """, (tgl_awal_tahun, tgl_akhir_tahun))
    anggota_keluar_tahun = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(id) FROM anggota
        WHERE tanggal_masuk <= ? AND (status = 'aktif' OR tanggal_keluar > ?);
    """, (tgl_akhir_tahun, tgl_akhir_tahun))
    anggota_aktif_akhir_tahun = cur.fetchone()[0]

    ringkasan_tahunan = {
        "tahun": tahun,
        "saldo_kas_awal": saldo_awal_tahun,
        "total_kas_masuk": tot_kas_masuk,
        "total_kas_keluar": tot_kas_keluar,
        "saldo_kas_akhir": saldo_akhir_tahun,
        "total_simpanan_masuk": tot_simpanan_masuk,
        "total_pinjaman_cair": tot_pinjaman_cair,
        "total_jasa_diterima": tot_jasa_diterima,
        "sisa_pokok_akhir": sisa_pokok_akhir_tahun,
        "total_tunggakan_akhir": tunggakan_akhir_tahun,
        "posisi_simpanan": posisi_simpanan,
        "anggota_baru": anggota_baru_tahun,
        "anggota_keluar": anggota_keluar_tahun,
        "anggota_aktif_akhir": anggota_aktif_akhir_tahun,
        "bulan_belum_closing": bulan_belum_closing,
        "rekonsiliasi_tahunan_cocok": rekonsiliasi_tahunan_cocok,
        "tabel_12_bulan": daftar_bulan_data
    }

    return ringkasan_tahunan
