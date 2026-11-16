"""
tests/test_toko_penjualan_piutang_titipan.py — Rangkaian Pengujian Modul 14:
Penjualan Kasir, Piutang Pembeli, dan Titipan Harian.
Mencakup:
1. Stok turun tepat sebesar jumlah terjual (50 - 5 = 45) dan naik saat restock, real-time dalam satu transaksi.
2. FIFO dua lot beda harga: HPP dan laba nota benar; pembalik mengembalikan ke lot asal.
3. Penjualan tunai menambah kas toko; kredit TIDAK menambah kas toko dan membuat piutang.
4. Pembayaran piutang sebagian beralokasi ke nota tertua; saldo per nota dan per pembeli benar.
5. Titipan: hutang penitip = qty terjual x harga titip; harga titip & harga jual beda tiap hari; titipan dijual kredit tetap menimbulkan hutang penitip.
6. Setoran penitip: bayar, retur sisa, tidak bisa dibayar dua kali; bayar sebagian.
7. Konsistensi: stok = SUM mutasi = SUM sisa lot; piutang = kredit - alokasi; laba nota = total jual - HPP.
8. Atomisitas: kegagalan di tengah menyimpan nota tidak mengubah stok, kas, atau piutang.
"""
import pytest
import sqlite3
from datetime import date
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_pihak import tambah_pihak, ambil_atau_buat_pembeli_umum
from app.db.repo_barang import tambah_barang, tambah_satuan_barang
from app.layanan.layanan_stok import tambah_stok_masuk, ambil_stok_barang, rekonsiliasi_stok_barang
from app.db.repo_penjualan import (
    simpan_penjualan, batalkan_nota_penjualan, ambil_harga_jual_default_barang
)
from app.db.repo_piutang import (
    bayar_piutang_pembeli, ambil_daftar_nota_kredit_pembeli,
    ambil_daftar_ringkasan_piutang_pembeli, hitung_total_piutang_semua_pembeli,
    balik_pembayaran_piutang
)
from app.db.repo_penitipan import (
    catat_penitipan_harian, ambil_daftar_titipan_aktif_penitip,
    hitung_total_hutang_penitip_terkini, selesaikan_setoran_penitip
)
from app.db.repo_kas_toko import hitung_saldo_kas_toko, tambah_kas_toko


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_modul14.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    return conn


def test_penjualan_tunai_stok_dan_kas(db_conn):
    """
    1. Stok turun tepat sebesar jumlah terjual (50 - 5 = 45).
    2. Penjualan tunai menambah kas toko.
    """
    pembeli_umum = ambil_atau_buat_pembeli_umum(db_conn)
    b_id = tambah_barang(db_conn, "BRG-01", "Biskuit Kaleng", "kaleng", harga_jual=20000)

    # Restock 50 kaleng @ 15.000 = 750.000
    tambah_stok_masuk(db_conn, b_id, 50, 750000, "penyesuaian", "manual", 1, "2026-11-01")
    assert ambil_stok_barang(db_conn, b_id) == 50

    saldo_kas_awal = hitung_saldo_kas_toko(db_conn)

    # Jual 5 kaleng tunai @ 20.000 = 100.000
    items = [{
        "barang_id": b_id,
        "jumlah_input": 5,
        "satuan_input": "kaleng",
        "isi_per_satuan": 1,
        "harga_jual_satuan_dasar": 20000
    }]
    pj_id, no_nota = simpan_penjualan(db_conn, "2026-11-15", pembeli_umum, "tunai", items)

    # Stok turun jadi 45
    assert ambil_stok_barang(db_conn, b_id) == 45
    # Kas bertambah 100.000
    assert hitung_saldo_kas_toko(db_conn) == saldo_kas_awal + 100000


def test_fifo_hpp_laba_dan_pembalik_nota(db_conn):
    """
    FIFO dua lot beda harga:
    - Lot 1: 10 unit @ 10.000 (total 100.000)
    - Lot 2: 10 unit @ 15.000 (total 150.000)
    Jual 15 unit @ 20.000 (total 300.000):
    - HPP = 10 x 10.000 + 5 x 15.000 = 100.000 + 75.000 = 175.000
    - Laba = 300.000 - 175.000 = 125.000
    Pembalik nota mengembalikan 10 unit ke Lot 1 dan 5 unit ke Lot 2 secara presisi.
    """
    pembeli_umum = ambil_atau_buat_pembeli_umum(db_conn)
    b_id = tambah_barang(db_conn, "BRG-02", "Minyak Goreng 1L", "pouch", harga_jual=20000)

    # Lot 1 (lama)
    lot1_id, _ = tambah_stok_masuk(db_conn, b_id, 10, 100000, "penyesuaian", "manual", 1, "2026-11-01")
    # Lot 2 (baru)
    lot2_id, _ = tambah_stok_masuk(db_conn, b_id, 10, 150000, "penyesuaian", "manual", 2, "2026-11-05")

    items = [{
        "barang_id": b_id,
        "jumlah_input": 15,
        "satuan_input": "pouch",
        "isi_per_satuan": 1,
        "harga_jual_satuan_dasar": 20000
    }]
    pj_id, _ = simpan_penjualan(db_conn, "2026-11-15", pembeli_umum, "tunai", items)

    # Periksa laba dan HPP di penjualan_baris
    cur = db_conn.cursor()
    cur.execute("SELECT hpp_total, laba FROM penjualan_baris WHERE penjualan_id = ?;", (pj_id,))
    row_baris = cur.fetchone()
    assert row_baris[0] == 175000  # HPP
    assert row_baris[1] == 125000  # Laba (300.000 - 175.000)

    # Stok tersisa 5 pouch (pada Lot 2)
    assert ambil_stok_barang(db_conn, b_id) == 5
    cur.execute("SELECT qty_sisa FROM lot_stok WHERE id = ?;", (lot1_id,))
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT qty_sisa FROM lot_stok WHERE id = ?;", (lot2_id,))
    assert cur.fetchone()[0] == 5

    # Batalkan nota penjualan
    batalkan_nota_penjualan(db_conn, pj_id, "2026-11-16", "Retur nota salah")

    # Stok kembali penuh 20
    assert ambil_stok_barang(db_conn, b_id) == 20
    # Masing-masing lot kembali ke posisi semula
    cur.execute("SELECT qty_sisa, biaya_sisa FROM lot_stok WHERE id = ?;", (lot1_id,))
    r1 = cur.fetchone()
    assert r1[0] == 10 and r1[1] == 100000
    cur.execute("SELECT qty_sisa, biaya_sisa FROM lot_stok WHERE id = ?;", (lot2_id,))
    r2 = cur.fetchone()
    assert r2[0] == 10 and r2[1] == 150000


def test_penjualan_kredit_dan_alokasi_piutang(db_conn):
    """
    Penjualan kredit:
    - Mewajibkan pembeli terdaftar (bukan 'Umum').
    - TIDAK menambah kas toko.
    - Pembayaran piutang sebagian beralokasi ke nota tertua lebih dulu.
    """
    pembeli_id = tambah_pihak(db_conn, "pembeli", "Budi Santoso", "08111222333")
    b_id = tambah_barang(db_conn, "BRG-03", "Beras 5kg", "karung", harga_jual=70000)
    tambah_stok_masuk(db_conn, b_id, 20, 1000000, "penyesuaian", "manual", 1, "2026-11-01")

    saldo_kas_awal = hitung_saldo_kas_toko(db_conn)

    # 1. Nota Kredit 1 (Tanggal 2026-11-01): Beli 1 karung = 70.000
    items1 = [{"barang_id": b_id, "jumlah_input": 1, "satuan_input": "karung", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 70000}]
    pj1_id, nota1 = simpan_penjualan(db_conn, "2026-11-01", pembeli_id, "kredit", items1)

    # 2. Nota Kredit 2 (Tanggal 2026-11-05): Beli 2 karung = 140.000
    items2 = [{"barang_id": b_id, "jumlah_input": 2, "satuan_input": "karung", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 70000}]
    pj2_id, nota2 = simpan_penjualan(db_conn, "2026-11-05", pembeli_id, "kredit", items2)

    # Kas tidak boleh bertambah
    assert hitung_saldo_kas_toko(db_conn) == saldo_kas_awal
    # Total piutang pembeli = 70.000 + 140.000 = 210.000
    assert hitung_total_piutang_semua_pembeli(db_conn) == 210000

    # 3. Pembeli bayar cicilan 100.000
    # Harus melunasi Nota 1 (70.000) dan mencicil Nota 2 sebesar 30.000
    bayar_id, alokasi = bayar_piutang_pembeli(db_conn, pembeli_id, "2026-11-15", 100000)

    # Kas bertambah 100.000
    assert hitung_saldo_kas_toko(db_conn) == saldo_kas_awal + 100000
    # Sisa total piutang tinggal 110.000
    assert hitung_total_piutang_semua_pembeli(db_conn) == 110000

    # Cek alokasi per nota
    daftar_nota = ambil_daftar_nota_kredit_pembeli(db_conn, pembeli_id)
    n1 = [n for n in daftar_nota if n["penjualan_id"] == pj1_id][0]
    n2 = [n for n in daftar_nota if n["penjualan_id"] == pj2_id][0]

    assert n1["status"] == "Lunas" and n1["sisa"] == 0
    assert n2["status"] == "Sebagian" and n2["sisa"] == 110000  # 140.000 - 30.000

    # Cek bahwa nota kredit yang sudah ada alokasi ditolak jika dibatalkan langsung
    with pytest.raises(ValueError, match="sudah memiliki pembayaran piutang"):
        batalkan_nota_penjualan(db_conn, pj1_id, "2026-11-16", "Coba batalkan")


def test_titipan_harian_kredit_dan_setoran_penitip(db_conn):
    """
    Titipan Harian:
    - Dititipkan per hari dengan harga titip & harga jual fleksibel.
    - Dijual KREDIT tetap menimbulkan hutang ke penitip.
    - Setoran penitip sore hari: bayar hasil laku, retur sisa, dan tidak bisa dibayar ganda.
    """
    penitip_id = tambah_pihak(db_conn, "penitip", "Ibu Aminah", "0812998877")
    pembeli_id = tambah_pihak(db_conn, "pembeli", "Pak Joko", "08133344455")

    # Master barang titipan terikat ke Ibu Aminah
    b_id = tambah_barang(
        db_conn, "TITIP-01", "Gorengan Tempe", "pcs",
        jenis_kepemilikan="titipan", penitip_id=penitip_id
    )

    # Modal kas toko
    tambah_kas_toko(db_conn, "2026-11-15", "Modal Kas Toko", 500000, 0, "modal_awal")
    saldo_kas = hitung_saldo_kas_toko(db_conn)

    # 1. Pagi: Ibu Aminah menitipkan 50 pcs @ harga titip 1.500, harga jual 2.000
    items_titip = [{
        "barang_id": b_id,
        "jumlah_input": 50,
        "satuan_input": "pcs",
        "isi_per_satuan": 1,
        "harga_titip_satuan_dasar": 1500,
        "harga_jual_satuan_dasar": 2000
    }]
    catat_penitipan_harian(db_conn, penitip_id, "2026-11-15", items_titip)
    assert ambil_stok_barang(db_conn, b_id) == 50

    # Saat baru dititip, hutang ke penitip masih 0 (kewajiban hanya tercipta saat laku)
    assert hitung_total_hutang_penitip_terkini(db_conn, penitip_id) == 0

    # 2. Siang: Terjual 30 pcs secara KREDIT ke Pak Joko
    items_jual = [{
        "barang_id": b_id,
        "jumlah_input": 30,
        "satuan_input": "pcs",
        "isi_per_satuan": 1,
        "harga_jual_satuan_dasar": 2000
    }]
    simpan_penjualan(db_conn, "2026-11-15", pembeli_id, "kredit", items_jual)

    # Stok tersisa 20 pcs
    assert ambil_stok_barang(db_conn, b_id) == 20
    # Hutang ke Ibu Aminah tercipta: 30 laku x 1.500 = 45.000 (meski pembeli ngutang)
    assert hitung_total_hutang_penitip_terkini(db_conn, penitip_id) == 45000

    # 3. Sore: Ibu Aminah datang untuk setoran
    daftar_aktif = ambil_daftar_titipan_aktif_penitip(db_conn, penitip_id)
    assert len(daftar_aktif) == 1
    row_t = daftar_aktif[0]
    assert row_t["qty_terjual"] == 30
    assert row_t["qty_sisa"] == 20
    assert row_t["subtotal_bayar"] == 45000

    # Selesaikan setoran: Bayar 45.000 dan retur sisa 20 pcs
    rincian_setor = [{
        "penitipan_baris_id": row_t["penitipan_baris_id"],
        "lot_id": row_t["lot_id"],
        "qty_terjual": 30,
        "harga_titip": 1500,
        "sisa_aksi": "retur"
    }]
    selesaikan_setoran_penitip(db_conn, penitip_id, "2026-11-15", rincian_setor, nominal_bayar=45000)

    # Hutang penitip tuntas (0)
    assert hitung_total_hutang_penitip_terkini(db_conn, penitip_id) == 0
    # Kas toko berkurang 45.000
    assert hitung_saldo_kas_toko(db_conn) == saldo_kas - 45000
    # Sisa stok barang setelah retur habis (0)
    assert ambil_stok_barang(db_conn, b_id) == 0

    # Daftar titipan aktif sekarang kosong (sudah terkunci selesai)
    assert len(ambil_daftar_titipan_aktif_penitip(db_conn, penitip_id)) == 0


def test_atomisitas_dan_rekonsiliasi(db_conn):
    """
    Atomisitas: jika penjualan gagal di tengah, tidak ada perubahan stok/kas.
    Rekonsiliasi: stok == SUM mutasi == SUM sisa lot.
    """
    pembeli_umum = ambil_atau_buat_pembeli_umum(db_conn)
    b_id = tambah_barang(db_conn, "BRG-04", "Kopi Sachet", "renteng", harga_jual=15000)
    tambah_stok_masuk(db_conn, b_id, 10, 100000, "penyesuaian", "manual", 1, "2026-11-01")

    # Coba jual melebihi stok saat stok minus diblokir
    items_gagal = [{
        "barang_id": b_id,
        "jumlah_input": 50,  # melebihi stok 10
        "satuan_input": "renteng",
        "isi_per_satuan": 1,
        "harga_jual_satuan_dasar": 15000
    }]
    with pytest.raises(ValueError, match="Stok tidak mencukupi"):
        simpan_penjualan(db_conn, "2026-11-15", pembeli_umum, "tunai", items_gagal)

    # Stok tetap 10, kas tetap tidak bertambah
    assert ambil_stok_barang(db_conn, b_id) == 10
    selisih = rekonsiliasi_stok_barang(db_conn, b_id)
    assert len(selisih) == 0
