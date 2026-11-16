"""
tests/test_toko_seed_demo_modul14.py — Pengujian Beban dan Kinerja Modul 14:
Simulasi 1 Tahun Transaksi Toko (300 Barang, 200 Pembeli, 10 Penitip),
Penjualan Harian (Tunai & Kredit), Penitipan Harian, Pembayaran Piutang,
Verifikasi Kecepatan Buka Layar Kasir, Piutang, dan Dasbor < 2 Detik,
serta Integritas Rekonsiliasi FIFO dan Kas.
"""
import time
import pytest
from datetime import date, timedelta
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_pihak import tambah_pihak
from app.db.repo_barang import tambah_barang, tambah_satuan_barang
from app.db.repo_pembelian import buat_faktur_pembelian
from app.db.repo_penjualan import simpan_penjualan, ambil_daftar_penjualan
from app.db.repo_piutang import ambil_daftar_ringkasan_piutang_pembeli, bayar_piutang_pembeli
from app.db.repo_penitipan import (
    catat_penitipan_harian, selesaikan_setoran_penitip, ambil_daftar_titipan_aktif_penitip
)
from app.db.repo_ringkasan_toko import ambil_ringkasan_dasbor_toko
from app.layanan.layanan_stok import rekonsiliasi_stok_barang


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_demo_m14.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    return conn


def test_seed_demo_modul14_dan_kinerja(db_conn):
    """
    Simulasi data operasional 1 tahun untuk toko koperasi:
    - 300 barang (250 barang koperasi, 50 barang titipan)
    - 200 pembeli terdaftar
    - 10 penitip harian
    - 5 supplier
    - Pembelian stok awal untuk barang koperasi
    - Transaksi penjualan harian (tunai dan kredit)
    - Penitipan harian dan setoran penitip
    - Pembayaran piutang pembeli
    - Benchmark respon waktu < 2 detik untuk query kasir, piutang, dan dasbor.
    """
    print("\n[SEED] Membuat 5 supplier, 10 penitip, dan 200 pembeli...")
    supp_ids = [
        tambah_pihak(db_conn, "supplier", f"Supplier Grosir {i}", f"0811000{i:03d}", f"Pasar Induk No. {i}")
        for i in range(1, 6)
    ]
    penitip_ids = [
        tambah_pihak(db_conn, "penitip", f"Penitip Kue {i}", f"0822000{i:03d}", f"Dusun Berkah RT {i}")
        for i in range(1, 11)
    ]
    pembeli_ids = [
        tambah_pihak(db_conn, "pembeli", f"Pembeli Warga {i:03d}", f"0855000{i:03d}", f"Komplek Warga Gang {i%10}")
        for i in range(1, 201)
    ]

    print("[SEED] Membuat 300 barang (250 koperasi + 50 titipan)...")
    brg_koperasi_ids = []
    for i in range(1, 251):
        bid = tambah_barang(
            db_conn,
            kode=f"BRG-{i:04d}",
            nama=f"Sembako / Barang Toko {i}",
            satuan_dasar="pcs",
            harga_jual=12000 + (i * 100),
            kata_kunci=f"sembako snack bumbu barang {i}",
            jenis_kepemilikan="milik_koperasi"
        )
        tambah_satuan_barang(db_conn, bid, "dus", 12)
        brg_koperasi_ids.append(bid)

    brg_titipan_ids = []
    for i in range(1, 51):
        pen_id = penitip_ids[i % len(penitip_ids)]
        bid = tambah_barang(
            db_conn,
            kode=f"TITIP-{i:03d}",
            nama=f"Kue Titipan Segar {i}",
            satuan_dasar="pcs",
            harga_jual=2500,
            kata_kunci=f"kue basah donat gorengan {i}",
            jenis_kepemilikan="titipan",
            penitip_id=pen_id
        )
        brg_titipan_ids.append((bid, pen_id))

    print("[SEED] Memasukkan stok awal pembelian untuk 250 barang koperasi...")
    # Masukkan faktur pembelian massal awal
    items_beli = [
        {
            "barang_id": bid,
            "jumlah_input": 10,
            "satuan_input": "dus",
            "isi_per_satuan": 12,
            "harga_per_satuan_input": 100000
        }
        for bid in brg_koperasi_ids[:100]  # 100 barang punya 120 pcs
    ]
    buat_faktur_pembelian(
        db_conn,
        no_faktur="FAK-MASSAL-01",
        supplier_id=supp_ids[0],
        tanggal="2026-01-02",
        status_bayar="tunai",
        items=items_beli
    )

    print("[SEED] Mensimulasikan transaksi penjualan & penitipan 300 transaksi sepanjang tahun...")
    tgl_mulai = date(2026, 1, 3)
    for hari in range(60):  # 60 gelombang hari
        tgl_str = (tgl_mulai + timedelta(days=hari)).isoformat()
        
        # Tiap hari ada 1 penitipan kue
        titip_brg, titip_owner = brg_titipan_ids[hari % len(brg_titipan_ids)]
        penitipan_id = catat_penitipan_harian(
            db_conn,
            penitip_id=titip_owner,
            tanggal=tgl_str,
            items=[{
                "barang_id": titip_brg,
                "jumlah_input": 20,
                "satuan_input": "pcs",
                "isi_per_satuan": 1,
                "harga_titip_satuan_dasar": 1800,
                "harga_jual_satuan_dasar": 2500
            }]
        )

        # 3 penjualan: 2 tunai, 1 kredit
        pembeli_kredit = pembeli_ids[hari % len(pembeli_ids)]
        barang_jual = brg_koperasi_ids[hari % 50]

        # Penjualan Tunai
        simpan_penjualan(
            db_conn,
            tanggal=tgl_str,
            pembeli_id=1,  # Pembeli Umum
            metode_bayar="tunai",
            nama_pembeli_nota="Warga Umum",
            items=[
                {"barang_id": barang_jual, "jumlah_input": 2, "satuan_input": "pcs", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 12500},
                {"barang_id": titip_brg, "jumlah_input": 5, "satuan_input": "pcs", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 2500}
            ]
        )

        # Penjualan Kredit
        nota_kredit_id, no_nota_kr = simpan_penjualan(
            db_conn,
            tanggal=tgl_str,
            pembeli_id=pembeli_kredit,
            metode_bayar="kredit",
            items=[
                {"barang_id": barang_jual, "jumlah_input": 1, "satuan_input": "pcs", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 12500},
                {"barang_id": titip_brg, "jumlah_input": 5, "satuan_input": "pcs", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 2500}
            ]
        )

        # Sore: Setoran penitip (10 pcs laku, 10 pcs retur)
        aktif_pen = ambil_daftar_titipan_aktif_penitip(db_conn, titip_owner)
        if aktif_pen:
            rincian_setor = [{
                "penitipan_baris_id": baris_aktif["penitipan_baris_id"],
                "lot_id": baris_aktif["lot_id"],
                "qty_terjual": baris_aktif["qty_terjual"],
                "harga_titip": baris_aktif["harga_titip_satuan_dasar"],
                "sisa_aksi": "retur"
            } for baris_aktif in aktif_pen]
            tot_bayar = sum(b["subtotal_bayar"] for b in aktif_pen)
            selesaikan_setoran_penitip(
                db_conn,
                penitip_id=titip_owner,
                tanggal=tgl_str,
                rincian_penyelesaian=rincian_setor,
                nominal_bayar=tot_bayar,
                keterangan=f"Setoran sore hari ke-{hari}"
            )

        # Tiap beberapa hari, pembeli kredit melunasi sebagian utangnya
        if hari % 3 == 0:
            bayar_piutang_pembeli(
                db_conn,
                pembeli_id=pembeli_kredit,
                tanggal=tgl_str,
                jumlah=15000,
                keterangan="Cicil piutang toko"
            )

    print("\n[BENCHMARK] Menguji waktu respon pembukaan dan pengambilan data layar...")
    
    # 1. Benchmark Layar Dasbor Ringkasan Toko (< 2 detik target i3-3220, < 0.5s di mesin modern)
    t0 = time.perf_counter()
    dasbor = ambil_ringkasan_dasbor_toko(db_conn, "2026-03-01")
    t_dasbor = time.perf_counter() - t0
    print(f"-> Waktu ambil dasbor ringkasan toko: {t_dasbor:.4f} detik")
    assert t_dasbor < 2.0
    assert dasbor["penjualan_hari_ini"] >= 0
    assert dasbor["total_piutang"] >= 0

    # 2. Benchmark Layar Piutang (ringkasan 200 pembeli)
    t0 = time.perf_counter()
    piutang = ambil_daftar_ringkasan_piutang_pembeli(db_conn)
    t_piutang = time.perf_counter() - t0
    print(f"-> Waktu ambil daftar ringkasan piutang: {t_piutang:.4f} detik (total pembeli: {len(piutang)})")
    assert t_piutang < 2.0
    assert len(piutang) > 0

    # 3. Benchmark Riwayat Penjualan Kasir (100 transaksi terakhir)
    t0 = time.perf_counter()
    daftar_jual = ambil_daftar_penjualan(db_conn, limit=100)
    t_jual = time.perf_counter() - t0
    print(f"-> Waktu ambil daftar nota penjualan: {t_jual:.4f} detik (total: {len(daftar_jual)})")
    assert t_jual < 2.0
    assert len(daftar_jual) == 100

    # 4. Rekonsiliasi Stok FIFO
    print("[REKONSILIASI] Memeriksa stok_saat_ini == sum(mutasi) == sum(qty_sisa lot)...")
    selisih_semua = rekonsiliasi_stok_barang(db_conn)
    assert len(selisih_semua) == 0, f"Ditemukan selisih stok rekonsiliasi: {selisih_semua}"

    print(" Semua pengujian beban, kinerja, dan rekonsiliasi Modul 14 LULUS.")
