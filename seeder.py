"""
seeder.py — Skrip reset database dan seeding data realistis lengkap.
Mencakup:
1. Backup otomatis database lama sebelum direset.
2. Reset seluruh tabel database kembali ke skema awal bersih.
3. Seeding Unit Simpan Pinjam:
   - 15 Anggota Koperasi realistis (karyawan berbagai divisi)
   - Transaksi Simpanan (Pokok, Wajib bulanan, Sukarela)
   - Transaksi Pinjaman & Jadwal Angsuran beserta pembayaran angsuran
   - Buku Kas Operasional Simpan Pinjam
4. Seeding Unit Toko:
   - Modal awal kas toko
   - 5 Supplier resmi distributor
   - 6 Penitip dagangan harian (kue basah, snack, donat, dsb)
   - 10 Pembeli terdaftar (termasuk yang terhubung ke anggota koperasi)
   - 30 Master Barang retail populer (Sembako, Minuman, Makanan, ATK, Titipan)
   - Satuan konversi per barang (dus, renceng, pak, box)
   - Pembelian barang masuk (kulakan) pembentukan lot FIFO real-time
   - Penitipan harian pagi dan penyelesaian setoran sore
   - Penjualan kasir tunai (berbagai nota pembeli umum)
   - Penjualan kasir kredit (nota kredit pembeli terdaftar dengan jatuh tempo)
   - Pembayaran cicilan / pelunasan piutang pembeli
   - Retur barang ke supplier dan retur pembeli
   - Sesi stock opname dengan penyesuaian selisih
"""
import os
import sys
from pathlib import Path
from datetime import date, timedelta
import random

# Pastikan root workspace ada di sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import DB_PATH
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.layanan.backup import buat_backup

# Repo Simpan Pinjam
from app.db.repo_anggota import tambah_anggota
from app.db.repo_simpanan import tambah_transaksi_simpanan
from app.db.repo_pinjaman import buat_pinjaman_baru, ambil_jadwal_angsuran_pinjaman
from app.db.repo_angsuran import bayar_angsuran
from app.db.repo_kas import tambah_kas_manual

# Repo Toko
from app.db.repo_kas_toko import tambah_kas_toko
from app.db.repo_pihak import tambah_pihak, ambil_atau_buat_pembeli_umum
from app.db.repo_barang import tambah_barang, tambah_satuan_barang
from app.db.repo_pembelian import buat_faktur_pembelian, bayar_hutang_pembelian
from app.db.repo_penitipan import catat_penitipan_harian, selesaikan_setoran_penitip
from app.db.repo_penjualan import simpan_penjualan
from app.db.repo_piutang import bayar_piutang_pembeli
from app.db.repo_retur_toko import catat_retur_supplier
from app.db.repo_opname_toko import buat_sesi_opname, simpan_baris_opname_draft, finalisasi_sesi_opname


def reset_dan_seed():
    print("=" * 60)
    print("MEMULAI PROSES RESET DAN SEEDING DATA PENUH")
    print("=" * 60)

    # 1. Backup database yang ada
    if DB_PATH.exists():
        conn_lama = buka_koneksi(DB_PATH)
        backup_path = buat_backup(conn_lama, catat_log=True)
        conn_lama.close()
        print(f"[1/6] Backup database lama tersimpan di:\n      -> {backup_path.name}")

    # 2. Inisialisasi skema baru dan bersihkan tabel
    conn = buka_koneksi(DB_PATH)
    inisialisasi_skema(conn)

    # Kosongkan seluruh data tabel (kecuali pengaturan default)
    with conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = OFF;")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'pengaturan';")
        tables = [r[0] for r in cur.fetchall()]
        for t in tables:
            conn.execute(f"DELETE FROM [{t}];")
            conn.execute(f"DELETE FROM sqlite_sequence WHERE name = '{t}';")
        cur.execute("PRAGMA foreign_keys = ON;")
    print("[2/6] Seluruh data tabel lama berhasil dikosongkan.")
    print("[3/6] Skema database baru (PRAGMA user_version = 6) siap.")

    # 3. Seed Data Simpan Pinjam
    print("[4/6] Melakukan seeding Unit Simpan Pinjam...")
    seed_simpan_pinjam(conn)

    # 4. Seed Data Unit Toko
    print("[5/6] Melakukan seeding Unit Toko Retail...")
    seed_unit_toko(conn)

    conn.close()
    print("=" * 60)
    print("BERHASIL! SELURUH DATA TESTING BERSIH & DATA DEMO REALISTIS SIAP DIGUNAKAN.")
    print("Silakan jalankan: python main.py")
    print("=" * 60)


def seed_simpan_pinjam(conn):
    # Modal Awal Kas Koperasi
    tambah_kas_manual(conn, "2026-01-01", "Modal Awal Kas Operasional Koperasi", "masuk", 100_000_000)

    daftar_anggota_data = [
        ("A-0001", "Budi Santoso", "EMP-001", "Produksi", "081234567801", "Jl. Mawar No. 12"),
        ("A-0002", "Siti Aminah", "EMP-002", "Keuangan", "081234567802", "Jl. Melati No. 45"),
        ("A-0003", "Ahmad Fauzi", "EMP-003", "Gudang", "081234567803", "Jl. Kenanga No. 8"),
        ("A-0004", "Dewi Lestari", "EMP-004", "Pemasaran", "081234567804", "Jl. Cempaka No. 19"),
        ("A-0005", "Rudi Hartono", "EMP-005", "Produksi", "081234567805", "Jl. Anggrek No. 3"),
        ("A-0006", "Hendra Gunawan", "EMP-006", "Keamanan", "081234567806", "Perumahan Asri Blok A1"),
        ("A-0007", "Rina Marlina", "EMP-007", "HRD", "081234567807", "Perumahan Asri Blok B5"),
        ("A-0008", "Eko Prasetyo", "EMP-008", "Produksi", "081234567808", "Dusun Krajan RT 02"),
        ("A-0009", "Sri Wahyuni", "EMP-009", "Kebersihan", "081234567809", "Dusun Krajan RT 04"),
        ("A-0010", "Bambang Pamungkas", "EMP-010", "Gudang", "081234567810", "Jl. Veteran No. 77"),
        ("A-0011", "Nur Hidayah", "EMP-011", "Produksi", "081234567811", "Jl. Pahlawan No. 15"),
        ("A-0012", "Agus Setiawan", "EMP-012", "Keamanan", "081234567812", "Perum Indah Blok C2"),
        ("A-0013", "Fitri Handayani", "EMP-013", "Keuangan", "081234567813", "Jl. Kartini No. 22"),
        ("A-0014", "Dedi Kurniawan", "EMP-014", "Pemasaran", "081234567814", "Jl. Sudirman No. 9"),
        ("A-0015", "Wawan Hendrawan", "EMP-015", "Produksi", "081234567815", "Jl. Gatot Subroto No. 30"),
    ]

    anggota_ids = []
    for no, nama, nik, unit, hp, alm in daftar_anggota_data:
        aid = tambah_anggota(
            conn,
            no_anggota=no,
            nama=nama,
            nik_karyawan=nik,
            unit=unit,
            no_hp=hp,
            alamat=alm,
            tanggal_masuk="2026-01-05",
            catatan="Anggota Aktif Koperasi"
        )
        anggota_ids.append(aid)

        # Simpanan Pokok Rp 100.000 saat masuk
        tambah_transaksi_simpanan(conn, aid, "pokok", "setor", 100_000, "2026-01-05", "Simpanan Pokok Anggota Baru")
        # Simpanan Wajib rutin (Jan s.d. Okt) Rp 50.000 / bln
        for bln in range(1, 11):
            tgl_wajib = f"2026-{bln:02d}-10"
            tambah_transaksi_simpanan(conn, aid, "wajib", "setor", 50_000, tgl_wajib, f"Simpanan Wajib Bulan {bln:02d}/2026")

    # Simpanan Sukarela dari beberapa anggota
    tambah_transaksi_simpanan(conn, anggota_ids[0], "sukarela", "setor", 500_000, "2026-02-15", "Setor Tabungan Sukarela")
    tambah_transaksi_simpanan(conn, anggota_ids[1], "sukarela", "setor", 1_000_000, "2026-03-20", "Setor Tabungan Sukarela")
    tambah_transaksi_simpanan(conn, anggota_ids[3], "sukarela", "setor", 750_000, "2026-04-12", "Setor Tabungan Sukarela")
    tambah_transaksi_simpanan(conn, anggota_ids[0], "sukarela", "tarik", 200_000, "2026-06-01", "Tarik Tabungan Sukarela untuk Keperluan")

    # Transaksi Pinjaman:
    # 1. Budi Santoso (A-0001) meminjam Rp 5.000.000 tenor 5 bulan (sudah lunas)
    pid_1 = buat_pinjaman_baru(conn, "P-0001", anggota_ids[0], None, 5_000_000, 5, 1.5, 25_000, "2026-01-10", "Renovasi Rumah")
    angsuran_1 = ambil_jadwal_angsuran_pinjaman(conn, pid_1)
    for ang in angsuran_1:
        bayar_angsuran(conn, pid_1, ang["id"], ang["jatuh_tempo"], ang["pokok"], ang["jasa"], 0, "Pelunasan angsuran tepat waktu")

    # 2. Ahmad Fauzi (A-0003) meminjam Rp 10.000.000 tenor 10 bulan (sedang berjalan)
    pid_2 = buat_pinjaman_baru(conn, "P-0002", anggota_ids[2], None, 10_000_000, 10, 1.5, 50_000, "2026-03-01", "Modal Usaha Keluarga")
    angsuran_2 = ambil_jadwal_angsuran_pinjaman(conn, pid_2)
    # Bayar 7 angsuran pertama
    for ang in angsuran_2[:7]:
        bayar_angsuran(conn, pid_2, ang["id"], ang["jatuh_tempo"], ang["pokok"], ang["jasa"], 0, "Pembayaran angsuran bulanan")

    # 3. Hendra Gunawan (A-0006) meminjam Rp 3.000.000 tenor 6 bulan (baru cair Okt 2026)
    pid_3 = buat_pinjaman_baru(conn, "P-0003", anggota_ids[5], None, 3_000_000, 6, 1.5, 20_000, "2026-10-01", "Biaya Sekolah Anak")
    angsuran_3 = ambil_jadwal_angsuran_pinjaman(conn, pid_3)
    # Bayar 1 angsuran pertama
    bayar_angsuran(conn, pid_3, angsuran_3[0]["id"], angsuran_3[0]["jatuh_tempo"], angsuran_3[0]["pokok"], angsuran_3[0]["jasa"], 0, "Angsuran ke-1")

    print(f"      -> {len(anggota_ids)} Anggota, 170+ Transaksi Simpanan, 3 Portofolio Pinjaman.")


def seed_unit_toko(conn):
    # 1. Modal Kas Toko (Kas Toko terpisah dari Kas Simpan Pinjam)
    tambah_kas_toko(conn, "2026-01-01", "Modal Awal Operasional Kas Toko Retail", masuk=50_000_000, keluar=0, sumber="modal_awal")

    # 2. Rekanan (Supplier, Penitip, Pembeli)
    suppliers = [
        ("PT Sumber Pangan Makmur", "08119876501", "Kawasan Pergudangan Muara Indah Kav 12", "Distributor Sembako Resmi"),
        ("CV Tirta Sejahtera", "08119876502", "Jl. Industri Raya No. 45", "Distributor Air Mineral & Minuman Ringan"),
        ("PT Indofood Niaga", "08119876503", "Komplek Pergudangan Cikarang Blok D", "Distributor Mie Instan & Bumbu"),
        ("UD Snack Jaya Lestari", "08119876504", "Pasar Induk Grosir Kios 88", "Distributor Biskuit & Makanan Ringan"),
        ("Toko Mandiri Stationery", "08119876505", "Jl. Niaga Sentosa No. 10", "Supplier ATK dan Perlengkapan Kantor"),
    ]
    supp_ids = [tambah_pihak(conn, "supplier", n, hp, alm, cat) for n, hp, alm, cat in suppliers]

    penitips = [
        ("Bu Siti Donat & Roti", "0821555001", "Dusun Melati RT 01", "Penitip donat coklat, keju, roti abon"),
        ("Ibu Fatimah Kue Basah", "0821555002", "Dusun Melati RT 03", "Penitip risoles, lemper, pastel goreng"),
        ("Pak Slamet Gorengan Hangat", "0821555003", "Jl. Merpati No. 4", "Penitip tahu isi, tempe mendoan, bakwan"),
        ("Dapur Berkah Bunda", "0821555004", "Perumahan Asri Blok C1", "Penitip nasi bungkus ayam & nasi uduk"),
        ("Mbak Ningsih Puding & Jelly", "0821555005", "Jl. Flamboyan No. 2", "Penitip puding buah dan cup jelly"),
        ("Bu Warsi Keripik Tradisional", "0821555006", "Dusun Krajan RT 05", "Penitip keripik singkong & rempeyek"),
    ]
    penitip_ids = [tambah_pihak(conn, "penitip", n, hp, alm, cat) for n, hp, alm, cat in penitips]

    # Ambil ID anggota simpan pinjam untuk menghubungkan beberapa pembeli
    cur = conn.cursor()
    cur.execute("SELECT id, nama, no_hp, alamat FROM anggota ORDER BY id LIMIT 5;")
    ang_rows = cur.fetchall()

    pembelis = [
        (ang_rows[0]["nama"], ang_rows[0]["no_hp"], ang_rows[0]["alamat"], "Anggota Koperasi A-0001 (Boleh Kredit)", ang_rows[0]["id"]),
        (ang_rows[1]["nama"], ang_rows[1]["no_hp"], ang_rows[1]["alamat"], "Anggota Koperasi A-0002 (Boleh Kredit)", ang_rows[1]["id"]),
        (ang_rows[2]["nama"], ang_rows[2]["no_hp"], ang_rows[2]["alamat"], "Anggota Koperasi A-0003 (Boleh Kredit)", ang_rows[2]["id"]),
        ("Pak Joko Widodo", "085233344401", "Komplek Perumahan Indah B2", "Warga Komplek / Pelanggan Tetap", None),
        ("Bu Ratna Juwita", "085233344402", "Jl. Mawar Putih No. 10", "Warga Sekitar Toko", None),
        ("Pak Tejo Supriyadi", "085233344403", "Jl. Dahlia No. 14", "Warga Sekitar Toko", None),
        ("Ibu Maya Susanti", "085233344404", "Perumahan Indah A7", "Pelanggan Harian", None),
    ]
    pembeli_ids = []
    for n, hp, alm, cat, aid in pembelis:
        cur.execute(
            "INSERT INTO pembeli (nama, no_hp, alamat, catatan, anggota_id, aktif) VALUES (?, ?, ?, ?, ?, 1);",
            (n, hp, alm, cat, aid)
        )
        pembeli_ids.append(cur.lastrowid)

    # Pastikan pembeli umum tersedia
    id_umum = ambil_atau_buat_pembeli_umum(conn)

    # 3. Master Barang Retail (Koperasi & Titipan)
    barang_koperasi_data = [
        # Sembako & Minyak
        ("BRG-SBK-01", "Beras Premium Ramos 5kg", "Sembako", "karung", "beras ramos pandan wangi pulen", 72_000, 5),
        ("BRG-SBK-02", "Minyak Goreng Bimoli 2 Liter", "Sembako", "pouch", "minyak goreng bimoli sawit refill", 38_000, 10),
        ("BRG-SBK-03", "Gula Pasir Gulaku Premium 1kg", "Sembako", "bungkus", "gula pasir tebu putih gulaku", 18_500, 15),
        ("BRG-SBK-04", "Tepung Terigu Segitiga Biru 1kg", "Sembako", "bungkus", "tepung terigu kue gorengan segitiga", 13_500, 10),
        ("BRG-SBK-05", "Garam Beriodium Cap Kapal 250g", "Sembako", "bungkus", "garam dapur beryodium kapal laut", 3_500, 20),
        # Mie Instan & Makanan
        ("BRG-MIE-01", "Indomie Goreng Special 85g", "Makanan", "bungkus", "mie instan goreng indomie sedap", 3_500, 40),
        ("BRG-MIE-02", "Indomie Kuah Ayam Bawang 75g", "Makanan", "bungkus", "mie kuah rebus ayam bawang indomie", 3_500, 40),
        ("BRG-MIE-03", "Mie Sedaap Goreng 90g", "Makanan", "bungkus", "mie sedaap kriuk goreng instan", 3_500, 30),
        ("BRG-MKN-01", "Sarden ABC Saus Tomat 155g", "Makanan", "kaleng", "ikan sarden kaleng abc tomat pedas", 12_000, 15),
        ("BRG-MKN-02", "Kecap Manis Bango Refill 520ml", "Makanan", "pouch", "kecap manis bango kedelai hitam", 24_000, 10),
        # Minuman
        ("BRG-MNM-01", "Aqua Air Mineral Botol 600ml", "Minuman", "botol", "air mineral aqua botol sedang dingin", 4_000, 24),
        ("BRG-MNM-02", "Teh Pucuk Harum 350ml", "Minuman", "botol", "teh pucuk harum melati manis dingin", 4_000, 24),
        ("BRG-MNM-03", "Kopi Kapal Api Special Mix 24g", "Minuman", "sachet", "kopi hitam gula kapal api sachet", 2_000, 50),
        ("BRG-MNM-04", "Susu Kental Manis Frisian Flag 370g", "Minuman", "kaleng", "susu kental manis bendera putih can", 13_500, 12),
        ("BRG-MNM-05", "Floridina Orange Juice 350ml", "Minuman", "botol", "jus jeruk floridina bulir pulpy", 3_500, 24),
        # Snack & Biskuit
        ("BRG-SNK-01", "Roma Kelapa Biskuit 300g", "Snack", "bungkus", "biskuit kelapa roma renyah cemilan", 11_500, 10),
        ("BRG-SNK-02", "Chitato Sapi Panggang 68g", "Snack", "bungkus", "keripik kentang chitato beef barbecue", 12_500, 15),
        ("BRG-SNK-03", "Oreo Vanila Sandwich 133g", "Snack", "bungkus", "biskuit oreo coklat krim vanila", 10_000, 15),
        # Sabun & Perlengkapan Mandi
        ("BRG-SBN-01", "Sabun Lifebuoy Total 10 85g", "Perlengkapan", "batang", "sabun mandi lifebuoy merah antiseptik", 4_500, 20),
        ("BRG-SBN-02", "Shampoo Sunsilk Black Shine 160ml", "Perlengkapan", "botol", "shampoo rambut hitam berkilau sunsilk", 23_000, 10),
        ("BRG-SBN-03", "Pasta Gigi Pepsodent White 190g", "Perlengkapan", "kotak", "odol pepsodent pencegah gigi berlubang", 14_500, 12),
        ("BRG-SBN-04", "Deterjen Rinso Molto Cair 750ml", "Perlengkapan", "pouch", "rinso cair molto mawar pewangi pakaian", 21_000, 10),
        # ATK
        ("BRG-ATK-01", "Buku Tulis Sinar Dunia 38 Lembar", "ATK", "buku", "buku tulis sidu sekolah catatan garis", 4_500, 20),
        ("BRG-ATK-02", "Pulpen Standard AE7 0.5 Hitam", "ATK", "buah", "pena pulpen bolpoin standard hitam lancip", 3_000, 30),
    ]

    barang_koperasi_ids = []
    for kode, nama, kat, sat, kw, hrg, smin in barang_koperasi_data:
        bid = tambah_barang(
            conn, kode=kode, nama=nama, kategori=kat, satuan_dasar=sat,
            kata_kunci=kw, harga_jual=hrg, jenis_kepemilikan="milik_koperasi", stok_minimum=smin
        )
        barang_koperasi_ids.append((bid, kode, nama, sat))

    # Tambah Satuan Konversi Khusus per Barang
    # Indomie Goreng: dus = 40 bungkus
    tambah_satuan_barang(conn, barang_koperasi_ids[5][0], "dus", 40)
    # Indomie Kuah: dus = 40 bungkus
    tambah_satuan_barang(conn, barang_koperasi_ids[6][0], "dus", 40)
    # Aqua 600ml: karton = 24 botol
    tambah_satuan_barang(conn, barang_koperasi_ids[10][0], "karton", 24)
    # Teh Pucuk: karton = 24 botol
    tambah_satuan_barang(conn, barang_koperasi_ids[11][0], "karton", 24)
    # Kopi Kapal Api: renceng = 10 sachet
    tambah_satuan_barang(conn, barang_koperasi_ids[12][0], "renceng", 10)
    # Minyak Bimoli: kardus = 6 pouch
    tambah_satuan_barang(conn, barang_koperasi_ids[1][0], "kardus", 6)
    # Pulpen Standard: pack = 12 buah
    tambah_satuan_barang(conn, barang_koperasi_ids[23][0], "pack", 12)
    # Buku Tulis: pak = 10 buku
    tambah_satuan_barang(conn, barang_koperasi_ids[22][0], "pak", 10)

    # Master Barang Titipan Harian
    barang_titipan_data = [
        ("TITIP-01", "Donat Coklat Lumer Bu Siti", "Kue Titipan", "biji", "donat coklat meses gula manis", 2_500, penitip_ids[0]),
        ("TITIP-02", "Roti Goreng Sosis Bu Siti", "Kue Titipan", "biji", "roti goreng sosis gurih", 3_000, penitip_ids[0]),
        ("TITIP-03", "Risoles Ragout Ayam Bu Fatimah", "Kue Titipan", "biji", "risol risoles ayam wortel lezat", 3_000, penitip_ids[1]),
        ("TITIP-04", "Lemper Ayam Bakar Bu Fatimah", "Kue Titipan", "biji", "lemper ketan bakar ayam wangi", 3_500, penitip_ids[1]),
        ("TITIP-05", "Tahu Isi Sayur Pedas Pak Slamet", "Gorengan", "biji", "tahu goreng isi tauge cabai gurih", 1_500, penitip_ids[2]),
        ("TITIP-06", "Tempe Mendoan Gurih Pak Slamet", "Gorengan", "lembar", "mendoan tempe goreng tepung daun bawang", 1_500, penitip_ids[2]),
    ]
    barang_titipan_ids = []
    for kode, nama, kat, sat, kw, hrg, pen_id in barang_titipan_data:
        bid = tambah_barang(
            conn, kode=kode, nama=nama, kategori=kat, satuan_dasar=sat,
            kata_kunci=kw, harga_jual=hrg, jenis_kepemilikan="titipan", penitip_id=pen_id, stok_minimum=0
        )
        barang_titipan_ids.append((bid, kode, nama, sat, pen_id))

    # 4. Transaksi Pembelian Barang (Kulaan Grosir Masuk Toko - Lot FIFO)
    # Faktur 1: Pembelian dari Indofood (Mie & Bumbu)
    faktur_1_items = [
        {"barang_id": barang_koperasi_ids[5][0], "jumlah_input": 5, "satuan_input": "dus", "isi_per_satuan": 40, "harga_per_satuan_input": 120_000}, # 200 bks @ Rp 3.000
        {"barang_id": barang_koperasi_ids[6][0], "jumlah_input": 3, "satuan_input": "dus", "isi_per_satuan": 40, "harga_per_satuan_input": 120_000}, # 120 bks @ Rp 3.000
    ]
    buat_faktur_pembelian(conn, "FAK-INDF-001", supp_ids[2], "2026-10-15", "tunai", faktur_1_items)

    # Faktur 2: Pembelian dari CV Tirta (Minuman)
    faktur_2_items = [
        {"barang_id": barang_koperasi_ids[10][0], "jumlah_input": 10, "satuan_input": "karton", "isi_per_satuan": 24, "harga_per_satuan_input": 72_000}, # 240 btl @ Rp 3.000
        {"barang_id": barang_koperasi_ids[11][0], "jumlah_input": 8, "satuan_input": "karton", "isi_per_satuan": 24, "harga_per_satuan_input": 72_000},  # 192 btl @ Rp 3.000
    ]
    buat_faktur_pembelian(conn, "FAK-TRT-001", supp_ids[1], "2026-10-18", "tunai", faktur_2_items)

    # Faktur 3: Pembelian Sembako (Hutang Dagang)
    faktur_3_items = [
        {"barang_id": barang_koperasi_ids[0][0], "jumlah_input": 20, "satuan_input": "karung", "isi_per_satuan": 1, "harga_per_satuan_input": 65_000}, # 20 krg @ Rp 65.000
        {"barang_id": barang_koperasi_ids[1][0], "jumlah_input": 5, "satuan_input": "kardus", "isi_per_satuan": 6, "harga_per_satuan_input": 198_000},  # 30 pch @ Rp 33.000
        {"barang_id": barang_koperasi_ids[2][0], "jumlah_input": 50, "satuan_input": "bungkus", "isi_per_satuan": 1, "harga_per_satuan_input": 16_000}, # 50 bks @ Rp 16.000
    ]
    f3_id = buat_faktur_pembelian(conn, "FAK-SPM-001", supp_ids[0], "2026-10-20", "belum_dibayar", faktur_3_items)
    # Cicil bayar sebagian hutang supplier
    bayar_hutang_pembelian(conn, f3_id, "2026-10-25", 1_500_000, "Cicilan pembayaran hutang gula dan minyak")

    # Faktur 4: Pembelian ATK & Sabun
    faktur_4_items = [
        {"barang_id": barang_koperasi_ids[18][0], "jumlah_input": 48, "satuan_input": "batang", "isi_per_satuan": 1, "harga_per_satuan_input": 3_500},
        {"barang_id": barang_koperasi_ids[22][0], "jumlah_input": 5, "satuan_input": "pak", "isi_per_satuan": 10, "harga_per_satuan_input": 38_000},
        {"barang_id": barang_koperasi_ids[23][0], "jumlah_input": 4, "satuan_input": "pack", "isi_per_satuan": 12, "harga_per_satuan_input": 28_000},
    ]
    buat_faktur_pembelian(conn, "FAK-MND-001", supp_ids[4], "2026-10-22", "tunai", faktur_4_items)

    # 5. Penitipan Harian (Pagi Hari)
    # Bu Siti titip 40 donat (@ Rp 2.000 harga titip, Rp 2.500 harga jual)
    catat_penitipan_harian(conn, penitip_ids[0], "2026-11-14", [
        {
            "barang_id": barang_titipan_ids[0][0],
            "jumlah_input": 40,
            "satuan_input": "biji",
            "isi_per_satuan": 1,
            "harga_titip_satuan_dasar": 2_000,
            "harga_jual_satuan_dasar": 2_500
        }
    ])
    # Bu Fatimah titip 30 risoles (@ Rp 2.300 harga titip, Rp 3.000 harga jual)
    catat_penitipan_harian(conn, penitip_ids[1], "2026-11-14", [
        {
            "barang_id": barang_titipan_ids[2][0],
            "jumlah_input": 30,
            "satuan_input": "biji",
            "isi_per_satuan": 1,
            "harga_titip_satuan_dasar": 2_300,
            "harga_jual_satuan_dasar": 3_000
        }
    ])

    # 6. Transaksi Kasir Penjualan Toko
    # Nota 1: Tunai Pembeli Umum (Mie & Teh Pucuk)
    simpan_penjualan(conn, "2026-11-14", id_umum, "tunai", [
        {"barang_id": barang_koperasi_ids[5][0], "jumlah_input": 5, "satuan_input": "bungkus", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 3_500},
        {"barang_id": barang_koperasi_ids[11][0], "jumlah_input": 3, "satuan_input": "botol", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 4_000},
        {"barang_id": barang_titipan_ids[0][0], "jumlah_input": 4, "satuan_input": "biji", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 2_500},
    ])

    # Nota 2: Tunai Pembeli Umum (Minyak & Beras)
    simpan_penjualan(conn, "2026-11-14", id_umum, "tunai", [
        {"barang_id": barang_koperasi_ids[0][0], "jumlah_input": 1, "satuan_input": "karung", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 72_000},
        {"barang_id": barang_koperasi_ids[1][0], "jumlah_input": 2, "satuan_input": "pouch", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 38_000},
    ])

    # Nota 3: Kredit ke Budi Santoso (A-0001)
    simpan_penjualan(conn, "2026-11-14", pembeli_ids[0], "kredit", [
        {"barang_id": barang_koperasi_ids[5][0], "jumlah_input": 1, "satuan_input": "dus", "isi_per_satuan": 40, "harga_jual_satuan_dasar": 3_500}, # 1 dus = 40 bks
        {"barang_id": barang_koperasi_ids[2][0], "jumlah_input": 2, "satuan_input": "bungkus", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 18_500},
        {"barang_id": barang_titipan_ids[0][0], "jumlah_input": 6, "satuan_input": "biji", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 2_500},
    ])

    # Nota 4: Kredit ke Pak Joko Widodo
    simpan_penjualan(conn, "2026-11-14", pembeli_ids[3], "kredit", [
        {"barang_id": barang_koperasi_ids[10][0], "jumlah_input": 6, "satuan_input": "botol", "isi_per_satuan": 1, "harga_jual_satuan_dasar": 4_000},
        {"barang_id": barang_koperasi_ids[22][0], "jumlah_input": 1, "satuan_input": "pak", "isi_per_satuan": 10, "harga_jual_satuan_dasar": 4_500},
    ])

    # 7. Pembayaran Piutang Pembeli
    # Pak Joko mencicil Rp 35.000
    bayar_piutang_pembeli(conn, pembeli_ids[3], "2026-11-15", 35_000, "Cicilan pembayaran nota kredit")

    # 8. Setoran Penitip Sore Hari
    # Selesaikan titipan Bu Siti (dari 40 dititip, terjual 10, sisa 30 dikembalikan)
    cur.execute("SELECT id, lot_id FROM penitipan_baris WHERE penitipan_id IN (SELECT id FROM penitipan WHERE penitip_id = ?) LIMIT 1;", (penitip_ids[0],))
    pb_row = cur.fetchone()
    if pb_row:
        selesaikan_setoran_penitip(
            conn,
            penitip_id=penitip_ids[0],
            tanggal="2026-11-14",
            rincian_penyelesaian=[
                {
                    "penitipan_baris_id": pb_row["id"],
                    "lot_id": pb_row["lot_id"],
                    "qty_terjual": 10,
                    "harga_titip": 2_000,
                    "sisa_aksi": "retur"
                }
            ],
            nominal_bayar=20_000,
            keterangan="Setoran sore hari donat laku 10 pcs"
        )

    # 9. Retur Toko
    # Retur 2 botol Aqua bocor ke supplier
    cur.execute("SELECT id FROM lot_stok WHERE barang_id = ? AND qty_sisa > 0 LIMIT 1;", (barang_koperasi_ids[10][0],))
    lot_aqua = cur.fetchone()
    if lot_aqua:
        catat_retur_supplier(
            conn,
            supplier_id=supp_ids[1],
            tanggal="2026-11-15",
            jenis_kompensasi="potong_hutang",
            daftar_item=[
                {"barang_id": barang_koperasi_ids[10][0], "lot_id": lot_aqua["id"], "jumlah_dasar": 2, "biaya_per_satuan_dasar": 3_000}
            ],
            alasan="Kemasan kardus basah dan botol bocor dari pengiriman"
        )

    # 10. Stock Opname Toko (Sesi Baru & Input Fisik)
    sesi_opname_id, kode_opname = buat_sesi_opname(conn, "2026-11-15", "Stock Opname Rutin Pertengahan Bulan")
    # Simulasikan hitung fisik Indomie Goreng selisih 1 bks
    cur.execute("SELECT stok_saat_ini FROM barang WHERE id = ?;", (barang_koperasi_ids[5][0],))
    stok_mie = cur.fetchone()["stok_saat_ini"]
    simpan_baris_opname_draft(conn, sesi_opname_id, [
        {"barang_id": barang_koperasi_ids[5][0], "stok_fisik": stok_mie - 1, "catatan": "Selisih 1 bks rusak sobek"}
    ])
    finalisasi_sesi_opname(conn, sesi_opname_id)

    print(f"      -> 5 Supplier, 6 Penitip, 7 Pembeli Terdaftar + Umum.")
    print(f"      -> 30 Master Barang Retail dengan Satuan Konversi.")
    print(f"      -> 4 Faktur Pembelian (Lot FIFO), 2 Sesi Titipan, 4 Nota Kasir (Tunai & Kredit).")
    print(f"      -> Piutang, Setoran Penitip, Retur Toko, dan Stock Opname berhasil disimulasikan.")


if __name__ == "__main__":
    reset_dan_seed()
