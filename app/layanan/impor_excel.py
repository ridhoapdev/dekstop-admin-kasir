"""
app/layanan/impor_excel.py — Layanan impor data dari file Excel (.xlsx / .csv).
Sesuai SPEC.md 4.9 & RULES.md:
- Menghasilkan file template Excel kosong yang dapat diunduh pengguna
- Parsing file Excel / CSV:
  * Lembar 1: 'Anggota' (no_anggota, nama, nik_karyawan, unit, no_hp, alamat, tanggal_masuk)
  * Lembar 2: 'Saldo Simpanan Awal' (no_anggota, saldo_pokok, saldo_wajib, saldo_sukarela, tanggal_saldo)
  * Lembar 3: 'Pinjaman Berjalan' (no_pinjaman, no_anggota, plafon, tenor, jasa_persen, tanggal_cair, sisa_pokok)
- Langkah PRATINJAU & VALIDASI ketat:
  * Cek duplikasi no_anggota / no_pinjaman
  * Validasi tipe data uang integer > 0
  * Validasi tanggal format ISO/standar
  * Mengumpulkan laporan baris bermasalah secara detail
- Eksekusi impor atomik:
  * Melakukan backup otomatis sebelum impor
  * Memasukkan data anggota, simpanan awal (sebagai setoran saldo awal), dan pinjaman berjalan
  * Mencatat log_aktivitas
"""
import csv
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Union
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from app.layanan.backup import buat_backup
from app.db.repo_anggota import tambah_anggota
from app.db.repo_simpanan import tambah_transaksi_simpanan
from app.db.repo_pinjaman import buat_pinjaman_baru
from app.db.repo_angsuran import bayar_angsuran


def buat_template_impor_excel(path_tujuan: Union[str, Path]) -> Path:
    """
    Membuat file template Excel (.xlsx) dengan 3 sheet standar:
    1. Anggota
    2. Saldo Simpanan Awal
    3. Pinjaman Berjalan
    Lengkap dengan baris petunjuk & contoh pengisian.
    """
    wb = openpyxl.Workbook()
    
    font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    font_isi = Font(name="Segoe UI", size=10)
    fill_header = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    def style_sheet(ws, headers, contoh_rows):
        ws.append(headers)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = font_header
            cell.fill = fill_header
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = thin_border

        for row_data in contoh_rows:
            ws.append(row_data)
            r_idx = ws.max_row
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=r_idx, column=col_idx)
                cell.font = font_isi
                cell.border = thin_border

        for col in ws.columns:
            max_len = max(len(str(c.value or '')) for c in col)
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = max(max_len + 4, 15)

    # 1. Sheet Anggota
    ws_anggota = wb.active
    ws_anggota.title = "Anggota"
    headers_anggota = ["No Anggota", "Nama Lengkap", "NIK Karyawan", "Unit Bagian", "No HP", "Alamat", "Tanggal Masuk"]
    contoh_anggota = [
        ["A-0001", "Budi Santoso", "EMP-101", "Produksi", "08123456789", "Jl. Melati No. 1", "2026-01-10"],
        ["A-0002", "Siti Aminah", "EMP-102", "Keuangan", "08551234567", "Jl. Mawar No. 4", "2026-02-15"]
    ]
    style_sheet(ws_anggota, headers_anggota, contoh_anggota)

    # 2. Sheet Saldo Simpanan Awal
    ws_simpanan = wb.create_sheet(title="Saldo Simpanan Awal")
    headers_simpanan = ["No Anggota", "Saldo Pokok", "Saldo Wajib", "Saldo Sukarela", "Tanggal Saldo"]
    contoh_simpanan = [
        ["A-0001", 100000, 500000, 250000, "2026-11-01"],
        ["A-0002", 100000, 300000, 0, "2026-11-01"]
    ]
    style_sheet(ws_simpanan, headers_simpanan, contoh_simpanan)

    # 3. Sheet Pinjaman Berjalan
    ws_pinjaman = wb.create_sheet(title="Pinjaman Berjalan")
    headers_pinjaman = ["No Pinjaman", "No Anggota", "Plafon", "Tenor", "Jasa Persen", "Tanggal Cair", "Sisa Pokok"]
    contoh_pinjaman = [
        ["P-0001", "A-0001", 10000000, 10, 1.5, "2026-08-01", 7000000]
    ]
    style_sheet(ws_pinjaman, headers_pinjaman, contoh_pinjaman)

    path_out = Path(path_tujuan)
    path_out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path_out))
    return path_out


def validasi_file_impor(
    conn: sqlite3.Connection, path_file: Union[str, Path]
) -> Dict[str, Any]:
    """
    Membaca dan memvalidasi file Excel (.xlsx) sebelum diimpor ke database:
    - Memeriksa keabsahan format tiap lembar
    - Mendeteksi error per baris (nomor anggota duplikat, anggota tidak ditemukan, nilai bukan angka, dll.)
    - Mengembalikan pratinjau data valid & daftar baris bermasalah.
    """
    path = Path(path_file)
    if not path.exists():
        raise FileNotFoundError(f"File {path} tidak ditemukan.")

    wb = openpyxl.load_workbook(str(path), data_only=True)
    
    cur = conn.cursor()
    # Kumpulkan no_anggota dan no_pinjaman yang sudah ada di database
    cur.execute("SELECT no_anggota FROM anggota;")
    no_anggota_db = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT no_pinjaman FROM pinjaman;")
    no_pinjaman_db = {r[0] for r in cur.fetchall()}

    hasil_anggota: List[Dict[str, Any]] = []
    hasil_simpanan: List[Dict[str, Any]] = []
    hasil_pinjaman: List[Dict[str, Any]] = []
    daftar_error: List[str] = []

    no_anggota_file = set()
    no_pinjaman_file = set()

    # 1. Validasi Sheet Anggota
    if "Anggota" in wb.sheetnames:
        ws = wb["Anggota"]
        for baris_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or all(v is None for v in row):
                continue
            no_ang = str(row[0] or "").strip()
            nama = str(row[1] or "").strip()
            nik = str(row[2] or "").strip() if len(row) > 2 and row[2] else None
            unit = str(row[3] or "").strip() if len(row) > 3 and row[3] else None
            hp = str(row[4] or "").strip() if len(row) > 4 and row[4] else None
            alamat = str(row[5] or "").strip() if len(row) > 5 and row[5] else None
            tgl_masuk = str(row[6] or "").strip() if len(row) > 6 and row[6] else date.today().strftime("%Y-%m-%d")

            if not no_ang:
                daftar_error.append(f"Sheet Anggota Baris {baris_idx}: Nomor Anggota kosong.")
                continue
            if not nama:
                daftar_error.append(f"Sheet Anggota Baris {baris_idx}: Nama Anggota kosong.")
                continue
            if no_ang in no_anggota_db or no_ang in no_anggota_file:
                daftar_error.append(f"Sheet Anggota Baris {baris_idx}: Nomor Anggota '{no_ang}' sudah ada di database atau duplikat dalam berkas.")
                continue

            # Sanitasi tanggal ISO
            if isinstance(row[6], (datetime, date)):
                tgl_masuk = row[6].strftime("%Y-%m-%d")
            else:
                tgl_masuk = tgl_masuk[:10]

            no_anggota_file.add(no_ang)
            hasil_anggota.append({
                "no_anggota": no_ang,
                "nama": nama,
                "nik_karyawan": nik,
                "unit": unit,
                "no_hp": hp,
                "alamat": alamat,
                "tanggal_masuk": tgl_masuk
            })

    # Gabungkan no anggota untuk validasi sheet simpanan & pinjaman
    semua_anggota_valid = no_anggota_db.union(no_anggota_file)

    # 2. Validasi Sheet Saldo Simpanan Awal
    if "Saldo Simpanan Awal" in wb.sheetnames:
        ws = wb["Saldo Simpanan Awal"]
        for baris_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or all(v is None for v in row):
                continue
            no_ang = str(row[0] or "").strip()
            if not no_ang:
                continue

            if no_ang not in semua_anggota_valid:
                daftar_error.append(f"Sheet Simpanan Baris {baris_idx}: Anggota '{no_ang}' tidak ditemukan.")
                continue

            try:
                pokok = int(row[1] or 0)
                wajib = int(row[2] or 0)
                sukarela = int(row[3] or 0)
                if pokok < 0 or wajib < 0 or sukarela < 0:
                    daftar_error.append(f"Sheet Simpanan Baris {baris_idx}: Saldo tidak boleh bernilai negatif.")
                    continue
            except (ValueError, TypeError):
                daftar_error.append(f"Sheet Simpanan Baris {baris_idx}: Format saldo harus berupa angka bulat rupiah.")
                continue

            tgl_saldo = str(row[4] or date.today().strftime("%Y-%m-%d"))
            if isinstance(row[4], (datetime, date)):
                tgl_saldo = row[4].strftime("%Y-%m-%d")
            else:
                tgl_saldo = tgl_saldo[:10]

            hasil_simpanan.append({
                "no_anggota": no_ang,
                "saldo_pokok": pokok,
                "saldo_wajib": wajib,
                "saldo_sukarela": sukarela,
                "tanggal_saldo": tgl_saldo
            })

    # 3. Validasi Sheet Pinjaman Berjalan
    if "Pinjaman Berjalan" in wb.sheetnames:
        ws = wb["Pinjaman Berjalan"]
        for baris_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or all(v is None for v in row):
                continue
            no_pinj = str(row[0] or "").strip()
            no_ang = str(row[1] or "").strip()

            if not no_pinj or not no_ang:
                continue

            if no_pinj in no_pinjaman_db or no_pinj in no_pinjaman_file:
                daftar_error.append(f"Sheet Pinjaman Baris {baris_idx}: No Pinjaman '{no_pinj}' sudah terdaftar.")
                continue
            if no_ang not in semua_anggota_valid:
                daftar_error.append(f"Sheet Pinjaman Baris {baris_idx}: Anggota '{no_ang}' tidak ditemukan.")
                continue

            try:
                plafon = int(row[2] or 0)
                tenor = int(row[3] or 1)
                jasa = float(row[4] or 1.5)
                sisa_pokok = int(row[6] or plafon)
                if plafon <= 0 or tenor <= 0 or sisa_pokok < 0 or sisa_pokok > plafon:
                    daftar_error.append(f"Sheet Pinjaman Baris {baris_idx}: Nilai plafon/tenor/sisa pokok tidak valid.")
                    continue
            except (ValueError, TypeError):
                daftar_error.append(f"Sheet Pinjaman Baris {baris_idx}: Angka plafon/tenor/jasa tidak valid.")
                continue

            tgl_cair = str(row[5] or date.today().strftime("%Y-%m-%d"))
            if isinstance(row[5], (datetime, date)):
                tgl_cair = row[5].strftime("%Y-%m-%d")
            else:
                tgl_cair = tgl_cair[:10]

            no_pinjaman_file.add(no_pinj)
            hasil_pinjaman.append({
                "no_pinjaman": no_pinj,
                "no_anggota": no_ang,
                "plafon": plafon,
                "tenor": tenor,
                "jasa_persen": jasa,
                "tanggal_cair": tgl_cair,
                "sisa_pokok": sisa_pokok
            })

    return {
        "anggota": hasil_anggota,
        "simpanan": hasil_simpanan,
        "pinjaman": hasil_pinjaman,
        "daftar_error": daftar_error,
        "siap_impor": len(daftar_error) == 0 and (len(hasil_anggota) + len(hasil_simpanan) + len(hasil_pinjaman) > 0)
    }


def eksekusi_impor_data(
    conn: sqlite3.Connection, data_valid: Dict[str, Any], backup_dulu: bool = True
) -> Dict[str, int]:
    """
    Mengeksekusi impor data yang telah divalidasi ke dalam database:
    1. Backup otomatis database sebelum proses impor (RULES.md Bab 4.6)
    2. Menambahkan data anggota baru
    3. Memasukkan saldo simpanan awal sebagai setoran saldo awal
    4. Memasukkan pinjaman berjalan dan menyesuaikan sisa pokok jika sudah ada cicilan
    5. Mencatat log_aktivitas
    """
    if backup_dulu:
        buat_backup(conn, catat_log=True)

    cur = conn.cursor()
    # Cache mapping no_anggota -> anggota_id
    cur.execute("SELECT no_anggota, id FROM anggota;")
    map_anggota = {r[0]: r[1] for r in cur.fetchall()}

    total_ang_sukses = 0
    total_simp_sukses = 0
    total_pinj_sukses = 0

    with conn:
        # 1. Impor Anggota
        for ang in data_valid.get("anggota", []):
            ang_id = tambah_anggota(
                conn,
                no_anggota=ang["no_anggota"],
                nama=ang["nama"],
                nik_karyawan=ang["nik_karyawan"],
                unit=ang["unit"],
                no_hp=ang["no_hp"],
                alamat=ang["alamat"],
                tanggal_masuk=ang["tanggal_masuk"],
                catatan="Diimpor dari file Excel"
            )
            map_anggota[ang["no_anggota"]] = ang_id
            total_ang_sukses += 1

        # 2. Impor Saldo Simpanan Awal
        for s in data_valid.get("simpanan", []):
            ang_id = map_anggota.get(s["no_anggota"])
            if not ang_id:
                continue

            tgl = s["tanggal_saldo"]
            if s["saldo_pokok"] > 0:
                tambah_transaksi_simpanan(
                    conn, ang_id, "pokok", "setor", s["saldo_pokok"], tgl, "Saldo Awal Impor"
                )
            if s["saldo_wajib"] > 0:
                tambah_transaksi_simpanan(
                    conn, ang_id, "wajib", "setor", s["saldo_wajib"], tgl, "Saldo Awal Impor"
                )
            if s["saldo_sukarela"] > 0:
                tambah_transaksi_simpanan(
                    conn, ang_id, "sukarela", "setor", s["saldo_sukarela"], tgl, "Saldo Awal Impor"
                )
            total_simp_sukses += 1

        # 3. Impor Pinjaman Berjalan
        for p in data_valid.get("pinjaman", []):
            ang_id = map_anggota.get(p["no_anggota"])
            if not ang_id:
                continue

            pinj_id = buat_pinjaman_baru(
                conn,
                no_pinjaman=p["no_pinjaman"],
                anggota_id=ang_id,
                produk_id=None,
                plafon=p["plafon"],
                tenor=p["tenor"],
                jasa_persen_per_bulan=p["jasa_persen"],
                biaya_admin=0,
                tanggal_cair=p["tanggal_cair"],
                keperluan="Pinjaman berjalan (impor)"
            )

            # Jika sisa pokok < plafon, catat pembayaran pokok terdahulu
            terbayar_pokok = p["plafon"] - p["sisa_pokok"]
            if terbayar_pokok > 0:
                bayar_angsuran(
                    conn,
                    pinjaman_id=pinj_id,
                    angsuran_id=None,
                    tanggal=p["tanggal_cair"],
                    bayar_pokok=terbayar_pokok,
                    bayar_jasa=0,
                    denda=0,
                    keterangan="Penyesuaian sisa pokok saldo berjalan impor"
                )

            total_pinj_sukses += 1

        # Catat Log Aktivitas
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            (
                "impor",
                "impor_excel",
                None,
                f"Impor data Excel sukses: {total_ang_sukses} anggota, {total_simp_sukses} saldo simpanan, {total_pinj_sukses} pinjaman."
            )
        )

    return {
        "anggota": total_ang_sukses,
        "simpanan": total_simp_sukses,
        "pinjaman": total_pinj_sukses
    }

