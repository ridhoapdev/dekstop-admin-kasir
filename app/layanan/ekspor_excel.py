"""
app/layanan/ekspor_excel.py — Layanan ekspor data ke format Excel (.xlsx) menggunakan openpyxl.
Sesuai RULES.md & SPEC.md 4.6.
"""
from pathlib import Path
from typing import List, Dict, Any, Union
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from app.util.format import format_rupiah, format_tanggal_indo


def ekspor_tabel_ke_excel(
    judul: str,
    kolom_header: List[str],
    baris_data: List[List[Any]],
    path_tujuan: Union[str, Path],
    baris_total: List[str] = None
) -> Path:
    """
    Mengekspor daftar baris data ke file Excel (.xlsx) dengan format rapi,
    header berwarna, garis tepi, dan baris total opsional.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Laporan"

    # Font styling
    font_judul = Font(name="Segoe UI", size=14, bold=True)
    font_header = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    font_isi = Font(name="Segoe UI", size=11)
    font_total = Font(name="Segoe UI", size=11, bold=True)

    fill_header = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    fill_total = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='D1D5DB'),
        right=Side(style='thin', color='D1D5DB'),
        top=Side(style='thin', color='D1D5DB'),
        bottom=Side(style='thin', color='D1D5DB')
    )

    # 1. Baris Judul
    ws.append([judul])
    ws.cell(row=1, column=1).font = font_judul
    ws.append([])  # Kosong

    # 2. Header Kolom
    ws.append(kolom_header)
    baris_header_idx = 3
    for col_idx in range(1, len(kolom_header) + 1):
        cell = ws.cell(row=baris_header_idx, column=col_idx)
        cell.font = font_header
        cell.fill = fill_header
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    # 3. Baris Data
    for baris in baris_data:
        ws.append(baris)
        current_row = ws.max_row
        for col_idx in range(1, len(kolom_header) + 1):
            cell = ws.cell(row=current_row, column=col_idx)
            cell.font = font_isi
            cell.border = thin_border

    # 4. Baris Total (jika ada)
    if baris_total:
        ws.append(baris_total)
        total_row = ws.max_row
        for col_idx in range(1, len(kolom_header) + 1):
            cell = ws.cell(row=total_row, column=col_idx)
            cell.font = font_total
            cell.fill = fill_total
            cell.border = thin_border

    # Atur lebar kolom otomatis
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    path_out = Path(path_tujuan)
    path_out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path_out))
    return path_out

