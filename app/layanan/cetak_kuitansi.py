"""
app/layanan/cetak_kuitansi.py — Layanan pembuatan kuitansi tanda terima PDF untuk anggota.
Menggunakan reportlab (A5 Landscape atau 1/2 A4) rapi dan siap cetak.
"""
from pathlib import Path
from typing import Union
from reportlab.lib.pagesizes import A5, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from app.util.format import format_rupiah, format_tanggal_indo


def buat_kuitansi_simpanan_pdf(
    tx_simpanan: dict,
    nama_koperasi: str,
    path_tujuan: Union[str, Path]
) -> Path:
    """
    Membuat file kuitansi PDF tanda terima simpanan:
    tx_simpanan: {id, tanggal, no_anggota, nama_anggota, unit, jenis, arah, jumlah, keterangan}
    """
    path_out = Path(path_tujuan)
    path_out.parent.mkdir(parents=True, exist_ok=True)

    # Ukuran A5 Landscape
    doc = SimpleDocTemplate(
        str(path_out),
        pagesize=landscape(A5),
        rightMargin=30,
        leftMargin=30,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    style_kop = ParagraphStyle(
        'Kop',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        textColor=colors.HexColor("#1E3A8A"),
        spaceAfter=2
    )
    style_judul = ParagraphStyle(
        'Judul',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        alignment=1,  # Center
        spaceAfter=12
    )
    style_body = ParagraphStyle('Body', fontName='Helvetica', fontSize=10, leading=14)
    style_body_bold = ParagraphStyle('BodyB', fontName='Helvetica-Bold', fontSize=10, leading=14)

    elements = []

    # 1. Header Koperasi & Judul
    elements.append(Paragraph(nama_koperasi.upper(), style_kop))
    elements.append(Paragraph("BUKTI TANDA TERIMA SIMPANAN", style_judul))

    # 2. Tabel Rincian Data
    arah_teks = "SETORAN SIMPANAN" if tx_simpanan.get("arah") == "setor" else "PENARIKAN SIMPANAN"
    rincian = [
        [Paragraph("No. Transaksi", style_body), Paragraph(f": #{tx_simpanan.get('id')}", style_body_bold)],
        [Paragraph("Tanggal Transaksi", style_body), Paragraph(f": {format_tanggal_indo(tx_simpanan.get('tanggal'))}", style_body)],
        [Paragraph("No. Anggota", style_body), Paragraph(f": {tx_simpanan.get('no_anggota')}", style_body)],
        [Paragraph("Nama Anggota", style_body), Paragraph(f": {tx_simpanan.get('nama_anggota')} (Unit: {tx_simpanan.get('unit') or '-'})", style_body_bold)],
        [Paragraph("Jenis Simpanan", style_body), Paragraph(f": Simpanan {str(tx_simpanan.get('jenis')).capitalize()} ({arah_teks})", style_body)],
        [Paragraph("Nominal", style_body), Paragraph(f": <b>{format_rupiah(tx_simpanan.get('jumlah', 0))}</b>", style_body_bold)],
        [Paragraph("Keterangan", style_body), Paragraph(f": {tx_simpanan.get('keterangan') or '-'}", style_body)]
    ]

    t_data = Table(rincian, colWidths=[130, 390])
    t_data.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_data)
    elements.append(Spacer(1, 20))

    # 3. Tanda Tangan
    ttd = [
        [Paragraph("Penerima / Petugas Kasir,", style_body), Paragraph("Anggota,", style_body)],
        [Spacer(1, 35), Spacer(1, 35)],
        [Paragraph("( .................................................... )", style_body),
         Paragraph(f"( {tx_simpanan.get('nama_anggota')} )", style_body)]
    ]
    t_ttd = Table(ttd, colWidths=[260, 260])
    elements.append(t_ttd)

    doc.build(elements)
    return path_out


def buat_kuitansi_angsuran_pdf(
    tx_angsuran: dict,
    nama_koperasi: str,
    path_tujuan: Union[str, Path]
) -> Path:
    """
    Membuat file kuitansi PDF tanda terima pembayaran angsuran:
    tx_angsuran: {id, tanggal, no_anggota, nama_anggota, unit, no_pinjaman, angsuran_ke,
                  bayar_pokok, bayar_jasa, denda, total_bayar, keterangan}
    """
    path_out = Path(path_tujuan)
    path_out.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(path_out),
        pagesize=landscape(A5),
        rightMargin=30,
        leftMargin=30,
        topMargin=25,
        bottomMargin=25
    )

    styles = getSampleStyleSheet()
    style_kop = ParagraphStyle('Kop', fontName='Helvetica-Bold', fontSize=13, textColor=colors.HexColor("#1E3A8A"), spaceAfter=2)
    style_judul = ParagraphStyle('Judul', fontName='Helvetica-Bold', fontSize=12, alignment=1, spaceAfter=12)
    style_body = ParagraphStyle('Body', fontName='Helvetica', fontSize=10, leading=14)
    style_body_bold = ParagraphStyle('BodyB', fontName='Helvetica-Bold', fontSize=10, leading=14)

    elements = []

    elements.append(Paragraph(nama_koperasi.upper(), style_kop))
    elements.append(Paragraph("BUKTI PEMBAYARAN ANGSURAN PINJAMAN", style_judul))

    angs_ke = f"Angsuran Ke-{tx_angsuran.get('angsuran_ke')}" if tx_angsuran.get("angsuran_ke") else "Pelunasan Dipercepat"
    tot = tx_angsuran.get("bayar_pokok", 0) + tx_angsuran.get("bayar_jasa", 0) + tx_angsuran.get("denda", 0)

    rincian = [
        [Paragraph("No. Pembayaran", style_body), Paragraph(f": #{tx_angsuran.get('id')}", style_body_bold)],
        [Paragraph("Tanggal Bayar", style_body), Paragraph(f": {format_tanggal_indo(tx_angsuran.get('tanggal'))}", style_body)],
        [Paragraph("No. Anggota / Nama", style_body), Paragraph(f": {tx_angsuran.get('no_anggota')} - {tx_angsuran.get('nama_anggota')} ({tx_angsuran.get('unit') or '-'})", style_body_bold)],
        [Paragraph("No. Pinjaman", style_body), Paragraph(f": {tx_angsuran.get('no_pinjaman')} ({angs_ke})", style_body)],
        [Paragraph("Rincian Pembayaran", style_body), Paragraph(f": Pokok: {format_rupiah(tx_angsuran.get('bayar_pokok', 0))} | Jasa: {format_rupiah(tx_angsuran.get('bayar_jasa', 0))} | Denda: {format_rupiah(tx_angsuran.get('denda', 0))}", style_body)],
        [Paragraph("Total Bayar", style_body), Paragraph(f": <b>{format_rupiah(tot)}</b>", style_body_bold)],
        [Paragraph("Keterangan", style_body), Paragraph(f": {tx_angsuran.get('keterangan') or '-'}", style_body)]
    ]

    t_data = Table(rincian, colWidths=[130, 390])
    t_data.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t_data)
    elements.append(Spacer(1, 20))

    ttd = [
        [Paragraph("Penerima / Petugas Kasir,", style_body), Paragraph("Penyetor / Anggota,", style_body)],
        [Spacer(1, 35), Spacer(1, 35)],
        [Paragraph("( .................................................... )", style_body),
         Paragraph(f"( {tx_angsuran.get('nama_anggota')} )", style_body)]
    ]
    t_ttd = Table(ttd, colWidths=[260, 260])
    elements.append(t_ttd)

    doc.build(elements)
    return path_out

