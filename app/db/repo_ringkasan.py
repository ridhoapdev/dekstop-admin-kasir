"""
app/db/repo_ringkasan.py — Repositori data untuk Layar Ringkasan (Dashboard Halaman Awal).
Sesuai SPEC.md 4.1 & RULES.md:
- Menghitung simpanan masuk hari ini
- Menghitung angsuran masuk hari ini
- Menghitung pinjaman cair hari ini
- Menghitung posisi saldo kas saat ini = SUM(masuk) - SUM(keluar)
- Menghitung jumlah angsuran jatuh tempo minggu ini (7 hari ke depan)
- Menghitung jumlah anggota menunggak
- Memeriksa status pengingat:
  * "Laporan mingguan belum dibuat" (jika belum ada log laporan untuk minggu terakhir)
  * "Closing bulan ini belum dilakukan" (jika bulan sebelumnya belum di-closing atau sudah akhir bulan)
- Riwayat aktivitas terbaru (log_aktivitas)
"""
import sqlite3
from datetime import date, datetime, timedelta
from typing import Dict, Any, List
from app.db.repo_angsuran import hitung_status_angsuran
from app.logika.transaksi_efektif import hitung_rekap_kas_bersih_rentang


def hitung_saldo_kas_saat_ini(conn: sqlite3.Connection) -> int:
    """Menghitung saldo kas operasional saat ini = SUM(masuk) - SUM(keluar)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(SUM(masuk), 0) - COALESCE(SUM(keluar), 0) AS saldo_kas
        FROM kas_transaksi;
        """
    )
    return cur.fetchone()[0]


def ambil_ringkasan_dashboard(
    conn: sqlite3.Connection, tanggal_patokan_iso: str = None
) -> Dict[str, Any]:
    """
    Mengambil data metrik utama dashboard ringkasan:
    - simpanan_masuk_hari_ini
    - angsuran_masuk_hari_ini
    - pinjaman_cair_hari_ini
    - posisi_kas
    - jumlah_jatuh_tempo_minggu_ini & daftar_pinjaman_tempo
    - jumlah_anggota_menunggak & daftar_anggota_menunggak
    - pengingat_laporan_mingguan (bool)
    - pengingat_closing (bool)
    """
    cur = conn.cursor()
    tgl_hari_ini = tanggal_patokan_iso or date.today().strftime("%Y-%m-%d")
    d_hari_ini = datetime.strptime(tgl_hari_ini, "%Y-%m-%d").date()

    # 1. Metrik Bersih Hari Ini (Satu Sumber Kebenaran)
    rekap_hari_ini = hitung_rekap_kas_bersih_rentang(
        conn, tanggal_awal=tgl_hari_ini, tanggal_akhir=tgl_hari_ini
    )
    simpanan_hari_ini = rekap_hari_ini["simpanan_setor"]
    angsuran_hari_ini = rekap_hari_ini["angsuran_total"]
    pinjaman_cair_hari_ini = rekap_hari_ini["pencairan_pinjaman"]
    biaya_admin_hari_ini = rekap_hari_ini["biaya_admin"]

    # 4. Posisi Kas Saat Ini
    posisi_kas = hitung_saldo_kas_saat_ini(conn)

    # 5. Angsuran Jatuh Tempo Minggu Ini (tgl_hari_ini s/d 7 hari ke depan)
    tgl_akhir_minggu = (d_hari_ini + timedelta(days=7)).strftime("%Y-%m-%d")
    cur.execute(
        """
        SELECT a.id, a.pinjaman_id, a.angsuran_ke, a.jatuh_tempo, a.pokok, a.jasa,
               p.no_pinjaman, ang.id AS anggota_id, ang.nama AS nama_anggota, ang.no_anggota,
               COALESCE(SUM(pa.bayar_pokok), 0) AS terbayar_pokok,
               COALESCE(SUM(pa.bayar_jasa), 0) AS terbayar_jasa
        FROM angsuran a
        JOIN pinjaman p ON a.pinjaman_id = p.id
        JOIN anggota ang ON p.anggota_id = ang.id
        LEFT JOIN v_pembayaran_angsuran_efektif pa ON a.id = pa.angsuran_id AND pa.status_efektif = 'NORMAL'
        WHERE p.status = 'aktif' AND a.jatuh_tempo >= ? AND a.jatuh_tempo <= ?
        GROUP BY a.id;
        """,
        (tgl_hari_ini, tgl_akhir_minggu)
    )
    daftar_tempo = []
    for r in cur.fetchall():
        lunas = (r["terbayar_pokok"] >= r["pokok"]) and (r["terbayar_jasa"] >= r["jasa"])
        if not lunas:
            daftar_tempo.append({
                "angsuran_id": r["id"],
                "pinjaman_id": r["pinjaman_id"],
                "no_pinjaman": r["no_pinjaman"],
                "anggota_id": r["anggota_id"],
                "nama_anggota": r["nama_anggota"],
                "no_anggota": r["no_anggota"],
                "angsuran_ke": r["angsuran_ke"],
                "jatuh_tempo": r["jatuh_tempo"],
                "sisa_tagihan": (r["pokok"] - r["terbayar_pokok"]) + (r["jasa"] - r["terbayar_jasa"])
            })

    # 6. Anggota Menunggak (pinjaman aktif dengan cicilan berstatus 'telat')
    cur.execute(
        """
        SELECT a.id, a.pinjaman_id, a.angsuran_ke, a.jatuh_tempo, a.pokok, a.jasa,
               p.no_pinjaman, ang.id AS anggota_id, ang.nama AS nama_anggota, ang.no_anggota, ang.no_hp,
               COALESCE(SUM(pa.bayar_pokok), 0) AS terbayar_pokok,
               COALESCE(SUM(pa.bayar_jasa), 0) AS terbayar_jasa
        FROM angsuran a
        JOIN pinjaman p ON a.pinjaman_id = p.id
        JOIN anggota ang ON p.anggota_id = ang.id
        LEFT JOIN v_pembayaran_angsuran_efektif pa ON a.id = pa.angsuran_id AND pa.status_efektif = 'NORMAL'
        WHERE p.status = 'aktif' AND a.jatuh_tempo < ?
        GROUP BY a.id;
        """,
        (tgl_hari_ini,)
    )
    tunggakan_per_anggota: Dict[int, Dict[str, Any]] = {}
    for r in cur.fetchall():
        stat = hitung_status_angsuran(
            tagihan_pokok=r["pokok"],
            tagihan_jasa=r["jasa"],
            total_bayar_pokok=r["terbayar_pokok"],
            total_bayar_jasa=r["terbayar_jasa"],
            jatuh_tempo_iso=r["jatuh_tempo"],
            tanggal_patokan_iso=tgl_hari_ini
        )
        if stat == "telat":
            ang_id = r["anggota_id"]
            sisa_tagihan = (r["pokok"] - r["terbayar_pokok"]) + (r["jasa"] - r["terbayar_jasa"])
            if ang_id not in tunggakan_per_anggota:
                tunggakan_per_anggota[ang_id] = {
                    "anggota_id": ang_id,
                    "nama_anggota": r["nama_anggota"],
                    "no_anggota": r["no_anggota"],
                    "no_hp": r["no_hp"] or "-",
                    "jumlah_cicilan_telat": 1,
                    "total_tunggakan": sisa_tagihan,
                    "pinjaman_id": r["pinjaman_id"]
                }
            else:
                tunggakan_per_anggota[ang_id]["jumlah_cicilan_telat"] += 1
                tunggakan_per_anggota[ang_id]["total_tunggakan"] += sisa_tagihan

    daftar_menunggak = list(tunggakan_per_anggota.values())

    # 7. Pengingat: Laporan Mingguan Belum Dibuat
    # Cek log laporan mingguan dalam 7 hari terakhir
    tgl_7_hari_lalu = (d_hari_ini - timedelta(days=7)).strftime("%Y-%m-%d")
    cur.execute(
        """
        SELECT 1 FROM laporan_mingguan_log
        WHERE dibuat_pada >= ? LIMIT 1;
        """,
        (tgl_7_hari_lalu,)
    )
    laporan_mingguan_dibuat = cur.fetchone() is not None
    pengingat_laporan_mingguan = not laporan_mingguan_dibuat

    # 8. Pengingat: Closing Bulan Ini / Bulan Lalu Belum Dilakukan
    # Bulan lalu:
    tahun_lalu = d_hari_ini.year if d_hari_ini.month > 1 else d_hari_ini.year - 1
    bulan_lalu = d_hari_ini.month - 1 if d_hari_ini.month > 1 else 12
    periode_lalu = f"{tahun_lalu:04d}-{bulan_lalu:02d}"

    cur.execute(
        "SELECT 1 FROM closing WHERE periode = ? AND status = 'tertutup' LIMIT 1;",
        (periode_lalu,)
    )
    periode_lalu_ditutup = cur.fetchone() is not None
    pengingat_closing = not periode_lalu_ditutup

    return {
        "simpanan_masuk_hari_ini": simpanan_hari_ini,
        "angsuran_masuk_hari_ini": angsuran_hari_ini,
        "pinjaman_cair_hari_ini": pinjaman_cair_hari_ini,
        "biaya_admin_hari_ini": biaya_admin_hari_ini,
        "posisi_kas": posisi_kas,
        "jumlah_jatuh_tempo_minggu_ini": len(daftar_tempo),
        "daftar_tempo_minggu_ini": daftar_tempo,
        "jumlah_anggota_menunggak": len(daftar_menunggak),
        "daftar_anggota_menunggak": daftar_menunggak,
        "pengingat_laporan_mingguan": pengingat_laporan_mingguan,
        "pengingat_closing": pengingat_closing,
        "periode_lalu_butuh_closing": periode_lalu
    }

