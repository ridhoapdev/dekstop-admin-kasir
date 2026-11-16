"""
app/db/skema_toko.py — Skema DDL dan Migrasi untuk Unit Toko (Modul 13 & 14).
Mencakup:
- Master: supplier, penitip, pembeli, barang, satuan_barang
- Kas Toko Mandiri: kas_toko_transaksi
- Pembelian: pembelian_faktur, pembelian_detail, pembayaran_hutang_supplier
- Stok: lot_stok, mutasi_stok
- Penitipan Harian: penitipan, penitipan_baris, pembayaran_penitip, penyelesaian_titipan_baris
- Penjualan & Piutang: penjualan, penjualan_baris, penjualan_lot, pembayaran_piutang, alokasi_piutang
- View Transaksi Efektif: v_mutasi_stok_efektif, v_pembelian_faktur_efektif, v_kas_toko_efektif,
  v_penjualan_efektif, v_penitipan_efektif, v_pembayaran_piutang_efektif, v_pembayaran_penitip_efektif
"""

DDL_SKEMA_TOKO = """
-- 1. Supplier
CREATE TABLE IF NOT EXISTS supplier (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL,
  no_hp TEXT,
  alamat TEXT,
  catatan TEXT,
  aktif INTEGER NOT NULL DEFAULT 1,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_supplier_nama ON supplier(nama);

-- 2. Penitip
CREATE TABLE IF NOT EXISTS penitip (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL,
  no_hp TEXT,
  alamat TEXT,
  catatan TEXT,
  aktif INTEGER NOT NULL DEFAULT 1,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_penitip_nama ON penitip(nama);

-- 3. Pembeli (Langganan Toko & Anggota Koperasi)
CREATE TABLE IF NOT EXISTS pembeli (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL,
  no_hp TEXT,
  alamat TEXT,
  catatan TEXT,
  anggota_id INTEGER REFERENCES anggota(id),
  aktif INTEGER NOT NULL DEFAULT 1,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_pembeli_nama ON pembeli(nama);
CREATE INDEX IF NOT EXISTS idx_pembeli_anggota ON pembeli(anggota_id);

-- 4. Barang
CREATE TABLE IF NOT EXISTS barang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kode TEXT NOT NULL UNIQUE,
  nama TEXT NOT NULL,
  kategori TEXT,
  satuan_dasar TEXT NOT NULL,               -- pcs, g, ml, butir, dll.
  kata_kunci TEXT,                          -- alias pencarian dipisahkan koma atau spasi
  harga_jual INTEGER NOT NULL DEFAULT 0,    -- harga jual default dalam rupiah int
  jenis_kepemilikan TEXT NOT NULL DEFAULT 'milik_koperasi' CHECK (jenis_kepemilikan IN ('milik_koperasi', 'titipan')),
  penitip_id INTEGER REFERENCES penitip(id),
  stok_minimum INTEGER NOT NULL DEFAULT 0,  -- dalam satuan dasar
  stok_saat_ini INTEGER NOT NULL DEFAULT 0,  -- cache stok dalam satuan dasar
  aktif INTEGER NOT NULL DEFAULT 1,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_barang_nama ON barang(nama);
CREATE INDEX IF NOT EXISTS idx_barang_kode ON barang(kode);

-- 5. Satuan Barang (Konversi Melekat pada Barang)
-- DILARANG membuat konversi global. 1 dus per Barang A bisa 20 pcs, per Barang B bisa 15 pcs.
CREATE TABLE IF NOT EXISTS satuan_barang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  nama_satuan TEXT NOT NULL,
  isi_dalam_satuan_dasar INTEGER NOT NULL CHECK (isi_dalam_satuan_dasar > 0),
  terkunci INTEGER NOT NULL DEFAULT 0,      -- 1 jika sudah dipakai dalam transaksi
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (barang_id, nama_satuan)
);
CREATE INDEX IF NOT EXISTS idx_satuan_barang ON satuan_barang(barang_id);

-- 6. Kas Toko Transaksi (Kas Toko TERPISAH dari kas simpan pinjam)
CREATE TABLE IF NOT EXISTS kas_toko_transaksi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tanggal TEXT NOT NULL,
  keterangan TEXT NOT NULL,
  masuk INTEGER NOT NULL DEFAULT 0,
  keluar INTEGER NOT NULL DEFAULT 0,
  sumber TEXT NOT NULL CHECK (sumber IN ('modal_awal', 'pembelian', 'bayar_hutang', 'penjualan', 'bayar_piutang', 'bayar_penitip', 'manual')),
  ref_tabel TEXT,                          -- 'penjualan', 'pembayaran_piutang', 'pembayaran_penitip', dll.
  ref_id INTEGER,
  membalik_id INTEGER REFERENCES kas_toko_transaksi(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  CHECK ((masuk > 0 AND keluar = 0) OR (keluar > 0 AND masuk = 0))
);
CREATE INDEX IF NOT EXISTS idx_kas_toko_tanggal ON kas_toko_transaksi(tanggal);

-- 7. Pembelian Faktur
CREATE TABLE IF NOT EXISTS pembelian_faktur (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_faktur TEXT NOT NULL UNIQUE,
  supplier_id INTEGER NOT NULL REFERENCES supplier(id),
  tanggal TEXT NOT NULL,
  status_bayar TEXT NOT NULL CHECK (status_bayar IN ('tunai', 'belum_dibayar')),
  total_biaya INTEGER NOT NULL DEFAULT 0,
  keterangan TEXT,
  membalik_id INTEGER REFERENCES pembelian_faktur(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_faktur_tanggal ON pembelian_faktur(tanggal);
CREATE INDEX IF NOT EXISTS idx_faktur_supplier ON pembelian_faktur(supplier_id);

-- 8. Pembelian Detail (Snapshot Konversi)
CREATE TABLE IF NOT EXISTS pembelian_detail (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  faktur_id INTEGER NOT NULL REFERENCES pembelian_faktur(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  jumlah_input INTEGER NOT NULL CHECK (jumlah_input > 0),
  satuan_input TEXT NOT NULL,
  isi_per_satuan INTEGER NOT NULL CHECK (isi_per_satuan > 0), -- snapshot konversi
  jumlah_dasar INTEGER NOT NULL CHECK (jumlah_dasar > 0),     -- jumlah_input * isi_per_satuan
  harga_per_satuan_input INTEGER NOT NULL CHECK (harga_per_satuan_input >= 0),
  total_biaya INTEGER NOT NULL CHECK (total_biaya >= 0)       -- snapshot total baris
);
CREATE INDEX IF NOT EXISTS idx_detail_faktur ON pembelian_detail(faktur_id);
CREATE INDEX IF NOT EXISTS idx_detail_barang ON pembelian_detail(barang_id);

-- 9. Pembayaran Hutang Supplier
CREATE TABLE IF NOT EXISTS pembayaran_hutang_supplier (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  faktur_id INTEGER NOT NULL REFERENCES pembelian_faktur(id),
  tanggal TEXT NOT NULL,
  jumlah_bayar INTEGER NOT NULL CHECK (jumlah_bayar > 0),
  keterangan TEXT,
  membalik_id INTEGER REFERENCES pembayaran_hutang_supplier(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_bayar_hutang_faktur ON pembayaran_hutang_supplier(faktur_id);

-- 10. Lot Stok FIFO
CREATE TABLE IF NOT EXISTS lot_stok (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  asal TEXT NOT NULL CHECK (asal IN ('pembelian', 'titipan', 'penyesuaian', 'koreksi')),
  ref_tabel TEXT,                          -- 'pembelian_detail', 'penitipan_baris', dll.
  ref_id INTEGER,
  tanggal_masuk TEXT NOT NULL,
  supplier_id INTEGER REFERENCES supplier(id),
  penitip_id INTEGER REFERENCES penitip(id),
  qty_awal INTEGER NOT NULL CHECK (qty_awal >= 0),
  qty_sisa INTEGER NOT NULL CHECK (qty_sisa >= 0),
  total_biaya_awal INTEGER NOT NULL CHECK (total_biaya_awal >= 0),
  biaya_sisa INTEGER NOT NULL CHECK (biaya_sisa >= 0),
  harga_jual_satuan_dasar INTEGER NOT NULL DEFAULT 0,  -- harga jual khusus untuk lot titipan
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_lot_barang ON lot_stok(barang_id, tanggal_masuk, id);

-- 11. Mutasi Stok (Buku Mutasi Append-Only)
CREATE TABLE IF NOT EXISTS mutasi_stok (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  lot_id INTEGER REFERENCES lot_stok(id),
  tanggal TEXT NOT NULL,
  jenis TEXT NOT NULL CHECK (jenis IN (
    'masuk', 'keluar_jual', 'retur_supplier', 'retur_penitip',
    'rusak', 'hilang', 'kedaluwarsa', 'penyesuaian_opname', 'koreksi'
  )),
  qty INTEGER NOT NULL,                     -- (+/-) dalam satuan dasar
  biaya INTEGER NOT NULL DEFAULT 0,        -- int rupiah proporsional
  ref_tabel TEXT,
  ref_id INTEGER,
  membalik_id INTEGER REFERENCES mutasi_stok(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_mutasi_barang ON mutasi_stok(barang_id, tanggal);
CREATE INDEX IF NOT EXISTS idx_mutasi_lot ON mutasi_stok(lot_id);

-- 12. Penitipan Harian
CREATE TABLE IF NOT EXISTS penitipan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penitip_id INTEGER NOT NULL REFERENCES penitip(id),
  tanggal TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif', 'selesai', 'dibatalkan')),
  catatan TEXT,
  membalik_id INTEGER REFERENCES penitipan(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_penitipan_penitip ON penitipan(penitip_id, tanggal);

-- 13. Penitipan Baris
CREATE TABLE IF NOT EXISTS penitipan_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penitipan_id INTEGER NOT NULL REFERENCES penitipan(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  jumlah_input INTEGER NOT NULL CHECK (jumlah_input > 0),
  satuan_input TEXT NOT NULL,
  isi_per_satuan INTEGER NOT NULL CHECK (isi_per_satuan > 0),
  jumlah_dasar INTEGER NOT NULL CHECK (jumlah_dasar > 0),
  harga_titip_satuan_dasar INTEGER NOT NULL CHECK (harga_titip_satuan_dasar >= 0),
  harga_jual_satuan_dasar INTEGER NOT NULL CHECK (harga_jual_satuan_dasar >= 0),
  lot_id INTEGER REFERENCES lot_stok(id),
  selesai INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_penitipan_baris_penitipan ON penitipan_baris(penitipan_id);
CREATE INDEX IF NOT EXISTS idx_penitipan_baris_barang ON penitipan_baris(barang_id);

-- 14. Pembayaran Penitip (Penyelesaian Harian Sore)
CREATE TABLE IF NOT EXISTS pembayaran_penitip (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penitip_id INTEGER NOT NULL REFERENCES penitip(id),
  tanggal TEXT NOT NULL,
  total_laku_terbayar INTEGER NOT NULL DEFAULT 0,
  keterangan TEXT,
  membalik_id INTEGER REFERENCES pembayaran_penitip(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_bayar_penitip_tgl ON pembayaran_penitip(penitip_id, tanggal);

-- 15. Penyelesaian Titipan Baris (Audit Item yang Diselesaikan Sore Hari)
CREATE TABLE IF NOT EXISTS penyelesaian_titipan_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pembayaran_penitip_id INTEGER NOT NULL REFERENCES pembayaran_penitip(id),
  penitipan_baris_id INTEGER NOT NULL REFERENCES penitipan_baris(id),
  lot_id INTEGER NOT NULL REFERENCES lot_stok(id),
  qty_terjual INTEGER NOT NULL DEFAULT 0,
  harga_titip INTEGER NOT NULL DEFAULT 0,
  subtotal_bayar INTEGER NOT NULL DEFAULT 0,
  qty_sisa_retur INTEGER NOT NULL DEFAULT 0,
  qty_sisa_tinggal INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 16. Penjualan (Kasir Nota)
CREATE TABLE IF NOT EXISTS penjualan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_nota TEXT NOT NULL UNIQUE,
  tanggal TEXT NOT NULL,
  pembeli_id INTEGER NOT NULL REFERENCES pembeli(id),
  nama_pembeli_nota TEXT,                  -- nama opsional pembeli umum di nota
  metode_bayar TEXT NOT NULL CHECK (metode_bayar IN ('tunai', 'kredit')),
  total INTEGER NOT NULL DEFAULT 0,
  jatuh_tempo TEXT,                        -- wajib jika metode_bayar == 'kredit'
  status TEXT NOT NULL DEFAULT 'selesai' CHECK (status IN ('selesai', 'dibatalkan')),
  keterangan TEXT,
  membalik_id INTEGER REFERENCES penjualan(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_penjualan_tgl ON penjualan(tanggal);
CREATE INDEX IF NOT EXISTS idx_penjualan_pembeli ON penjualan(pembeli_id);

-- 17. Penjualan Baris
CREATE TABLE IF NOT EXISTS penjualan_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penjualan_id INTEGER NOT NULL REFERENCES penjualan(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  jumlah_input INTEGER NOT NULL CHECK (jumlah_input > 0),
  satuan_input TEXT NOT NULL,
  isi_per_satuan INTEGER NOT NULL CHECK (isi_per_satuan > 0),
  jumlah_dasar INTEGER NOT NULL CHECK (jumlah_dasar > 0),
  harga_jual_satuan_dasar INTEGER NOT NULL CHECK (harga_jual_satuan_dasar >= 0),
  total_baris INTEGER NOT NULL CHECK (total_baris >= 0),
  hpp_total INTEGER NOT NULL DEFAULT 0,
  laba INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_penjualan_baris_penj ON penjualan_baris(penjualan_id);

-- 18. Penjualan Lot (Pencatat Lot FIFO yang Terpakai untuk Presisi Pembalik & HPP)
CREATE TABLE IF NOT EXISTS penjualan_lot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penjualan_baris_id INTEGER NOT NULL REFERENCES penjualan_baris(id),
  lot_id INTEGER REFERENCES lot_stok(id),
  qty INTEGER NOT NULL CHECK (qty > 0),
  biaya INTEGER NOT NULL DEFAULT 0,
  penitip_id INTEGER REFERENCES penitip(id) -- jika lot titipan, catat penitip_id untuk menghitung hutang penitip
);
CREATE INDEX IF NOT EXISTS idx_penjualan_lot_baris ON penjualan_lot(penjualan_baris_id);
CREATE INDEX IF NOT EXISTS idx_penjualan_lot_lot ON penjualan_lot(lot_id);

-- 19. Pembayaran Piutang
CREATE TABLE IF NOT EXISTS pembayaran_piutang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pembeli_id INTEGER NOT NULL REFERENCES pembeli(id),
  tanggal TEXT NOT NULL,
  jumlah INTEGER NOT NULL CHECK (jumlah > 0),
  keterangan TEXT,
  membalik_id INTEGER REFERENCES pembayaran_piutang(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_bayar_piutang_pembeli ON pembayaran_piutang(pembeli_id);

-- 20. Alokasi Piutang (Alokasi ke Nota Kredit Tertua)
CREATE TABLE IF NOT EXISTS alokasi_piutang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pembayaran_piutang_id INTEGER NOT NULL REFERENCES pembayaran_piutang(id),
  penjualan_id INTEGER NOT NULL REFERENCES penjualan(id),
  jumlah INTEGER NOT NULL CHECK (jumlah > 0),
  membalik_id INTEGER REFERENCES alokasi_piutang(id),
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_alokasi_penjualan ON alokasi_piutang(penjualan_id);

-- 21. View Transaksi Efektif Toko
CREATE VIEW IF NOT EXISTS v_mutasi_stok_efektif AS
SELECT m.*,
       CASE 
         WHEN m.id IN (SELECT membalik_id FROM mutasi_stok WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN m.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM mutasi_stok m;

CREATE VIEW IF NOT EXISTS v_pembelian_faktur_efektif AS
SELECT pf.*,
       CASE 
         WHEN pf.id IN (SELECT membalik_id FROM pembelian_faktur WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pf.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembelian_faktur pf;

CREATE VIEW IF NOT EXISTS v_kas_toko_efektif AS
SELECT k.*,
       CASE 
         WHEN k.id IN (SELECT membalik_id FROM kas_toko_transaksi WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN k.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM kas_toko_transaksi k;

CREATE VIEW IF NOT EXISTS v_penjualan_efektif AS
SELECT pj.*,
       CASE 
         WHEN pj.id IN (SELECT membalik_id FROM penjualan WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pj.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM penjualan pj;

CREATE VIEW IF NOT EXISTS v_penitipan_efektif AS
SELECT pt.*,
       CASE 
         WHEN pt.id IN (SELECT membalik_id FROM penitipan WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pt.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM penitipan pt;

CREATE VIEW IF NOT EXISTS v_pembayaran_piutang_efektif AS
SELECT pp.*,
       CASE 
         WHEN pp.id IN (SELECT membalik_id FROM pembayaran_piutang WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pp.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembayaran_piutang pp;

CREATE VIEW IF NOT EXISTS v_pembayaran_penitip_efektif AS
SELECT ppen.*,
       CASE 
         WHEN ppen.id IN (SELECT membalik_id FROM pembayaran_penitip WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN ppen.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembayaran_penitip ppen;
"""

DDL_MIGRASI_V5 = """
-- Tambah kolom anggota_id ke pembeli jika belum ada
ALTER TABLE pembeli ADD COLUMN anggota_id INTEGER REFERENCES anggota(id);

-- Tambah kolom harga_jual_satuan_dasar ke lot_stok jika belum ada
ALTER TABLE lot_stok ADD COLUMN harga_jual_satuan_dasar INTEGER NOT NULL DEFAULT 0;

-- Tabel Penitipan Harian
CREATE TABLE IF NOT EXISTS penitipan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penitip_id INTEGER NOT NULL REFERENCES penitip(id),
  tanggal TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif', 'selesai', 'dibatalkan')),
  catatan TEXT,
  membalik_id INTEGER REFERENCES penitipan(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_penitipan_penitip ON penitipan(penitip_id, tanggal);

CREATE TABLE IF NOT EXISTS penitipan_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penitipan_id INTEGER NOT NULL REFERENCES penitipan(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  jumlah_input INTEGER NOT NULL CHECK (jumlah_input > 0),
  satuan_input TEXT NOT NULL,
  isi_per_satuan INTEGER NOT NULL CHECK (isi_per_satuan > 0),
  jumlah_dasar INTEGER NOT NULL CHECK (jumlah_dasar > 0),
  harga_titip_satuan_dasar INTEGER NOT NULL CHECK (harga_titip_satuan_dasar >= 0),
  harga_jual_satuan_dasar INTEGER NOT NULL CHECK (harga_jual_satuan_dasar >= 0),
  lot_id INTEGER REFERENCES lot_stok(id),
  selesai INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_penitipan_baris_penitipan ON penitipan_baris(penitipan_id);
CREATE INDEX IF NOT EXISTS idx_penitipan_baris_barang ON penitipan_baris(barang_id);

CREATE TABLE IF NOT EXISTS pembayaran_penitip (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penitip_id INTEGER NOT NULL REFERENCES penitip(id),
  tanggal TEXT NOT NULL,
  total_laku_terbayar INTEGER NOT NULL DEFAULT 0,
  keterangan TEXT,
  membalik_id INTEGER REFERENCES pembayaran_penitip(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_bayar_penitip_tgl ON pembayaran_penitip(penitip_id, tanggal);

CREATE TABLE IF NOT EXISTS penyelesaian_titipan_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pembayaran_penitip_id INTEGER NOT NULL REFERENCES pembayaran_penitip(id),
  penitipan_baris_id INTEGER NOT NULL REFERENCES penitipan_baris(id),
  lot_id INTEGER NOT NULL REFERENCES lot_stok(id),
  qty_terjual INTEGER NOT NULL DEFAULT 0,
  harga_titip INTEGER NOT NULL DEFAULT 0,
  subtotal_bayar INTEGER NOT NULL DEFAULT 0,
  qty_sisa_retur INTEGER NOT NULL DEFAULT 0,
  qty_sisa_tinggal INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS penjualan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_nota TEXT NOT NULL UNIQUE,
  tanggal TEXT NOT NULL,
  pembeli_id INTEGER NOT NULL REFERENCES pembeli(id),
  nama_pembeli_nota TEXT,
  metode_bayar TEXT NOT NULL CHECK (metode_bayar IN ('tunai', 'kredit')),
  total INTEGER NOT NULL DEFAULT 0,
  jatuh_tempo TEXT,
  status TEXT NOT NULL DEFAULT 'selesai' CHECK (status IN ('selesai', 'dibatalkan')),
  keterangan TEXT,
  membalik_id INTEGER REFERENCES penjualan(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_penjualan_tgl ON penjualan(tanggal);
CREATE INDEX IF NOT EXISTS idx_penjualan_pembeli ON penjualan(pembeli_id);

CREATE TABLE IF NOT EXISTS penjualan_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penjualan_id INTEGER NOT NULL REFERENCES penjualan(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  jumlah_input INTEGER NOT NULL CHECK (jumlah_input > 0),
  satuan_input TEXT NOT NULL,
  isi_per_satuan INTEGER NOT NULL CHECK (isi_per_satuan > 0),
  jumlah_dasar INTEGER NOT NULL CHECK (jumlah_dasar > 0),
  harga_jual_satuan_dasar INTEGER NOT NULL CHECK (harga_jual_satuan_dasar >= 0),
  total_baris INTEGER NOT NULL CHECK (total_baris >= 0),
  hpp_total INTEGER NOT NULL DEFAULT 0,
  laba INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_penjualan_baris_penj ON penjualan_baris(penjualan_id);

CREATE TABLE IF NOT EXISTS penjualan_lot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penjualan_baris_id INTEGER NOT NULL REFERENCES penjualan_baris(id),
  lot_id INTEGER REFERENCES lot_stok(id),
  qty INTEGER NOT NULL CHECK (qty > 0),
  biaya INTEGER NOT NULL DEFAULT 0,
  penitip_id INTEGER REFERENCES penitip(id)
);
CREATE INDEX IF NOT EXISTS idx_penjualan_lot_baris ON penjualan_lot(penjualan_baris_id);
CREATE INDEX IF NOT EXISTS idx_penjualan_lot_lot ON penjualan_lot(lot_id);

CREATE TABLE IF NOT EXISTS pembayaran_piutang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pembeli_id INTEGER NOT NULL REFERENCES pembeli(id),
  tanggal TEXT NOT NULL,
  jumlah INTEGER NOT NULL CHECK (jumlah > 0),
  keterangan TEXT,
  membalik_id INTEGER REFERENCES pembayaran_piutang(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_bayar_piutang_pembeli ON pembayaran_piutang(pembeli_id);

CREATE TABLE IF NOT EXISTS alokasi_piutang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pembayaran_piutang_id INTEGER NOT NULL REFERENCES pembayaran_piutang(id),
  penjualan_id INTEGER NOT NULL REFERENCES penjualan(id),
  jumlah INTEGER NOT NULL CHECK (jumlah > 0),
  membalik_id INTEGER REFERENCES alokasi_piutang(id),
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_alokasi_penjualan ON alokasi_piutang(penjualan_id);

-- Views
CREATE VIEW IF NOT EXISTS v_penjualan_efektif AS
SELECT pj.*,
       CASE 
         WHEN pj.id IN (SELECT membalik_id FROM penjualan WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pj.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM penjualan pj;

CREATE VIEW IF NOT EXISTS v_penitipan_efektif AS
SELECT pt.*,
       CASE 
         WHEN pt.id IN (SELECT membalik_id FROM penitipan WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pt.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM penitipan pt;

CREATE VIEW IF NOT EXISTS v_pembayaran_piutang_efektif AS
SELECT pp.*,
       CASE 
         WHEN pp.id IN (SELECT membalik_id FROM pembayaran_piutang WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pp.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembayaran_piutang pp;

CREATE VIEW IF NOT EXISTS v_pembayaran_penitip_efektif AS
SELECT ppen.*,
       CASE 
         WHEN ppen.id IN (SELECT membalik_id FROM pembayaran_penitip WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN ppen.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembayaran_penitip ppen;
"""
