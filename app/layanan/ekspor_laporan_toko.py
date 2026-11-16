"""
app/layanan/ekspor_laporan_toko.py — Layanan Ekspor Laporan Unit Toko ke Excel (.xlsx) dan PDF (.pdf):
- Ekspor Rekapitulasi per Barang
- Ekspor Rincian Transaksi
- Ekspor Laporan Tahunan Toko
- Ekspor Hasil Stock Opname
Format angka asli (bukan teks), mata uang Rupiah, header identitas koperasi, dan styling bersih.
"""
import os
from datetime import datetime, date
from typing import List, Dict, Any, Optional

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.util.format import format_rupiah, format_tanggal_indo


def _border_tipis():
    thin = Side(border_style="thin", color="CBD5E1")
    return Border(top=thin, left=thin, right=thin, bottom=thin)


def ekspor_rekap_barang_excel(
    daftar_rekap: List[Dict[str, Any]],
    ringkasan_keuangan: Dict[str, Any],
    periode_label: str,
    path_output: str,
    nama_koperasi: str = "Koperasi Karyawan"
) -> str:
    """Mengekspor Rekapitulasi Barang ke file Excel."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Rekap Barang"
    ws.views.sheetView[0].showGridLines = True

    # Header Dokumen
    ws.merge_cells("A1:K1")
    ws["A1"] = nama_koperasi.upper()
    ws["A1"].font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center")

    ws.merge_cells("A2:K2")
    ws["A2"] = f"LAPORAN REKAPITULASI PENJUALAN DAN PERSEDIAAN BARANG — {periode_label.upper()}"
    ws["A2"].font = Font(name="Calibri", size=11, bold=True, color="334155")

    ws.merge_cells("A3:K3")
    ws["A3"] = f"Dicetak pada: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    ws["A3"].font = Font(name="Calibri", size=9, italic=True, color="64748B")

    # Tabel Kolom Header
    headers = [
        "No", "Kode", "Nama Barang", "Satuan", "Awal", "Masuk", "Keluar",
        "Penyesuaian", "Akhir", "Total Penjualan", "HPP", "Laba Kotor", "Margin"
    ]
    baris_h = 5
    for col_idx, text in enumerate(headers, 1):
        cell = ws.cell(row=baris_h, column=col_idx, value=text)
        cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _border_tipis()

    # Isi Data
    baris_curr = 6
    for idx, r in enumerate(daftar_rekap, 1):
        ws.cell(row=baris_curr, column=1, value=idx).alignment = Alignment(horizontal="center")
        ws.cell(row=baris_curr, column=2, value=r["kode"]).alignment = Alignment(horizontal="left")
        ws.cell(row=baris_curr, column=3, value=r["nama"]).alignment = Alignment(horizontal="left")
        ws.cell(row=baris_curr, column=4, value=r["satuan_dasar"]).alignment = Alignment(horizontal="center")
        
        c_awal = ws.cell(row=baris_curr, column=5, value=r["stok_awal"])
        c_awal.number_format = '#,##0'
        c_masuk = ws.cell(row=baris_curr, column=6, value=r["masuk"])
        c_masuk.number_format = '#,##0'
        c_keluar = ws.cell(row=baris_curr, column=7, value=r["keluar"])
        c_keluar.number_format = '#,##0'
        c_peny = ws.cell(row=baris_curr, column=8, value=r["penyesuaian"])
        c_peny.number_format = '#,##0'
        c_akhir = ws.cell(row=baris_curr, column=9, value=r["stok_akhir"])
        c_akhir.number_format = '#,##0'

        c_jual = ws.cell(row=baris_curr, column=10, value=r["total_penjualan"])
        c_jual.number_format = '#,##0'
        c_hpp = ws.cell(row=baris_curr, column=11, value=r["total_hpp"])
        c_hpp.number_format = '#,##0'
        c_laba = ws.cell(row=baris_curr, column=12, value=r["laba"])
        c_laba.number_format = '#,##0'

        c_mrg = ws.cell(row=baris_curr, column=13, value=r["margin_persen"] / 100.0)
        c_mrg.number_format = '0.00%'

        for col in range(1, 14):
            ws.cell(row=baris_curr, column=col).border = _border_tipis()
        baris_curr += 1

    # Baris Total
    ws.merge_cells(start_row=baris_curr, start_column=1, end_row=baris_curr, end_column=4)
    cell_tot_lbl = ws.cell(row=baris_curr, column=1, value="TOTAL KESELURUHAN")
    cell_tot_lbl.font = Font(name="Calibri", size=10, bold=True)
    cell_tot_lbl.alignment = Alignment(horizontal="right", vertical="center")

    for c_idx in range(5, 10):
        c = ws.cell(row=baris_curr, column=c_idx, value=f"=SUM({get_column_letter(c_idx)}6:{get_column_letter(c_idx)}{baris_curr-1})")
        c.font = Font(name="Calibri", size=10, bold=True)
        c.number_format = '#,##0'

    for c_idx in range(10, 13):
        c = ws.cell(row=baris_curr, column=c_idx, value=f"=SUM({get_column_letter(c_idx)}6:{get_column_letter(c_idx)}{baris_curr-1})")
        c.font = Font(name="Calibri", size=10, bold=True)
        c.number_format = '#,##0'

    # Margin rata-rata
    c_mrg_tot = ws.cell(row=baris_curr, column=13, value=f"=IF(J{baris_curr}>0, L{baris_curr}/J{baris_curr}, 0)")
    c_mrg_tot.font = Font(name="Calibri", size=10, bold=True)
    c_mrg_tot.number_format = '0.00%'

    for col in range(1, 14):
        ws.cell(row=baris_curr, column=col).border = _border_tipis()
        ws.cell(row=baris_curr, column=col).fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    # Sesuaikan lebar kolom otomatis
    for col in ws.columns:
        maks_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if cell.number_format and "0" in cell.number_format:
                val_str += "    "
            if len(val_str) > maks_len and cell.row > 3:
                maks_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(maks_len + 3, 11)

    wb.save(path_output)
    return path_output


def ekspor_rekap_barang_pdf(
    daftar_rekap: List[Dict[str, Any]],
    ringkasan_keuangan: Dict[str, Any],
    periode_label: str,
    path_output: str,
    nama_koperasi: str = "Koperasi Karyawan"
) -> str:
    """Mengekspor Rekapitulasi Barang ke file PDF (A4 Landscape)."""
    doc = SimpleDocTemplate(
        path_output,
        pagesize=landscape(A4),
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=25
    )
    styles = getSampleStyleSheet()
    elemen = []

    # Judul
    p_judul = Paragraph(
        f"<b>{nama_koperasi.upper()}</b><br/><font size=12>LAPORAN REKAPITULASI BARANG — {periode_label.upper()}</font>",
        ParagraphStyle(name="HeaderToko", parent=styles["Normal"], fontSize=14, textColor=colors.HexColor("#1E3A8A"), leading=16)
    )
    elemen.append(p_judul)
    elemen.append(Spacer(1, 10))

    # Tabel Data
    table_data = [
        ["No", "Kode", "Nama Barang", "Awal", "Masuk", "Keluar", "Peny.", "Akhir", "Penjualan", "HPP", "Laba"]
    ]

    tot_jual = 0
    tot_hpp = 0
    tot_laba = 0

    for idx, r in enumerate(daftar_rekap, 1):
        tot_jual += r["total_penjualan"]
        tot_hpp += r["total_hpp"]
        tot_laba += r["laba"]
        table_data.append([
            str(idx),
            r["kode"],
            r["nama"][:24],
            f"{r['stok_awal']:,}".replace(",", "."),
            f"{r['masuk']:,}".replace(",", "."),
            f"{r['keluar']:,}".replace(",", "."),
            f"{r['penyesuaian']:,}".replace(",", "."),
            f"{r['stok_akhir']:,}".replace(",", "."),
            f"Rp {r['total_penjualan']:,}".replace(",", "."),
            f"Rp {r['total_hpp']:,}".replace(",", "."),
            f"Rp {r['laba']:,}".replace(",", ".")
        ])

    table_data.append([
        "TOTAL", "", "", "", "", "", "", "",
        f"Rp {tot_jual:,}".replace(",", "."),
        f"Rp {tot_hpp:,}".replace(",", "."),
        f"Rp {tot_laba:,}".replace(",", ".")
    ])

    col_widths = [25, 60, 160, 45, 45, 45, 45, 45, 95, 95, 95]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (2, -1), 'LEFT'),
        ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#F1F5F9")),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('SPAN', (0, -1), (2, -1)),
    ]))

    elemen.append(t)
    doc.build(elemen)
    return path_output
