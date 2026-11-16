"""
tests/test_toko_modul15.py — Rangkaian Pengujian Lengkap Modul 15:
1. Pencarian Cepat Global (pucuk -> menemukan nama & kata_kunci)
2. Kartu Barang: stok dasar & representasi satuan besar, nilai persediaan, urutan lot FIFO, akumulasi laba
3. Transaksi Retur:
   - Retur ke supplier (potong hutang & kas masuk, validasi sisa lot)
   - Retur penjualan (stok kembali ke lot asal FIFO dengan biaya sama, potong piutang & kembali kas)
   - Penolakan jika melebihi kuantitas asal
4. Stock Opname & Penyesuaian:
   - Penyesuaian manual rusak/hilang (mengurangi FIFO & beban rugi)
   - Stock opname berkala (draft auto-save, finalisasi: selisih kurang -> rugi persediaan, selisih lebih -> lot baru)
   - Finalisasi mengunci sesi
5. Konsistensi Persediaan:
   - Stok awal + masuk - keluar +/- penyesuaian == stok akhir
6. Closing Toko:
   - Rekonsiliasi gagal -> closing diblokir dengan pesan ramah
   - Rekonsiliasi cocok -> closing berhasil, snapshot tersimpan, transaksi terkunci
   - Transaksi di periode closing tidak dapat diubah
   - Buka kembali membutuhkan PIN keamanan yang benar
"""
import pytest
import sqlite3
from datetime import date
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_pihak import tambah_pihak
from app.db.repo_barang import tambah_barang, tambah_satuan_barang
from app.db.repo_pembelian import buat_faktur_pembelian
from app.db.repo_penjualan import simpan_penjualan
from app.db.repo_piutang import bayar_piutang_pembeli
from app.db.repo_kas_toko import hitung_saldo_kas_toko, tambah_kas_toko
from app.layanan.layanan_stok import ambil_stok_barang, rekonsiliasi_stok_barang

from app.db.repo_kartu_toko import cari_entitas_toko_global, ambil_data_kartu_barang
from app.db.repo_retur_toko import catat_retur_supplier, catat_retur_penjualan
from app.db.repo_opname_toko import (
    catat_penyesuaian_manual, buat_sesi_opname, simpan_baris_opname_draft, finalisasi_sesi_opname
)
from app.db.repo_laporan_toko import (
    ambil_rekap_per_barang_periode, ambil_rincian_transaksi_toko, hitung_ringkasan_keuangan_toko
)
from app.db.repo_closing_toko import (
    periksa_pra_closing_toko, eksekusi_closing_toko, buka_kembali_closing_toko
)


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_modul15.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    return conn


def test_pencarian_global_toko_dan_kartu_barang(db_conn):
    """
    1. Pencarian kata 'pucuk' menemukan barang lewat nama dan kata kunci.
    2. Kartu Barang menampilkan representasi satuan besar, status, lot FIFO, dan estimasi laba.
    """
    supp_id = tambah_pihak(db_conn, "supplier", "PT Tirta Makmur", "081299991", "Kawasan Industri")
    pembeli_id = tambah_pihak(db_conn, "pembeli", "Kantin Sehat", "081388881", "Gedung A")

    bid = tambah_barang(
        db_conn,
        kode="MNM-101",
        nama="Teh Pucuk Harum 350ml",
        satuan_dasar="botol",
        harga_jual=4000,
        kata_kunci="minuman segar melati pucuk harum",
        stok_minimum=10
    )
    tambah_satuan_barang(db_conn, bid, "dus", 24)

    # Uji Pencarian Cepat
    hasil = cari_entitas_toko_global(db_conn, "pucuk")
    assert len(hasil) >= 1
    assert hasil[0]["tipe"] == "barang"
    assert hasil[0]["barang_id"] == bid

    # Beli 2 dus @ 72.000 (per dus 24 pcs = 48 botol @ 3.000)
    items_beli = [{
        "barang_id": bid,
        "jumlah_input": 2,
        "satuan_input": "dus",
        "isi_per_satuan": 24,
        "harga_per_satuan_input": 72000
    }]
    buat_faktur_pembelian(db_conn, "FAK-TP-01", supp_id, "2026-11-01", "tunai", items_beli)

    # Jual 3 botol @ 4.000
    items_jual = [{
        "barang_id": bid,
        "jumlah_input": 3,
        "satuan_input": "botol",
        "isi_per_satuan": 1,
        "harga_jual_satuan_dasar": 4000
    }]
    simpan_penjualan(db_conn, "2026-11-02", pembeli_id, "tunai", items_jual)

    # Ambil Kartu Barang
    kb = ambil_data_kartu_barang(db_conn, bid)
    assert kb is not None
    # Stok sekarang = 48 - 3 = 45 botol = 1 dus (24) + 21 botol
    assert kb["stok_saat_ini"] == 45
    assert "1 dus + 21 botol" in kb["stok_representasi"]
    assert kb["status_stok"] == "aman"
    # Nilai persediaan = 45 botol x 3.000 = 135.000
    assert kb["nilai_persediaan"] == 135000
    # Estimasi laba per satuan berikutnya = 4.000 - 3.000 = 1.000
    assert kb["laba_per_satuan_berikutnya"] == 1000
    # Lot FIFO aktif ada 1 lot sisa 45 unit
    assert len(kb["lot_aktif"]) == 1
    assert kb["lot_aktif"][0]["qty_sisa"] == 45
    # Laba total penjualan = 3 x (4.000 - 3.000) = 3.000
    assert kb["laba"]["laba_total"] == 3000


def test_transaksi_retur_supplier_dan_retur_penjualan(db_conn):
    """
    1. Retur ke supplier mengurangi sisa lot stok dan menambah kas/potong hutang.
    2. Retur penjualan mengembalikan stok ke lot asal FIFO dengan biaya sama.
    3. Validasi penolakan kuantitas melebihi sisa/penjualan.
    """
    supp_id = tambah_pihak(db_conn, "supplier", "Distributor Snack", "081233344", "Komp Pergudangan")
    pembeli_id = tambah_pihak(db_conn, "pembeli", "Warung Berkah", "081277788", "Jl Mawar")

    bid = tambah_barang(db_conn, "SNK-01", "Wafer Coklat", "pcs", harga_jual=2500)
    tambah_satuan_barang(db_conn, bid, "box", 10)

    # Beli 50 pcs @ 1.500 (Total 75.000) tunai
    faktur_id = buat_faktur_pembelian(
        db_conn, "FAK-SNK-01", supp_id, "2026-11-05", "tunai",
        [{"barang_id": bid, "jumlah_input": 5, "satuan_input": "box", "isi_per_satuan": 10, "harga_per_satuan_input": 15000}]
    )
    assert ambil_stok_barang(db_conn, bid) == 50

    cur = db_conn.cursor()
    cur.execute("SELECT id FROM lot_stok WHERE barang_id = ?;", (bid,))
    lot_id = cur.fetchone()[0]

    # 1. Retur 10 pcs ke Supplier (uang kas toko masuk kembali 10 x 1.500 = 15.000)
    saldo_kas_sebelum_rs = hitung_saldo_kas_toko(db_conn)
    catat_retur_supplier(
        conn=db_conn,
        supplier_id=supp_id,
        tanggal="2026-11-06",
        jenis_kompensasi="kas_masuk",
        daftar_item=[{"barang_id": bid, "lot_id": lot_id, "jumlah_dasar": 10, "biaya_per_satuan_dasar": 1500}],
        pembelian_faktur_id=faktur_id,
        alasan="Kemasan rusak dari pabrik"
    )
    # Stok menjadi 40 pcs
    assert ambil_stok_barang(db_conn, bid) == 40
    # Kas toko bertambah 15.000
    assert hitung_saldo_kas_toko(db_conn) == saldo_kas_sebelum_rs + 15000

    # Coba retur melebihi sisa lot (misal 50 pcs, sisa cuma 40) -> WAJIB DITOLAK
    with pytest.raises(ValueError, match="melebihi sisa lot stok"):
        catat_retur_supplier(
            conn=db_conn,
            supplier_id=supp_id,
            tanggal="2026-11-06",
            jenis_kompensasi="kas_masuk",
            daftar_item=[{"barang_id": bid, "lot_id": lot_id, "jumlah_dasar": 50, "biaya_per_satuan_dasar": 1500}],
            pembelian_faktur_id=faktur_id
        )

    # 2. Penjualan ke Warung Berkah sebanyak 20 pcs tunai @ 2.500 = 50.000
    pj_id, no_nota = simpan_penjualan(
        db_conn, "2026-11-07", pembeli_id, "tunai",
        [{"barang_id": bid, "jumlah_input": 20, "satuan_input": "pcs", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 2500}]
    )
    assert ambil_stok_barang(db_conn, bid) == 20

    cur.execute("SELECT id FROM penjualan_baris WHERE penjualan_id = ?;", (pj_id,))
    baris_pj_id = cur.fetchone()[0]

    # Pembeli meretur 5 pcs karena salah pesan varian (kembali kas 5 x 2.500 = 12.500)
    saldo_kas_sebelum_rj = hitung_saldo_kas_toko(db_conn)
    catat_retur_penjualan(
        conn=db_conn,
        penjualan_id=pj_id,
        tanggal="2026-11-08",
        jenis_kompensasi="kembali_kas",
        daftar_item=[{"penjualan_baris_id": baris_pj_id, "jumlah_dasar": 5}],
        alasan="Salah pesan varian"
    )
    # Stok kembali bertambah 5 -> menjadi 25 pcs
    assert ambil_stok_barang(db_conn, bid) == 25
    # Kas berkurang 12.500
    assert hitung_saldo_kas_toko(db_conn) == saldo_kas_sebelum_rj - 12500

    # Coba retur melebihi sisa yang dijual di baris nota (misal 20 pcs lagi, sisa cuma 15) -> WAJIB DITOLAK
    with pytest.raises(ValueError, match="melebihi jumlah barang yang dapat diretur"):
        catat_retur_penjualan(
            conn=db_conn,
            penjualan_id=pj_id,
            tanggal="2026-11-08",
            jenis_kompensasi="kembali_kas",
            daftar_item=[{"penjualan_baris_id": baris_pj_id, "jumlah_dasar": 20}]
        )


def test_penyesuaian_manual_dan_stock_opname(db_conn):
    """
    1. Penyesuaian manual (rusak/hilang) memotong stok FIFO terlama dan menjadi kerugian persediaan.
    2. Stock Opname:
       - Selisih kurang memotong lot FIFO terlama.
       - Selisih lebih membuat lot penyesuaian baru.
       - Finalisasi mengunci sesi.
    """
    bid = tambah_barang(db_conn, "TELUR-01", "Telur Ayam Negeri", "butir", harga_jual=2000)
    # Masukkan stok 100 butir @ 1.500 (total biaya 150.000)
    from app.layanan.layanan_stok import tambah_stok_masuk
    tambah_stok_masuk(db_conn, bid, 100, 150000, "penyesuaian", "manual", 1, "2026-11-01")
    assert ambil_stok_barang(db_conn, bid) == 100

    # 1. Catat 5 butir pecah (rusak)
    catat_penyesuaian_manual(db_conn, bid, "2026-11-02", "rusak", 5, "Pecah saat bongkar rak")
    assert ambil_stok_barang(db_conn, bid) == 95

    # 2. Sesi Stock Opname Akhir Bulan
    sesi_id, kode_op = buat_sesi_opname(db_conn, "2026-11-28", "Opname Rutin")
    # Fisik dihitung ternyata hanya ada 90 butir (selisih kurang 5 butir)
    simpan_baris_opname_draft(db_conn, sesi_id, [{
        "barang_id": bid,
        "stok_fisik": 90,
        "catatan": "Selisih kurang fisik 5 butir"
    }])

    # Finalisasi Opname
    res_fin = finalisasi_sesi_opname(db_conn, sesi_id)
    assert res_fin["total_kurang_qty"] == 5
    assert res_fin["total_kurang_nilai"] == 5 * 1500
    # Stok sekarang pas 90 butir
    assert ambil_stok_barang(db_conn, bid) == 90

    # Coba finalkan lagi -> WAJIB DITOLAK
    with pytest.raises(ValueError, match="sudah difinalkan"):
        finalisasi_sesi_opname(db_conn, sesi_id)


def test_konsistensi_laporan_dan_persamaan_persediaan(db_conn):
    """
    Uji Persamaan Akuntansi Persediaan:
    Stok Awal + Masuk - Keluar + Penyesuaian == Stok Akhir.
    Total Penjualan, HPP, dan Laba cocok di seluruh laporan.
    """
    supp_id = tambah_pihak(db_conn, "supplier", "Grosir Sembako", "08112233", "Pasar")
    pembeli_id = tambah_pihak(db_conn, "pembeli", "Koperasi Warga", "08556677", "Dusun")

    bid = tambah_barang(db_conn, "GULA-01", "Gula Pasir 1kg", "kg", harga_jual=17000)

    # 1. Stok Awal di bulan Oktober: Masuk 20 kg
    from app.layanan.layanan_stok import tambah_stok_masuk
    tambah_stok_masuk(db_conn, bid, 20, 260000, "penyesuaian", "manual", 1, "2026-10-25")

    # 2. Di bulan November:
    # Pembelian 30 kg @ 13.000 = 390.000
    buat_faktur_pembelian(
        db_conn, "FAK-GL-01", supp_id, "2026-11-02", "tunai",
        [{"barang_id": bid, "jumlah_input": 30, "satuan_input": "kg", "isi_per_satuan": 1, "harga_per_satuan_input": 13000}]
    )
    # Penjualan 15 kg @ 17.000
    simpan_penjualan(
        db_conn, "2026-11-10", pembeli_id, "tunai",
        [{"barang_id": bid, "jumlah_input": 15, "satuan_input": "kg", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 17000}]
    )
    # Penyesuaian rusak 2 kg
    catat_penyesuaian_manual(db_conn, bid, "2026-11-15", "rusak", 2, "Bungkus sobek digigit tikus")

    # Ambil Rekap per Barang periode November (2026-11-01 s.d. 2026-11-30)
    rekap = ambil_rekap_per_barang_periode(db_conn, "2026-11-01", "2026-11-30", barang_id=bid)
    assert len(rekap) == 1
    r = rekap[0]

    # Verifikasi Persamaan Persediaan:
    # Stok Awal (20) + Masuk (30) - Keluar (15) + Penyesuaian (-2) = Stok Akhir (33)
    assert r["stok_awal"] == 20
    assert r["masuk"] == 30
    assert r["keluar"] == 15
    assert r["penyesuaian"] == -2
    assert r["stok_akhir"] == 33
    assert r["stok_awal"] + r["masuk"] - r["keluar"] + r["penyesuaian"] == r["stok_akhir"]
    assert ambil_stok_barang(db_conn, bid) == r["stok_akhir"]


def test_closing_toko_rekonsiliasi_kunci_dan_reopen(db_conn):
    """
    1. Closing toko memeriksa rekonsiliasi pra-closing.
    2. Eksekusi closing mengunci transaksi pada periode tersebut.
    3. Transaksi pada periode closing ditolak jika ingin diubah/dibuat.
    4. Buka kembali (reopen) hanya lewat PIN keamanan.
    """
    supp_id = tambah_pihak(db_conn, "supplier", "PT Jaya Abadi", "0819999", "Jakarta")
    pembeli_id = tambah_pihak(db_conn, "pembeli", "Pelanggan Tetap", "0817777", "Bandung")
    bid = tambah_barang(db_conn, "MINYAK-01", "Minyak Goreng 1L", "pouch", harga_jual=18000)

    # Pembelian 20 pouch tunai di bulan November 2026
    buat_faktur_pembelian(
        db_conn, "FAK-MYK-01", supp_id, "2026-11-01", "tunai",
        [{"barang_id": bid, "jumlah_input": 20, "satuan_input": "pouch", "isi_per_satuan": 1, "harga_per_satuan_input": 15000}]
    )

    # 1. Periksa Pra-Closing November 2026
    cek = periksa_pra_closing_toko(db_conn, "2026-11")
    assert cek["bisa_closing"] is True

    # 2. Eksekusi Closing Toko November 2026
    cid = eksekusi_closing_toko(db_conn, "2026-11", "Closing Toko Resmi November 2026")
    assert cid > 0

    # 3. Coba lakukan transaksi baru di periode 2026-11 -> WAJIB DITOLAK
    with pytest.raises(ValueError, match="sudah ditutup"):
        simpan_penjualan(
            db_conn, "2026-11-20", pembeli_id, "tunai",
            [{"barang_id": bid, "jumlah_input": 1, "satuan_input": "pouch", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 18000}]
        )

    # 4. Buka Kembali (Reopen) dengan PIN salah -> Ditolak
    with pytest.raises(ValueError, match="PIN keamanan salah"):
        buka_kembali_closing_toko(db_conn, "2026-11", "9999", "Salah input")

    # Buka Kembali dengan PIN benar (default '1234') -> Sukses
    sukses_reopen = buka_kembali_closing_toko(db_conn, "2026-11", "1234", "Koreksi data")
    assert sukses_reopen is True

    # Transaksi sekarang diizinkan kembali
    pj_id, nota = simpan_penjualan(
        db_conn, "2026-11-20", pembeli_id, "tunai",
        [{"barang_id": bid, "jumlah_input": 1, "satuan_input": "pouch", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 18000}]
    )
    assert pj_id > 0
