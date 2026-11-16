"""
app/db/skema_modul15.py — DDL Skema dan Migrasi v6 untuk Modul 15:
- Retur Supplier: retur_supplier, retur_supplier_baris
- Retur Penjualan: retur_penjualan, retur_penjualan_baris
- Stock Opname: opname_sesi, opname_barang
- Closing Toko: closing_toko, closing_stok_barang
- Views Efektif: v_retur_supplier_efektif, v_retur_penjualan_efektif
"""

DDL_MIGRASI_V6 = """
-- 1. Retur ke Supplier
CREATE TABLE IF NOT EXISTS retur_supplier (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_retur TEXT NOT NULL UNIQUE,
  tanggal TEXT NOT NULL,
  pembelian_faktur_id INTEGER REFERENCES pembelian_faktur(id),
  supplier_id INTEGER NOT NULL REFERENCES supplier(id),
  total_retur INTEGER NOT NULL CHECK (total_retur >= 0),
  jenis_kompensasi TEXT NOT NULL CHECK (jenis_kompensasi IN ('potong_hutang', 'kas_masuk')),
  kas_toko_transaksi_id INTEGER REFERENCES kas_toko_transaksi(id),
  alasan TEXT,
  membalik_id INTEGER REFERENCES retur_supplier(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_retur_supp_tgl ON retur_supplier(tanggal);
CREATE INDEX IF NOT EXISTS idx_retur_supp_supp ON retur_supplier(supplier_id);

CREATE TABLE IF NOT EXISTS retur_supplier_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  retur_supplier_id INTEGER NOT NULL REFERENCES retur_supplier(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  lot_id INTEGER NOT NULL REFERENCES lot_stok(id),
  jumlah_dasar INTEGER NOT NULL CHECK (jumlah_dasar > 0),
  biaya_per_satuan_dasar INTEGER NOT NULL CHECK (biaya_per_satuan_dasar >= 0),
  total_biaya INTEGER NOT NULL CHECK (total_biaya >= 0),
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 2. Retur Penjualan (Konsumen / Pembeli Mengembalikan Barang)
CREATE TABLE IF NOT EXISTS retur_penjualan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_retur TEXT NOT NULL UNIQUE,
  tanggal TEXT NOT NULL,
  penjualan_id INTEGER NOT NULL REFERENCES penjualan(id),
  pembeli_id INTEGER NOT NULL REFERENCES pembeli(id),
  total_retur INTEGER NOT NULL CHECK (total_retur >= 0),
  jenis_kompensasi TEXT NOT NULL CHECK (jenis_kompensasi IN ('kembali_kas', 'potong_piutang')),
  kas_toko_transaksi_id INTEGER REFERENCES kas_toko_transaksi(id),
  alasan TEXT,
  membalik_id INTEGER REFERENCES retur_penjualan(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_retur_pj_tgl ON retur_penjualan(tanggal);
CREATE INDEX IF NOT EXISTS idx_retur_pj_penj ON retur_penjualan(penjualan_id);

CREATE TABLE IF NOT EXISTS retur_penjualan_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  retur_penjualan_id INTEGER NOT NULL REFERENCES retur_penjualan(id),
  penjualan_baris_id INTEGER NOT NULL REFERENCES penjualan_baris(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  lot_id INTEGER NOT NULL REFERENCES lot_stok(id),
  jumlah_dasar INTEGER NOT NULL CHECK (jumlah_dasar > 0),
  harga_jual_satuan_dasar INTEGER NOT NULL CHECK (harga_jual_satuan_dasar >= 0),
  total_harga INTEGER NOT NULL CHECK (total_harga >= 0),
  hpp_satuan_dasar INTEGER NOT NULL DEFAULT 0,
  hpp_total INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 3. Stock Opname
CREATE TABLE IF NOT EXISTS opname_sesi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kode_opname TEXT NOT NULL UNIQUE,
  tanggal TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'final')),
  catatan TEXT,
  total_selisih_kurang_qty INTEGER NOT NULL DEFAULT 0,
  total_selisih_kurang_nilai INTEGER NOT NULL DEFAULT 0,
  total_selisih_lebih_qty INTEGER NOT NULL DEFAULT 0,
  total_selisih_lebih_nilai INTEGER NOT NULL DEFAULT 0,
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS opname_barang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opname_sesi_id INTEGER NOT NULL REFERENCES opname_sesi(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  stok_sistem INTEGER NOT NULL,
  stok_fisik INTEGER NOT NULL,
  selisih_qty INTEGER NOT NULL,
  harga_satuan_dasar INTEGER NOT NULL DEFAULT 0,
  selisih_nilai INTEGER NOT NULL DEFAULT 0,
  catatan TEXT,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (opname_sesi_id, barang_id)
);
CREATE INDEX IF NOT EXISTS idx_opname_barang_brg ON opname_barang(barang_id);

-- 4. Closing Toko
CREATE TABLE IF NOT EXISTS closing_toko (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  periode TEXT NOT NULL UNIQUE,
  tanggal TEXT NOT NULL,
  kas_toko_awal INTEGER NOT NULL DEFAULT 0,
  kas_toko_masuk INTEGER NOT NULL DEFAULT 0,
  kas_toko_keluar INTEGER NOT NULL DEFAULT 0,
  kas_toko_akhir INTEGER NOT NULL DEFAULT 0,
  total_penjualan INTEGER NOT NULL DEFAULT 0,
  total_hpp INTEGER NOT NULL DEFAULT 0,
  laba_kotor INTEGER NOT NULL DEFAULT 0,
  kerugian_persediaan INTEGER NOT NULL DEFAULT 0,
  nilai_persediaan INTEGER NOT NULL DEFAULT 0,
  total_piutang INTEGER NOT NULL DEFAULT 0,
  total_hutang_supplier INTEGER NOT NULL DEFAULT 0,
  total_hutang_penitip INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'closed' CHECK (status IN ('closed', 'dibuka_kembali')),
  catatan TEXT,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS closing_stok_barang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  closing_toko_id INTEGER NOT NULL REFERENCES closing_toko(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  stok_akhir_dasar INTEGER NOT NULL,
  nilai_persediaan INTEGER NOT NULL,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (closing_toko_id, barang_id)
);
CREATE INDEX IF NOT EXISTS idx_closing_stok_brg ON closing_stok_barang(barang_id);

-- 5. Views Efektif Modul 15
CREATE VIEW IF NOT EXISTS v_retur_supplier_efektif AS
SELECT rs.*,
       CASE 
         WHEN rs.id IN (SELECT membalik_id FROM retur_supplier WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN rs.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM retur_supplier rs;

CREATE VIEW IF NOT EXISTS v_retur_penjualan_efektif AS
SELECT rp.*,
       CASE 
         WHEN rp.id IN (SELECT membalik_id FROM retur_penjualan WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN rp.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM retur_penjualan rp;
"""
