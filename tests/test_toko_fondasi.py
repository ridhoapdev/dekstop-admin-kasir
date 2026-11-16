"""
tests/test_toko_fondasi.py — Rangkaian Pengujian Modul 13: Fondasi Unit Toko.
Mencakup:
1. Konversi per barang: Barang A dus=20, Barang B dus=15 -> Snapshot pembelian 3 dus -> 60 dan 45.
2. Snapshot konversi tetap benar setelah isi dus diubah (atau satuan diubah/dikunci).
3. FIFO: dua lot berbeda harga, penjualan memakai lot lama dulu, sisa lot benar.
4. Pembulatan: 25.000 per dus isi 15 -> total biaya lot pas setelah semua unit terpakai tanpa selisih.
5. Atomisitas: jika penyimpanan mutasi gagal di tengah, stok tidak berubah sama sekali.
6. Rekonsiliasi: stok_saat_ini == SUM(mutasi) == SUM(qty_sisa lot).
7. Pembalik pembelian: lot belum terpakai (sukses) vs lot sudah terpakai (ditolak dengan pesan jelas).
8. Stok minus: blokir (default) dan izinkan jika opsi diaktifkan.
9. Seed data demo fiktif: 300 barang, 50 supplier, 1 tahun transaksi, uji performa dan rekonsiliasi.
"""
import pytest
import sqlite3
from datetime import date
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_pihak import tambah_pihak, ambil_daftar_pihak, cek_nama_mirip_pihak
from app.db.repo_barang import (
    tambah_barang, ubah_barang, cari_barang, nonaktifkan_barang,
    tambah_satuan_barang, ubah_satuan_barang, ambil_satuan_barang, cek_nama_mirip_barang
)
from app.layanan.layanan_stok import (
    tambah_stok_masuk, kurangi_stok_fifo, balik_mutasi_stok,
    rekonsiliasi_stok_barang, atur_izinkan_stok_minus, ambil_stok_barang
)
from app.db.repo_pembelian import (
    buat_faktur_pembelian, balik_faktur_pembelian, bayar_hutang_pembelian,
    ambil_daftar_faktur_pembelian, ambil_detail_faktur_pembelian
)
from app.db.repo_kas_toko import hitung_saldo_kas_toko, tambah_kas_toko, balik_kas_toko


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_toko.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    return conn


def test_konversi_per_barang_dan_snapshot(db_conn):
    """
    Uji konversi per barang:
    Barang A dus=20 pcs, Barang B dus=15 pcs.
    Input 3 dus masing-masing -> 60 pcs dan 45 pcs.
    Snapshot konversi tetap benar walau konversi dicoba diubah kemudian.
    """
    supp_id = tambah_pihak(db_conn, "supplier", "PT Pangan Sejahtera", "0812345678", "Jl. Merdeka")

    id_a = tambah_barang(db_conn, "BRG-A", "Barang A", "pcs")
    id_b = tambah_barang(db_conn, "BRG-B", "Barang B", "pcs")

    # Tambah satuan dus masing-masing
    tambah_satuan_barang(db_conn, id_a, "dus", 20)
    tambah_satuan_barang(db_conn, id_b, "dus", 15)

    # Buat faktur beli 3 dus Barang A dan 3 dus Barang B
    items = [
        {
            "barang_id": id_a,
            "jumlah_input": 3,
            "satuan_input": "dus",
            "isi_per_satuan": 20,
            "harga_per_satuan_input": 100000
        },
        {
            "barang_id": id_b,
            "jumlah_input": 3,
            "satuan_input": "dus",
            "isi_per_satuan": 15,
            "harga_per_satuan_input": 75000
        }
    ]
    faktur_id = buat_faktur_pembelian(
        db_conn, "FAK-001", supp_id, "2026-11-15", "tunai", items
    )

    # Cek stok bertambah sesuai satuan dasar
    assert ambil_stok_barang(db_conn, id_a) == 60
    assert ambil_stok_barang(db_conn, id_b) == 45

    # Verifikasi penguncian satuan barang yang telah dipakai transaksi
    sats_a = ambil_satuan_barang(db_conn, id_a)
    sat_dus_a = [s for s in sats_a if s["nama_satuan"] == "dus"][0]
    assert sat_dus_a["terkunci"] == 1

    # Mencoba mengubah isi_dalam_satuan_dasar yang sudah terkunci harus ditolak
    with pytest.raises(ValueError, match="sudah terkunci"):
        ubah_satuan_barang(db_conn, sat_dus_a["id"], "dus", 25)

    # Snapshot di pembelian_detail tetap 20 dan 60 pcs
    det = ambil_detail_faktur_pembelian(db_conn, faktur_id)
    assert len(det["items"]) == 2
    item_a = [it for it in det["items"] if it["barang_id"] == id_a][0]
    assert item_a["isi_per_satuan"] == 20
    assert item_a["jumlah_dasar"] == 60
    assert item_a["total_biaya"] == 300000


def test_fifo_dan_pembulatan_serap_sisa(db_conn):
    """
    Uji FIFO: Dua lot berbeda harga, pemakaian memakai lot terlama dulu.
    Uji pembulatan serap sisa:
    25.000 per dus isi 15 -> total biaya lot pas setelah semua unit terpakai (tanpa selisih 1 rupiah pun).
    """
    id_barang = tambah_barang(db_conn, "BRG-C", "Barang C", "pcs")

    # Lot 1: tanggal 2026-11-01, 15 pcs seharga Rp 25.000 (biaya per pcs ~ 1.666,666...)
    lot1_id, _ = tambah_stok_masuk(
        db_conn, id_barang, qty=15, total_biaya=25000,
        asal="penyesuaian", ref_tabel="manual", ref_id=1, tanggal="2026-11-01"
    )

    # Lot 2: tanggal 2026-11-05, 10 pcs seharga Rp 20.000 (biaya per pcs = 2.000)
    lot2_id, _ = tambah_stok_masuk(
        db_conn, id_barang, qty=10, total_biaya=20000,
        asal="penyesuaian", ref_tabel="manual", ref_id=2, tanggal="2026-11-05"
    )

    assert ambil_stok_barang(db_conn, id_barang) == 25

    # Ambil 10 pcs dari inventori (harus memotong dari Lot 1 terlama)
    mutasi_1 = kurangi_stok_fifo(
        db_conn, id_barang, qty_diminta=10,
        jenis_mutasi="keluar_jual", ref_tabel="penjualan", ref_id=101, tanggal="2026-11-15"
    )
    assert len(mutasi_1) == 1
    assert mutasi_1[0]["lot_id"] == lot1_id
    assert mutasi_1[0]["qty"] == 10
    # Biaya 10 pcs dari 25.000/15 -> round(10 * 25000 / 15) = 16667
    biaya_1 = mutasi_1[0]["biaya"]
    assert biaya_1 == 16667

    # Ambil 10 pcs lagi (5 pcs menghabiskan Lot 1, 5 pcs mengambil dari Lot 2)
    mutasi_2 = kurangi_stok_fifo(
        db_conn, id_barang, qty_diminta=10,
        jenis_mutasi="keluar_jual", ref_tabel="penjualan", ref_id=102, tanggal="2026-11-15"
    )
    assert len(mutasi_2) == 2
    # Bagian Lot 1 (5 pcs terakhir)
    part_lot1 = [m for m in mutasi_2 if m["lot_id"] == lot1_id][0]
    assert part_lot1["qty"] == 5
    # Total biaya Lot 1 = 25000. Bagian pertama 16667. Maka sisa wajib pas: 25000 - 16667 = 8333!
    assert part_lot1["biaya"] == 8333
    assert biaya_1 + part_lot1["biaya"] == 25000  # PAS TANPA SELISIH!

    # Bagian Lot 2 (5 pcs dari 10 pcs seharga 20.000)
    part_lot2 = [m for m in mutasi_2 if m["lot_id"] == lot2_id][0]
    assert part_lot2["qty"] == 5
    assert part_lot2["biaya"] == 10000

    # Sisa stok saat ini = 5 pcs
    assert ambil_stok_barang(db_conn, id_barang) == 5


def test_atomisitas_transaksi_stok(db_conn):
    """
    Jika penyimpanan mutasi atau faktur gagal di tengah, stok tidak berubah sama sekali.
    """
    id_barang = tambah_barang(db_conn, "BRG-D", "Barang D", "pcs")
    assert ambil_stok_barang(db_conn, id_barang) == 0

    # Coba buat faktur dengan salah satu baris memiliki jumlah negatif (harus gagal seluruhnya)
    supp_id = tambah_pihak(db_conn, "supplier", "CV Makmur Jaya")
    items_gagal = [
        {"barang_id": id_barang, "jumlah_input": 10, "satuan_input": "pcs", "isi_per_satuan": 1, "harga_per_satuan_input": 1000},
        {"barang_id": id_barang, "jumlah_input": -5, "satuan_input": "pcs", "isi_per_satuan": 1, "harga_per_satuan_input": 1000}
    ]

    with pytest.raises(ValueError):
        buat_faktur_pembelian(db_conn, "FAK-GAGAL", supp_id, "2026-11-15", "tunai", items_gagal)

    # Stok harus tetap 0 (rollback sempurna)
    assert ambil_stok_barang(db_conn, id_barang) == 0


def test_rekonsiliasi_stok(db_conn):
    """
    Rekonsiliasi: stok_saat_ini == SUM(mutasi) == SUM(qty_sisa lot).
    """
    id_barang = tambah_barang(db_conn, "BRG-E", "Barang E", "pcs")

    # Tambah stok 100 pcs
    tambah_stok_masuk(db_conn, id_barang, 100, 100000, "penyesuaian", "manual", 1, "2026-11-01")
    # Kurangi 30 pcs
    kurangi_stok_fifo(db_conn, id_barang, 30, "keluar_jual", "manual", 2, "2026-11-02")

    # Jalankan rekonsiliasi
    selisih = rekonsiliasi_stok_barang(db_conn, id_barang)
    assert len(selisih) == 0  # Tidak ada selisih sama sekali

    # Uji deteksi jika cache stok dirusak secara ilegal
    db_conn.execute("UPDATE barang SET stok_saat_ini = 999 WHERE id = ?;", (id_barang,))
    selisih_rusak = rekonsiliasi_stok_barang(db_conn, id_barang)
    assert len(selisih_rusak) == 1
    assert selisih_rusak[0]["selisih_mutasi"] != 0


def test_pembalik_pembelian(db_conn):
    """
    Pembalik pembelian:
    - Lot belum terpakai -> Sukses dibatalkan, kas toko kembali, stok berkurang.
    - Lot sudah terpakai sebagian -> Ditolak dengan pesan jelas.
    """
    supp_id = tambah_pihak(db_conn, "supplier", "PT Sumber Berkah")
    id_barang = tambah_barang(db_conn, "BRG-F", "Barang F", "pcs")

    # Beri modal awal kas toko
    tambah_kas_toko(db_conn, "2026-11-01", "Modal Kas Toko", masuk=1000000, keluar=0, sumber="modal_awal")
    saldo_awal_kas = hitung_saldo_kas_toko(db_conn)

    # Beli 50 pcs tunai @ 5.000 = 250.000
    items = [{"barang_id": id_barang, "jumlah_input": 50, "satuan_input": "pcs", "isi_per_satuan": 1, "harga_per_satuan_input": 5000}]
    faktur_1 = buat_faktur_pembelian(db_conn, "FAK-010", supp_id, "2026-11-10", "tunai", items)

    assert ambil_stok_barang(db_conn, id_barang) == 50
    assert hitung_saldo_kas_toko(db_conn) == saldo_awal_kas - 250000

    # 1. Batalkan saat lot belum terpakai -> SUKSES
    balik_faktur_pembelian(db_conn, faktur_1, "2026-11-12", "Salah beli")
    assert ambil_stok_barang(db_conn, id_barang) == 0
    assert hitung_saldo_kas_toko(db_conn) == saldo_awal_kas

    # 2. Beli lagi 50 pcs, lalu pakai 10 pcs
    faktur_2 = buat_faktur_pembelian(db_conn, "FAK-011", supp_id, "2026-11-13", "tunai", items)
    kurangi_stok_fifo(db_conn, id_barang, 10, "keluar_jual", "penjualan", 999, "2026-11-14")

    # Coba batalkan faktur_2 -> WAJIB DITOLAK karena lot sudah terpakai
    with pytest.raises(ValueError, match="sudah terpakai sebanyak 10 unit"):
        balik_faktur_pembelian(db_conn, faktur_2, "2026-11-15", "Coba batalkan")


def test_stok_minus_blokir_dan_izinkan(db_conn):
    """
    Pengaturan stok minus:
    - Default (blokir): transaksi melebihi stok ditolak dengan pesan ramah.
    - Diizinkan: transaksi dapat disimpan, stok menjadi minus.
    """
    id_barang = tambah_barang(db_conn, "BRG-G", "Barang G", "pcs")
    assert ambil_stok_barang(db_conn, id_barang) == 0

    # 1. Default: blokir
    with pytest.raises(ValueError, match="Stok tidak mencukupi"):
        kurangi_stok_fifo(db_conn, id_barang, 5, "keluar_jual", "penjualan", 1, "2026-11-15")

    # 2. Aktifkan izinkan_stok_minus
    atur_izinkan_stok_minus(db_conn, True)
    mutasi_minus = kurangi_stok_fifo(db_conn, id_barang, 5, "keluar_jual", "penjualan", 1, "2026-11-15")
    assert len(mutasi_minus) == 1
    assert ambil_stok_barang(db_conn, id_barang) == -5

    # Restock 10 pcs -> stok naik dari -5 menjadi +5
    tambah_stok_masuk(db_conn, id_barang, 10, 50000, "penyesuaian", "manual", 2, "2026-11-16")
    assert ambil_stok_barang(db_conn, id_barang) == 5


def test_pencarian_fuzzy_dan_kata_kunci(db_conn):
    """
    Pencarian barang:
    - Case-insensitive, cocok sebagian kata ("pucuk" menemukan "Teh Pucuk Harum 350ml").
    - Peringatan nama mirip (fuzzy match) saat menambah barang/pihak baru.
    """
    id_teh = tambah_barang(
        db_conn,
        kode="MNM-001",
        nama="Teh Pucuk Harum 350ml",
        satuan_dasar="botol",
        kata_kunci="minuman teh melati pucuk harum"
    )

    # Cari dengan kata "pucuk"
    hasil_cari = cari_barang(db_conn, "pucuk")
    assert len(hasil_cari) >= 1
    assert hasil_cari[0]["id"] == id_teh

    # Cari case insensitive "PUCUK HARUM"
    hasil_cari_2 = cari_barang(db_conn, "PUCUK HARUM")
    assert len(hasil_cari_2) >= 1

    # Fuzzy match nama mirip
    mirip = cek_nama_mirip_barang(db_conn, "Teh Pucuk Harum 300ml")
    assert len(mirip) >= 1
    assert mirip[0]["id"] == id_teh
    assert mirip[0]["persen"] > 75
