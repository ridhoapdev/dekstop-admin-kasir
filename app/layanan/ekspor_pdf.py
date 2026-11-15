"""
app/layanan/ekspor_pdf.py — Layanan ekspor dokumen PDF memakai reportlab.
Sesuai RULES.md Bab 1 & SPEC.md 4.7.
"""
from pathlib import Path
from typing import List, Dict, Any, Union
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from app.util.format import format_rupiah, format_tanggal_indo


def ekspor_laporan_ke_pdf(
    judul: str,
    periode_teks: str,
    ringkasan_metrik: List[tuple],
    kolom_tabel: List[str],
    baris_tabel: List[List[str]],
    path_tujuan: Union[str, Path]
) -> Path:
    """
    Membuat file PDF profesional menggunakan reportlab:
    - Judul dan periode
    - Tabel ringkasan arus kas
    - Tabel transaksi rinci
    """
    path_out = Path(path_tujuan)
    path_out.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(path_out),
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    style_judul = ParagraphStyle(
        'Judul',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=15,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=4
    )
    style_sub = ParagraphStyle(
        'SubJudul',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        textColor=colors.HexColor("#4B5563"),
        spaceAfter=12
    )
    style_body = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9
    )

    elements = []

    # 1. Judul & Periode
    elements.append(Paragraph(judul, style_judul))
    elements.append(Paragraph(f"Periode: {periode_teks}", style_sub))

    # 2. Tabel Ringkasan Metrik
    if ringkasan_metrik:
        data_ringkasan = [[k, v] for k, v in ringkasan_metrik]
        t_ringkasan = Table(data_ringkasan, colWidths=[240, 280])
        t_ringkasan.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('FONTNAME', (0, -2), (-1, -1), 'Helvetica-Bold'),
        ]))
        elements.append(t_ringkasan)
        elements.append(Spacer(1, 14))

    # 3. Tabel Rincian Transaksi
    elements.append(Paragraph("<b>Rincian Transaksi Kas Selama Periode:</b>", style_body))
    elements.append(Spacer(1, 6))

    data_transaksi = [kolom_tabel] + baris_tabel
    # Kolom: No, Tanggal, Keterangan, Masuk, Keluar, Sumber
    t_transaksi = Table(data_transaksi, colWidths=[25, 65, 230, 80, 80, 45])
    t_transaksi.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (3, 0), (4, -1), 'RIGHT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    elements.append(t_transaksi)

    doc.build(elements)
    return path_out

