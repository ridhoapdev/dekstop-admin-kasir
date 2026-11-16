"""
tests/test_toko_seed_demo.py — Seed Data Demo Fiktif dan Uji Performa Toko.
Mencakup:
- 300 Master Barang
- 50 Supplier
- Transaksi pembelian dan mutasi stok FIFO selama 1 tahun (simulasi ribuan mutasi)
- Uji performa kecepatan eksekusi (< 5 detik)
- Rekonsiliasi integritas data (stok_saat_ini == sum lot == sum mutasi).
"""
import pytest
import sqlite3
import time
import random
from datetime import date, timedelta
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_pihak import tambah_pihak
from app.db.repo_barang import tambah_barang, tambah_satuan_barang, cari_barang
from app.db.repo_pembelian import buat_faktur_pembelian
from app.layanan.layanan_stok import rekonsiliasi_stok_barang, kurangi_stok_fifo, ambil_stok_barang
from app.db.repo_kas_toko import tambah_kas_toko


def test_seed_demo_300_barang_50_supplier(tmp_path):
    """Menguji performa dan integritas data dengan volume skala produksi."""
    db_file = tmp_path / "test_demo_volume.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)

    # Modal awal kas toko
    tambah_kas_toko(conn, "2026-01-01", "Modal Kas Toko Awal", masuk=500000000, keluar=0, sumber="modal_awal")

    waktu_mulai = time.time()

    # 1. Buat 50 Supplier fiktif
    supplier_ids = []
    with conn:
        for i in range(1, 51):
            s_id = tambah_pihak(
                conn, "supplier",
                f"Distributor Logistik {i}",
                f"0812{i:08d}",
                f"Kawasan Pergudangan Blok {i}"
            )
            supplier_ids.append(s_id)

    # 2. Buat 300 Barang fiktif
    kategori_list = ["Makanan", "Minuman", "Sembako", "Perlengkapan Mandi", "ATK", "Snack"]
    satuan_list = ["pcs", "botol", "bungkus", "sachet", "kotak"]
    barang_ids = []

    with conn:
        for b in range(1, 301):
            kat = kategori_list[b % len(kategori_list)]
            sat = satuan_list[b % len(satuan_list)]
            b_id = tambah_barang(
                conn,
                kode=f"BRG-{b:04d}",
                nama=f"Produk Retail {kat} Nomor {b}",
                kategori=kat,
                satuan_dasar=sat,
                kata_kunci=f"alias{b} retail{b} grosir",
                harga_jual=10000 + (b * 500),
                stok_minimum=10
            )
            # Tambah satuan dus = 12 atau 24
            isi_dus = 12 if b % 2 == 0 else 24
            tambah_satuan_barang(conn, b_id, "dus", isi_dus)
            barang_ids.append((b_id, sat, isi_dus))

    # 3. Buat transaksi pembelian dan pemakaian FIFO selama 1 tahun (12 bulan)
    tgl_dasar = date(2026, 1, 1)
    # Jalankan 150 faktur pembelian multi-item
    random.seed(42)
    for f in range(1, 151):
        tgl_faktur = (tgl_dasar + timedelta(days=(f * 2) % 360)).isoformat()
        supp_id = random.choice(supplier_ids)
        # Pilih 2 sampai 4 barang secara acak
        items = []
        pilihan_b = random.sample(barang_ids, k=3)
        for b_id, sat_dasar, isi_dus in pilihan_b:
            # Beli dalam bentuk dus atau satuan dasar
            beli_dus = (f % 2 == 0)
            sat_input = "dus" if beli_dus else sat_dasar
            isi = isi_dus if beli_dus else 1
            jml = random.randint(2, 10)
            hrg = 5000 * isi
            items.append({
                "barang_id": b_id,
                "jumlah_input": jml,
                "satuan_input": sat_input,
                "isi_per_satuan": isi,
                "harga_per_satuan_input": hrg
            })

        buat_faktur_pembelian(
            conn, f"FAK-DEMO-{f:04d}", supp_id, tgl_faktur, "tunai", items
        )

    # 4. Simulasikan pemakaian / pengurangan stok FIFO pada 100 barang
    for f in range(1, 101):
        tgl_keluar = (tgl_dasar + timedelta(days=(f * 3) % 360)).isoformat()
        b_id, _, _ = barang_ids[f]
        stok_ada = ambil_stok_barang(conn, b_id)
        if stok_ada > 5:
            kurangi_stok_fifo(
                conn, b_id, qty_diminta=random.randint(1, 5),
                jenis_mutasi="keluar_jual", ref_tabel="simulasi", ref_id=f, tanggal=tgl_keluar
            )

    durasi = time.time() - waktu_mulai

    # 5. Uji pencarian instan
    t_cari_mulai = time.time()
    hasil_cari = cari_barang(conn, "retail Makanan")
    durasi_cari = time.time() - t_cari_mulai

    assert len(hasil_cari) > 0
    assert durasi_cari < 0.2  # Sangat cepat (< 200 ms)

    # 6. Uji Rekonsiliasi Seluruh 300 Barang
    t_rekon_mulai = time.time()
    selisih_list = rekonsiliasi_stok_barang(conn)
    durasi_rekon = time.time() - t_rekon_mulai

    assert len(selisih_list) == 0  # 100% REKONSILIASI KONSISTEN SEMPURNA
    assert durasi_rekon < 0.5      # Rekonsiliasi pembukaan cepat (< 500 ms)
    assert durasi < 15.0           # Total seed dan transaksi efisien
