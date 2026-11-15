"""
app/layanan/ekspor_laporan_periode.py — Layanan ekspor Excel & PDF untuk Laporan Bulanan dan Tahunan.
Menampilkan nama koperasi dari pengaturan, periode, status closing, tanggal cetak,
dan grafik batang kas masuk vs keluar tahunan pada dokumen PDF.
"""
from pathlib import Path
from typing import Dict, Any, Union
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Group

from app.util.format import format_rupiah, format_tanggal_indo


def ekspor_laporan_bulanan_excel(
    data: Dict[str, Any],
    nama_koperasi: str,
    path_tujuan: Union[str, Path]
) -> Path:
    wb = openpyxl.Workbook()
    
    # Sheet 1: Ringkasan Bulanan
    ws_ringkasan = wb.active
    ws_ringkasan.title = "Ringkasan Bulanan"

    font_judul = Font(name="Segoe UI", size=14, bold=True, color="1E3A8A")
    font_sub = Font(name="Segoe UI", size=10, italic=True, color="64748B")
    font_sec = Font(name="Segoe UI", size=11, bold=True, color="1E293B")
    font_th = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_td = Font(name="Segoe UI", size=10)
    font_tb = Font(name="Segoe UI", size=10, bold=True)

    fill_th = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    fill_sub_th = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid")
    fill_row_alt = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    fill_tot = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    ws_ringkasan.append([nama_koperasi.upper()])
    ws_ringkasan.cell(row=1, column=1).font = font_judul
    ws_ringkasan.append([f"LAPORAN KEUANGAN BULANAN — {data['nama_bulan'].upper()} {data['tahun']}"])
    ws_ringkasan.cell(row=2, column=1).font = Font(name="Segoe UI", size=12, bold=True)
    ws_ringkasan.append([f"Status: {data['status_label']} | Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M')}"])
    ws_ringkasan.cell(row=3, column=1).font = font_sub
    ws_ringkasan.append([])

    # 1. Arus Kas Bersih
    ws_ringkasan.append(["1. RINGKASAN ARUS KAS"])
    ws_ringkasan.cell(row=5, column=1).font = font_sec
    ws_ringkasan.append(["Pos Kas", "Nominal (Rp)"])
    for c in range(1, 3):
        cell = ws_ringkasan.cell(row=6, column=c)
        cell.font = font_th
        cell.fill = fill_th
        cell.border = thin_border

    baris_kas = [
        ["Saldo Kas Awal", data["saldo_kas_awal"]],
        ["Total Kas Masuk (+)", data["total_kas_masuk"]],
        ["Total Kas Keluar (-)", data["total_kas_keluar"]],
        ["Saldo Kas Akhir", data["saldo_kas_akhir"]],
    ]
    for r in baris_kas:
        ws_ringkasan.append(r)
        r_idx = ws_ringkasan.max_row
        for c in range(1, 3):
            cell = ws_ringkasan.cell(row=r_idx, column=c)
            cell.font = font_tb if "Akhir" in str(r[0]) else font_td
            cell.border = thin_border
            if c == 2:
                cell.number_format = '#,##0'

    ws_ringkasan.append([])

    # 2. Simpanan per Jenis
    ws_ringkasan.append(["2. MUTASI DAN SALDO SIMPANAN ANGGOTA"])
    ws_ringkasan.cell(row=ws_ringkasan.max_row, column=1).font = font_sec
    ws_ringkasan.append(["Jenis Simpanan", "Setor (Rp)", "Tarik (Rp)", "Saldo Akhir (Rp)"])
    th_r = ws_ringkasan.max_row
    for c in range(1, 5):
        cell = ws_ringkasan.cell(row=th_r, column=c)
        cell.font = font_th
        cell.fill = fill_th
        cell.border = thin_border

    simp = data["simpanan"]
    rows_simp = [
        ["Simpanan Pokok", simp["pokok"]["setor"], simp["pokok"]["tarik"], simp["pokok"]["saldo_akhir"]],
        ["Simpanan Wajib", simp["wajib"]["setor"], simp["wajib"]["tarik"], simp["wajib"]["saldo_akhir"]],
        ["Simpanan Sukarela", simp["sukarela"]["setor"], simp["sukarela"]["tarik"], simp["sukarela"]["saldo_akhir"]],
        ["Total Simpanan", simp["total"]["setor"], simp["total"]["tarik"], simp["total"]["saldo_akhir"]],
    ]
    for r in rows_simp:
        ws_ringkasan.append(r)
        r_idx = ws_ringkasan.max_row
        for c in range(1, 5):
            cell = ws_ringkasan.cell(row=r_idx, column=c)
            cell.font = font_tb if "Total" in str(r[0]) else font_td
            cell.border = thin_border
            if c > 1:
                cell.number_format = '#,##0'

    ws_ringkasan.append([])

    # 3. Pinjaman & Anggota
    ws_ringkasan.append(["3. PINJAMAN DAN KEANGGOTAAN"])
    ws_ringkasan.cell(row=ws_ringkasan.max_row, column=1).font = font_sec
    pinj = data["pinjaman"]
    ang = data["anggota"]
    rows_pinj_ang = [
        ["Pinjaman Cair (Jumlah / Plafon)", f"{pinj['cair_jumlah']} Pengajuan / Rp {pinj['cair_nominal']:,}".replace(",", ".")],
        ["Angsuran Pokok Diterima", f"Rp {pinj['angsuran_pokok']:,}".replace(",", ".")],
        ["Jasa Pinjaman Diterima", f"Rp {pinj['jasa_diterima']:,}".replace(",", ".")],
        ["Biaya Admin Pinjaman", f"Rp {pinj['biaya_admin']:,}".replace(",", ".")],
        ["Sisa Pokok Pinjaman Akhir Bulan", f"Rp {pinj['sisa_pokok_akhir']:,}".replace(",", ".")],
        ["Jumlah Pinjaman Berjalan / Aktif", f"{pinj['pinjaman_aktif_jumlah']} Pinjaman"],
        ["Anggota Baru Bulan Ini", f"{ang['baru']} Orang"],
        ["Anggota Keluar Bulan Ini", f"{ang['keluar']} Orang"],
        ["Total Anggota Aktif Akhir Bulan", f"{ang['aktif_akhir']} Orang"],
    ]
    for r in rows_pinj_ang:
        ws_ringkasan.append(r)
        r_idx = ws_ringkasan.max_row
        for c in range(1, 3):
            cell = ws_ringkasan.cell(row=r_idx, column=c)
            cell.font = font_td
            cell.border = thin_border

    ws_ringkasan.append([])

    # 4. Perbandingan Bulan Lalu
    ws_ringkasan.append(["4. PERBANDINGAN DENGAN BULAN SEBELUMNYA"])
    ws_ringkasan.cell(row=ws_ringkasan.max_row, column=1).font = font_sec
    ws_ringkasan.append(["Indikator", "Bulan Ini (Rp)", "Bulan Lalu (Rp)", "Selisih (Rp)", "Pertumbuhan"])
    th_r2 = ws_ringkasan.max_row
    for c in range(1, 6):
        cell = ws_ringkasan.cell(row=th_r2, column=c)
        cell.font = font_th
        cell.fill = fill_th
        cell.border = thin_border

    pb = data["perbandingan"]
    rows_pb = [
        ["Total Kas Masuk", pb["kas_masuk"]["kini"], pb["kas_masuk"]["lalu"], pb["kas_masuk"]["selisih"], pb["kas_masuk"]["persen_str"]],
        ["Total Kas Keluar", pb["kas_keluar"]["kini"], pb["kas_keluar"]["lalu"], pb["kas_keluar"]["selisih"], pb["kas_keluar"]["persen_str"]],
        ["Setoran Simpanan", pb["simpanan"]["kini"], pb["simpanan"]["lalu"], pb["simpanan"]["selisih"], pb["simpanan"]["persen_str"]],
        ["Pinjaman Cair", pb["pinjaman_cair"]["kini"], pb["pinjaman_cair"]["lalu"], pb["pinjaman_cair"]["selisih"], pb["pinjaman_cair"]["persen_str"]],
        ["Jasa Diterima", pb["jasa_diterima"]["kini"], pb["jasa_diterima"]["lalu"], pb["jasa_diterima"]["selisih"], pb["jasa_diterima"]["persen_str"]],
    ]
    for r in rows_pb:
        ws_ringkasan.append(r)
        r_idx = ws_ringkasan.max_row
        for c in range(1, 6):
            cell = ws_ringkasan.cell(row=r_idx, column=c)
            cell.font = font_td
            cell.border = thin_border
            if 2 <= c <= 4:
                cell.number_format = '#,##0'

    # Auto-lebar kolom ringkasan
    for col in ws_ringkasan.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws_ringkasan.column_dimensions[col_letter].width = max(max_len + 3, 14)

    # Sheet 2: Daftar Transaksi Kas Rinci
    ws_tx = wb.create_sheet(title="Transaksi Kas Rinci")
    ws_tx.append(["No", "Tanggal", "Keterangan", "Kas Masuk (Rp)", "Kas Keluar (Rp)", "Sumber", "Status"])
    for c in range(1, 8):
        cell = ws_tx.cell(row=1, column=c)
        cell.font = font_th
        cell.fill = fill_th
        cell.border = thin_border

    for idx, tx in enumerate(data["transaksi_rinci"], 1):
        ws_tx.append([
            idx,
            tx["tanggal"],
            tx["keterangan"],
            tx["masuk"],
            tx["keluar"],
            tx["sumber"],
            tx["status_klasifikasi"]
        ])
        r_idx = ws_tx.max_row
        for c in range(1, 8):
            cell = ws_tx.cell(row=r_idx, column=c)
            cell.font = font_td
            cell.border = thin_border
            if c in (4, 5):
                cell.number_format = '#,##0'

    for col in ws_tx.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws_tx.column_dimensions[col_letter].width = max(max_len + 3, 12)

    # Sheet 3: Daftar Tunggakan Rinci
    ws_tg = wb.create_sheet(title="Daftar Tunggakan")
    ws_tg.append(["No", "No. Anggota", "Nama Anggota", "Unit", "No. Pinjaman", "Cicilan Telat", "Total Tunggakan (Rp)"])
    for c in range(1, 8):
        cell = ws_tg.cell(row=1, column=c)
        cell.font = font_th
        cell.fill = fill_th
        cell.border = thin_border

    for idx, tg in enumerate(data["tunggakan"]["daftar"], 1):
        ws_tg.append([
            idx,
            tg["no_anggota"],
            tg["nama_anggota"],
            tg["unit"],
            tg["no_pinjaman"],
            tg["jumlah_cicilan_telat"],
            tg["total_tunggakan"]
        ])
        r_idx = ws_tg.max_row
        for c in range(1, 8):
            cell = ws_tg.cell(row=r_idx, column=c)
            cell.font = font_td
            cell.border = thin_border
            if c == 7:
                cell.number_format = '#,##0'

    for col in ws_tg.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws_tg.column_dimensions[col_letter].width = max(max_len + 3, 12)

    path_out = Path(path_tujuan)
    path_out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path_out))
    return path_out


def ekspor_laporan_tahunan_excel(
    data: Dict[str, Any],
    nama_koperasi: str,
    path_tujuan: Union[str, Path]
) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Tahunan {data['tahun']}"

    font_judul = Font(name="Segoe UI", size=14, bold=True, color="1E3A8A")
    font_sub = Font(name="Segoe UI", size=10, italic=True, color="64748B")
    font_th = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    font_td = Font(name="Segoe UI", size=10)
    font_tb = Font(name="Segoe UI", size=10, bold=True)

    fill_th = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    fill_tot = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    ws.append([nama_koperasi.upper()])
    ws.cell(row=1, column=1).font = font_judul
    ws.append([f"LAPORAN KEUANGAN TAHUN BUKU {data['tahun']}"])
    ws.cell(row=2, column=1).font = Font(name="Segoe UI", size=12, bold=True)
    ws.append([f"Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M')}"])
    ws.cell(row=3, column=1).font = font_sub
    ws.append([])

    headers = [
        "Bulan", "Status", "Kas Masuk (Rp)", "Kas Keluar (Rp)", "Saldo Kas Akhir (Rp)",
        "Simpanan Masuk (Rp)", "Pinjaman Cair (Rp)", "Jasa Diterima (Rp)", "Sisa Pokok Akhir (Rp)"
    ]
    ws.append(headers)
    th_r = ws.max_row
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=th_r, column=c)
        cell.font = font_th
        cell.fill = fill_th
        cell.border = thin_border

    for b in data["tabel_12_bulan"]:
        ws.append([
            b["nama_bulan"],
            b["status_label"],
            b["kas_masuk"],
            b["kas_keluar"],
            b["saldo_kas_akhir"],
            b["simpanan_masuk"],
            b["pinjaman_cair"],
            b["jasa_diterima"],
            b["sisa_pokok"]
        ])
        r_idx = ws.max_row
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=r_idx, column=c)
            cell.font = font_td
            cell.border = thin_border
            if c >= 3:
                cell.number_format = '#,##0'

    # Baris Total Setahun
    ws.append([
        "TOTAL SETAHUN",
        "-",
        data["total_kas_masuk"],
        data["total_kas_keluar"],
        data["saldo_kas_akhir"],
        data["total_simpanan_masuk"],
        data["total_pinjaman_cair"],
        data["total_jasa_diterima"],
        data["sisa_pokok_akhir"]
    ])
    tot_r = ws.max_row
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=tot_r, column=c)
        cell.font = font_tb
        cell.fill = fill_tot
        cell.border = thin_border
        if c >= 3:
            cell.number_format = '#,##0'

    ws.append([])
    ws.append(["POSISI AKHIR TAHUN"])
    ws.cell(row=ws.max_row, column=1).font = Font(name="Segoe UI", size=11, bold=True)

    simp = data["posisi_simpanan"]
    ws.append(["Total Saldo Simpanan Pokok", simp["pokok"]["saldo_akhir"]])
    ws.append(["Total Saldo Simpanan Wajib", simp["wajib"]["saldo_akhir"]])
    ws.append(["Total Saldo Simpanan Sukarela", simp["sukarela"]["saldo_akhir"]])
    ws.append(["Total Seluruh Simpanan", simp["total"]["saldo_akhir"]])
    ws.append(["Total Pinjaman Beredar (Sisa Pokok)", data["sisa_pokok_akhir"]])
    ws.append(["Total Tunggakan Anggota", data["total_tunggakan_akhir"]])
    ws.append(["Anggota Baru Selama Tahun Ini", data["anggota_baru"]])
    ws.append(["Anggota Keluar Selama Tahun Ini", data["anggota_keluar"]])
    ws.append(["Total Anggota Aktif Akhir Tahun", data["anggota_aktif_akhir"]])

    for r_idx in range(tot_r + 3, ws.max_row + 1):
        for c in range(1, 3):
            cell = ws.cell(row=r_idx, column=c)
            cell.font = font_tb if "Total" in str(ws.cell(row=r_idx, column=1).value) else font_td
            cell.border = thin_border
            if c == 2 and isinstance(cell.value, int):
                cell.number_format = '#,##0'

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 3, 14)

    path_out = Path(path_tujuan)
    path_out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path_out))
    return path_out


def ekspor_laporan_bulanan_pdf(
    data: Dict[str, Any],
    nama_koperasi: str,
    path_tujuan: Union[str, Path]
) -> Path:
    path_out = Path(path_tujuan)
    path_out.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(path_out),
        pagesize=A4,
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    style_kop = ParagraphStyle('Kop', fontName='Helvetica-Bold', fontSize=13, textColor=colors.HexColor("#1E3A8A"), spaceAfter=2)
    style_judul = ParagraphStyle('Judul', fontName='Helvetica-Bold', fontSize=12, alignment=1, spaceAfter=2)
    style_sub = ParagraphStyle('Sub', fontName='Helvetica', fontSize=9, alignment=1, textColor=colors.HexColor("#64748B"), spaceAfter=10)
    style_sec = ParagraphStyle('Sec', fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor("#1E293B"), spaceBefore=6, spaceAfter=4)
    style_td = ParagraphStyle('Td', fontName='Helvetica', fontSize=8, leading=10)
    style_td_r = ParagraphStyle('TdR', fontName='Helvetica', fontSize=8, leading=10, alignment=2)
    style_td_b = ParagraphStyle('TdB', fontName='Helvetica-Bold', fontSize=8, leading=10)
    style_td_br = ParagraphStyle('TdBR', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=2)

    elements = []
    elements.append(Paragraph(nama_koperasi.upper(), style_kop))
    elements.append(Paragraph(f"LAPORAN KEUANGAN BULANAN — {data['nama_bulan'].upper()} {data['tahun']}", style_judul))
    elements.append(Paragraph(f"Status: <b>{data['status_label']}</b> | Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M')}", style_sub))

    # 1. Tabel Arus Kas & Simpanan Berdampingan / Berurutan
    elements.append(Paragraph("1. Ringkasan Arus Kas dan Mutasi Simpanan", style_sec))
    kas_data = [
        [Paragraph("<b>Pos Arus Kas</b>", style_td_b), Paragraph("<b>Nominal</b>", style_td_br),
         Paragraph("<b>Jenis Simpanan</b>", style_td_b), Paragraph("<b>Setor</b>", style_td_br), Paragraph("<b>Tarik</b>", style_td_br), Paragraph("<b>Saldo Akhir</b>", style_td_br)],
        [Paragraph("Saldo Kas Awal", style_td), Paragraph(format_rupiah(data["saldo_kas_awal"]), style_td_r),
         Paragraph("Simp. Pokok", style_td), Paragraph(format_rupiah(data["simpanan"]["pokok"]["setor"]), style_td_r), Paragraph(format_rupiah(data["simpanan"]["pokok"]["tarik"]), style_td_r), Paragraph(format_rupiah(data["simpanan"]["pokok"]["saldo_akhir"]), style_td_r)],
        [Paragraph("Total Kas Masuk (+)", style_td), Paragraph(format_rupiah(data["total_kas_masuk"]), style_td_r),
         Paragraph("Simp. Wajib", style_td), Paragraph(format_rupiah(data["simpanan"]["wajib"]["setor"]), style_td_r), Paragraph(format_rupiah(data["simpanan"]["wajib"]["tarik"]), style_td_r), Paragraph(format_rupiah(data["simpanan"]["wajib"]["saldo_akhir"]), style_td_r)],
        [Paragraph("Total Kas Keluar (-)", style_td), Paragraph(format_rupiah(data["total_kas_keluar"]), style_td_r),
         Paragraph("Simp. Sukarela", style_td), Paragraph(format_rupiah(data["simpanan"]["sukarela"]["setor"]), style_td_r), Paragraph(format_rupiah(data["simpanan"]["sukarela"]["tarik"]), style_td_r), Paragraph(format_rupiah(data["simpanan"]["sukarela"]["saldo_akhir"]), style_td_r)],
        [Paragraph("<b>Saldo Kas Akhir</b>", style_td_b), Paragraph(f"<b>{format_rupiah(data['saldo_kas_akhir'])}</b>", style_td_br),
         Paragraph("<b>Total Simpanan</b>", style_td_b), Paragraph(f"<b>{format_rupiah(data['simpanan']['total']['setor'])}</b>", style_td_br), Paragraph(f"<b>{format_rupiah(data['simpanan']['total']['tarik'])}</b>", style_td_br), Paragraph(f"<b>{format_rupiah(data['simpanan']['total']['saldo_akhir'])}</b>", style_td_br)],
    ]
    t_kas = Table(kas_data, colWidths=[105, 80, 85, 75, 75, 80])
    t_kas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_kas)
    elements.append(Spacer(1, 8))

    # 2. Pinjaman & Keanggotaan
    elements.append(Paragraph("2. Posisi Pinjaman, Jasa, dan Keanggotaan", style_sec))
    pj = data["pinjaman"]
    ag = data["anggota"]
    pj_ag_data = [
        [Paragraph("<b>Indikator Pinjaman</b>", style_td_b), Paragraph("<b>Nilai</b>", style_td_br),
         Paragraph("<b>Indikator Keanggotaan</b>", style_td_b), Paragraph("<b>Nilai</b>", style_td_br)],
        [Paragraph("Pinjaman Cair Bulan Ini", style_td), Paragraph(f"{pj['cair_jumlah']} Pinj ({format_rupiah(pj['cair_nominal'])})", style_td_r),
         Paragraph("Anggota Baru Bulan Ini", style_td), Paragraph(f"{ag['baru']} Orang", style_td_r)],
        [Paragraph("Angsuran Pokok Diterima", style_td), Paragraph(format_rupiah(pj["angsuran_pokok"]), style_td_r),
         Paragraph("Anggota Keluar Bulan Ini", style_td), Paragraph(f"{ag['keluar']} Orang", style_td_r)],
        [Paragraph("Jasa Diterima / Biaya Admin", style_td), Paragraph(f"{format_rupiah(pj['jasa_diterima'])} / {format_rupiah(pj['biaya_admin'])}", style_td_r),
         Paragraph("Total Anggota Aktif Akhir", style_td), Paragraph(f"<b>{ag['aktif_akhir']} Orang</b>", style_td_r)],
        [Paragraph("Sisa Pokok Pinjaman Beredar", style_td_b), Paragraph(f"<b>{format_rupiah(pj['sisa_pokok_akhir'])}</b>", style_td_br),
         Paragraph("Pinjaman Aktif Berjalan", style_td), Paragraph(f"{pj['pinjaman_aktif_jumlah']} Pinjaman", style_td_r)],
    ]
    t_pj_ag = Table(pj_ag_data, colWidths=[150, 120, 150, 80])
    t_pj_ag.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_pj_ag)
    elements.append(Spacer(1, 8))

    # 3. Perbandingan Bulan Lalu
    elements.append(Paragraph("3. Perbandingan dengan Bulan Sebelumnya", style_sec))
    pb = data["perbandingan"]
    pb_data = [
        [Paragraph("<b>Indikator Keuangan</b>", style_td_b), Paragraph("<b>Bulan Ini</b>", style_td_br),
         Paragraph("<b>Bulan Lalu</b>", style_td_br), Paragraph("<b>Selisih (Rp)</b>", style_td_br), Paragraph("<b>Pertumbuhan</b>", style_td_br)],
        [Paragraph("Total Kas Masuk", style_td), Paragraph(format_rupiah(pb["kas_masuk"]["kini"]), style_td_r), Paragraph(format_rupiah(pb["kas_masuk"]["lalu"]), style_td_r), Paragraph(format_rupiah(pb["kas_masuk"]["selisih"]), style_td_r), Paragraph(pb["kas_masuk"]["persen_str"], style_td_br)],
        [Paragraph("Total Kas Keluar", style_td), Paragraph(format_rupiah(pb["kas_keluar"]["kini"]), style_td_r), Paragraph(format_rupiah(pb["kas_keluar"]["lalu"]), style_td_r), Paragraph(format_rupiah(pb["kas_keluar"]["selisih"]), style_td_r), Paragraph(pb["kas_keluar"]["persen_str"], style_td_br)],
        [Paragraph("Setoran Simpanan Masuk", style_td), Paragraph(format_rupiah(pb["simpanan"]["kini"]), style_td_r), Paragraph(format_rupiah(pb["simpanan"]["lalu"]), style_td_r), Paragraph(format_rupiah(pb["simpanan"]["selisih"]), style_td_r), Paragraph(pb["simpanan"]["persen_str"], style_td_br)],
        [Paragraph("Pencairan Pinjaman", style_td), Paragraph(format_rupiah(pb["pinjaman_cair"]["kini"]), style_td_r), Paragraph(format_rupiah(pb["pinjaman_cair"]["lalu"]), style_td_r), Paragraph(format_rupiah(pb["pinjaman_cair"]["selisih"]), style_td_r), Paragraph(pb["pinjaman_cair"]["persen_str"], style_td_br)],
        [Paragraph("Jasa Pinjaman Diterima", style_td), Paragraph(format_rupiah(pb["jasa_diterima"]["kini"]), style_td_r), Paragraph(format_rupiah(pb["jasa_diterima"]["lalu"]), style_td_r), Paragraph(format_rupiah(pb["jasa_diterima"]["selisih"]), style_td_r), Paragraph(pb["jasa_diterima"]["persen_str"], style_td_br)],
    ]
    t_pb = Table(pb_data, colWidths=[150, 90, 90, 90, 80])
    t_pb.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_pb)
    elements.append(Spacer(1, 8))

    # 4. Ringkasan Tunggakan
    tg = data["tunggakan"]
    elements.append(Paragraph(f"4. Informasi Tunggakan Akhir Bulan ({tg['jumlah_anggota']} Anggota — Total: {format_rupiah(tg['total_nominal'])})", style_sec))
    if tg["daftar"]:
        tg_headers = [Paragraph("<b>No</b>", style_td_b), Paragraph("<b>No. Anggota</b>", style_td_b), Paragraph("<b>Nama Anggota</b>", style_td_b),
                      Paragraph("<b>Unit</b>", style_td_b), Paragraph("<b>No. Pinjaman</b>", style_td_b), Paragraph("<b>Cicilan</b>", style_td_br), Paragraph("<b>Tunggakan</b>", style_td_br)]
        tg_rows = [tg_headers]
        for idx, item in enumerate(tg["daftar"][:15], 1):  # tampilkan sampai 15 data teratas di cetakan
            tg_rows.append([
                Paragraph(str(idx), style_td),
                Paragraph(item["no_anggota"], style_td),
                Paragraph(item["nama_anggota"], style_td),
                Paragraph(item["unit"], style_td),
                Paragraph(item["no_pinjaman"], style_td),
                Paragraph(f"{item['jumlah_cicilan_telat']}x", style_td_r),
                Paragraph(format_rupiah(item["total_tunggakan"]), style_td_r)
            ])
        t_tg = Table(tg_rows, colWidths=[20, 70, 140, 70, 80, 40, 80])
        t_tg.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#DC2626")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(t_tg)
    else:
        elements.append(Paragraph("<i>Tidak ada anggota yang menunggak pada akhir bulan ini.</i>", style_td))

    doc.build(elements)
    return path_out


def _buat_grafik_batang_reportlab(data_12_bulan: list, width: int = 500, height: int = 140) -> Drawing:
    """Menggambar grafik batang kas masuk vs keluar 12 bulan menggunakan reportlab.graphics."""
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, strokeColor=colors.HexColor("#E2E8F0"), fillColor=colors.HexColor("#F8FAFC"), rx=4, ry=4))
    
    max_val = max([max(b["kas_masuk"], b["kas_keluar"]) for b in data_12_bulan] + [100000])
    
    margin_l = 40
    margin_b = 25
    plot_w = width - margin_l - 20
    plot_h = height - margin_b - 25

    # Axis horizontal
    d.add(Line(margin_l, margin_b, margin_l + plot_w, margin_b, strokeColor=colors.HexColor("#94A3B8"), strokeWidth=1))

    # Legend
    d.add(Rect(width - 150, height - 18, 10, 8, fillColor=colors.HexColor("#10B981"), strokeColor=None))
    d.add(String(width - 135, height - 18, "Masuk", fontName="Helvetica", fontSize=8, fillColor=colors.HexColor("#1E293B")))
    d.add(Rect(width - 80, height - 18, 10, 8, fillColor=colors.HexColor("#EF4444"), strokeColor=None))
    d.add(String(width - 65, height - 18, "Keluar", fontName="Helvetica", fontSize=8, fillColor=colors.HexColor("#1E293B")))

    slot_w = plot_w / 12
    bar_w = slot_w * 0.35

    singkatan_bulan = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

    for i, b in enumerate(data_12_bulan):
        x_base = margin_l + i * slot_w + (slot_w - 2 * bar_w) / 2
        h_masuk = (b["kas_masuk"] / max_val) * plot_h
        h_keluar = (b["kas_keluar"] / max_val) * plot_h

        # Batang Masuk (Hijau)
        if h_masuk > 0:
            d.add(Rect(x_base, margin_b, bar_w, h_masuk, fillColor=colors.HexColor("#10B981"), strokeColor=None))
        # Batang Keluar (Merah)
        if h_keluar > 0:
            d.add(Rect(x_base + bar_w + 1, margin_b, bar_w, h_keluar, fillColor=colors.HexColor("#EF4444"), strokeColor=None))

        # Label Bulan
        d.add(String(x_base, margin_b - 12, singkatan_bulan[i], fontName="Helvetica", fontSize=7, fillColor=colors.HexColor("#64748B")))

    return d


def ekspor_laporan_tahunan_pdf(
    data: Dict[str, Any],
    nama_koperasi: str,
    path_tujuan: Union[str, Path]
) -> Path:
    path_out = Path(path_tujuan)
    path_out.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(path_out),
        pagesize=A4,
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    style_kop = ParagraphStyle('Kop', fontName='Helvetica-Bold', fontSize=13, textColor=colors.HexColor("#1E3A8A"), spaceAfter=2)
    style_judul = ParagraphStyle('Judul', fontName='Helvetica-Bold', fontSize=12, alignment=1, spaceAfter=2)
    style_sub = ParagraphStyle('Sub', fontName='Helvetica', fontSize=9, alignment=1, textColor=colors.HexColor("#64748B"), spaceAfter=10)
    style_sec = ParagraphStyle('Sec', fontName='Helvetica-Bold', fontSize=10, textColor=colors.HexColor("#1E293B"), spaceBefore=6, spaceAfter=4)
    style_td = ParagraphStyle('Td', fontName='Helvetica', fontSize=7.5, leading=9)
    style_td_r = ParagraphStyle('TdR', fontName='Helvetica', fontSize=7.5, leading=9, alignment=2)
    style_td_b = ParagraphStyle('TdB', fontName='Helvetica-Bold', fontSize=7.5, leading=9)
    style_td_br = ParagraphStyle('TdBR', fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=2)

    elements = []
    elements.append(Paragraph(nama_koperasi.upper(), style_kop))
    elements.append(Paragraph(f"LAPORAN KEUANGAN TAHUNAN — TAHUN BUKU {data['tahun']}", style_judul))
    elements.append(Paragraph(f"Dicetak: {datetime.now().strftime('%d/%m/%Y %H:%M')}", style_sub))

    # Peringatan bulan belum closing jika ada
    if data["bulan_belum_closing"]:
        teks_blm = ", ".join(data["bulan_belum_closing"])
        elements.append(Paragraph(f"<font color='#B45309'><b>Perhatian:</b> Terdapat {len(data['bulan_belum_closing'])} bulan dengan data sementara (belum di-closing): {teks_blm}</font>", style_td))
        elements.append(Spacer(1, 4))

    # 1. Grafik Batang Masuk vs Keluar
    elements.append(Paragraph("1. Grafik Perkembangan Arus Kas Bulanan (Kas Masuk vs Kas Keluar)", style_sec))
    grafik = _buat_grafik_batang_reportlab(data["tabel_12_bulan"])
    elements.append(grafik)
    elements.append(Spacer(1, 10))

    # 2. Tabel 12 Bulan
    elements.append(Paragraph("2. Rekapitulasi Keuangan 12 Bulan", style_sec))
    tb_headers = [
        Paragraph("<b>Bulan</b>", style_td_b), Paragraph("<b>Status</b>", style_td_b),
        Paragraph("<b>Kas Masuk</b>", style_td_br), Paragraph("<b>Kas Keluar</b>", style_td_br),
        Paragraph("<b>Kas Akhir</b>", style_td_br), Paragraph("<b>Simp. Masuk</b>", style_td_br),
        Paragraph("<b>Pinj. Cair</b>", style_td_br), Paragraph("<b>Jasa Diterima</b>", style_td_br)
    ]
    tb_rows = [tb_headers]
    for b in data["tabel_12_bulan"]:
        tb_rows.append([
            Paragraph(b["nama_bulan"], style_td),
            Paragraph(b["status_label"], style_td),
            Paragraph(format_rupiah(b["kas_masuk"]), style_td_r),
            Paragraph(format_rupiah(b["kas_keluar"]), style_td_r),
            Paragraph(format_rupiah(b["saldo_kas_akhir"]), style_td_r),
            Paragraph(format_rupiah(b["simpanan_masuk"]), style_td_r),
            Paragraph(format_rupiah(b["pinjaman_cair"]), style_td_r),
            Paragraph(format_rupiah(b["jasa_diterima"]), style_td_r),
        ])

    # Total setahun row
    tb_rows.append([
        Paragraph("<b>TOTAL SETAHUN</b>", style_td_b),
        Paragraph("-", style_td),
        Paragraph(f"<b>{format_rupiah(data['total_kas_masuk'])}</b>", style_td_br),
        Paragraph(f"<b>{format_rupiah(data['total_kas_keluar'])}</b>", style_td_br),
        Paragraph(f"<b>{format_rupiah(data['saldo_kas_akhir'])}</b>", style_td_br),
        Paragraph(f"<b>{format_rupiah(data['total_simpanan_masuk'])}</b>", style_td_br),
        Paragraph(f"<b>{format_rupiah(data['total_pinjaman_cair'])}</b>", style_td_br),
        Paragraph(f"<b>{format_rupiah(data['total_jasa_diterima'])}</b>", style_td_br),
    ])

    t_12 = Table(tb_rows, colWidths=[55, 45, 65, 65, 75, 75, 75, 75])
    t_12.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#EFF6FF")),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(t_12)
    elements.append(Spacer(1, 8))

    # 3. Posisi Akhir Tahun
    elements.append(Paragraph("3. Posisi Neraca dan Keanggotaan Akhir Tahun", style_sec))
    simp = data["posisi_simpanan"]
    neraca_data = [
        [Paragraph("<b>Posisi Simpanan & Pinjaman</b>", style_td_b), Paragraph("<b>Nominal</b>", style_td_br),
         Paragraph("<b>Statistik Keanggotaan</b>", style_td_b), Paragraph("<b>Jumlah</b>", style_td_br)],
        [Paragraph("Simpanan Pokok", style_td), Paragraph(format_rupiah(simp["pokok"]["saldo_akhir"]), style_td_r),
         Paragraph("Anggota Baru Tahun Ini", style_td), Paragraph(f"{data['anggota_baru']} Orang", style_td_r)],
        [Paragraph("Simpanan Wajib", style_td), Paragraph(format_rupiah(simp["wajib"]["saldo_akhir"]), style_td_r),
         Paragraph("Anggota Keluar Tahun Ini", style_td), Paragraph(f"{data['anggota_keluar']} Orang", style_td_r)],
        [Paragraph("Simpanan Sukarela", style_td), Paragraph(format_rupiah(simp["sukarela"]["saldo_akhir"]), style_td_r),
         Paragraph("Total Anggota Aktif Akhir Tahun", style_td), Paragraph(f"<b>{data['anggota_aktif_akhir']} Orang</b>", style_td_r)],
        [Paragraph("<b>Total Seluruh Simpanan</b>", style_td_b), Paragraph(f"<b>{format_rupiah(simp['total']['saldo_akhir'])}</b>", style_td_br),
         Paragraph("Pinjaman Beredar (Sisa Pokok)", style_td_b), Paragraph(f"<b>{format_rupiah(data['sisa_pokok_akhir'])}</b>", style_td_br)],
        [Paragraph("Total Tunggakan Akhir Tahun", style_td), Paragraph(format_rupiah(data["total_tunggakan_akhir"]), style_td_r),
         Paragraph("Saldo Kas Operasional Akhir", style_td_b), Paragraph(f"<b>{format_rupiah(data['saldo_kas_akhir'])}</b>", style_td_br)],
    ]
    t_neraca = Table(neraca_data, colWidths=[150, 110, 150, 90])
    t_neraca.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t_neraca)

    doc.build(elements)
    return path_out

