# DATABASE.md — Skema SQLite

Database: **satu file** `koperasi.db` (SQLite). Lokasi: folder `data/` di samping aplikasi.

## Konvensi

- **Uang**: `INTEGER` dalam rupiah penuh. JANGAN pakai REAL/FLOAT.
- **Tanggal**: `TEXT` format ISO `YYYY-MM-DD`. Waktu lengkap: `YYYY-MM-DD HH:MM:SS`.
- **Persen**: simpan sebagai `INTEGER` dalam basis poin per 10.000 ATAU `TEXT`/`NUMERIC` dibaca dengan `decimal.Decimal`. Pilihan proyek ini: simpan `jasa_persen_per_bulan` sebagai `REAL` HANYA untuk konfigurasi, dan hitung angsuran memakai `Decimal` lalu bulatkan ke integer.
- Semua tabel punya `id INTEGER PRIMARY KEY AUTOINCREMENT`, `dibuat_pada`, kecuali dinyatakan lain.
- **Tidak ada DELETE** pada tabel transaksi. Koreksi = transaksi pembalik (`membalik_id`).
- Saat membuka koneksi: `PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA synchronous=FULL;`
- Versi skema disimpan di `PRAGMA user_version` untuk migrasi di masa depan.

## Tabel

### pengaturan
Pasangan kunci-nilai untuk konfigurasi.
```sql
CREATE TABLE pengaturan (
  kunci TEXT PRIMARY KEY,
  nilai TEXT NOT NULL
);
-- contoh kunci: nama_koperasi, hari_awal_minggu, pin_hash,
-- backup_jumlah_simpan, backup_folder_kedua, denda_aktif
```

### anggota
```sql
CREATE TABLE anggota (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_anggota TEXT NOT NULL UNIQUE,
  nama TEXT NOT NULL,
  nik_karyawan TEXT,
  unit TEXT,
  no_hp TEXT,
  alamat TEXT,
  tanggal_masuk TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif','keluar')),
  tanggal_keluar TEXT,
  catatan TEXT,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_anggota_nama ON anggota(nama);
```

### simpanan_transaksi
Saldo = jumlah setor dikurangi jumlah tarik (dihitung dengan SUM), TIDAK disimpan permanen kecuali di snapshot closing.
```sql
CREATE TABLE simpanan_transaksi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  anggota_id INTEGER NOT NULL REFERENCES anggota(id),
  jenis TEXT NOT NULL CHECK (jenis IN ('pokok','wajib','sukarela')),
  arah TEXT NOT NULL CHECK (arah IN ('setor','tarik')),
  jumlah INTEGER NOT NULL CHECK (jumlah > 0),
  tanggal TEXT NOT NULL,
  keterangan TEXT,
  membalik_id INTEGER REFERENCES simpanan_transaksi(id),
  periode TEXT NOT NULL,            -- 'YYYY-MM', turunan dari tanggal
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_simp_anggota ON simpanan_transaksi(anggota_id, tanggal);
CREATE INDEX idx_simp_tanggal ON simpanan_transaksi(tanggal);
```

### produk_pinjaman
Parameter jenis pinjaman, agar angka tidak di-hardcode.
```sql
CREATE TABLE produk_pinjaman (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL UNIQUE,
  jasa_persen_per_bulan REAL NOT NULL,   -- contoh 1.5 = 1,5% per bulan (flat)
  tenor_min INTEGER NOT NULL DEFAULT 1,
  tenor_maks INTEGER NOT NULL DEFAULT 60,
  plafon_maks INTEGER,
  biaya_admin INTEGER NOT NULL DEFAULT 0,
  aktif INTEGER NOT NULL DEFAULT 1
);
```

### pinjaman
Setelah dibuat, parameter pinjaman (plafon, tenor, jasa) **tidak boleh diubah**. Simpan salinan nilai produk saat itu.
```sql
CREATE TABLE pinjaman (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_pinjaman TEXT NOT NULL UNIQUE,
  anggota_id INTEGER NOT NULL REFERENCES anggota(id),
  produk_id INTEGER REFERENCES produk_pinjaman(id),
  plafon INTEGER NOT NULL CHECK (plafon > 0),
  tenor INTEGER NOT NULL CHECK (tenor > 0),
  jasa_persen_per_bulan REAL NOT NULL,
  biaya_admin INTEGER NOT NULL DEFAULT 0,
  tanggal_cair TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif','lunas','batal')),
  tanggal_lunas TEXT,
  keperluan TEXT,
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_pinjaman_anggota ON pinjaman(anggota_id, status);
```

### angsuran
Satu baris per cicilan, dibuat otomatis saat pinjaman disimpan.
```sql
CREATE TABLE angsuran (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pinjaman_id INTEGER NOT NULL REFERENCES pinjaman(id),
  angsuran_ke INTEGER NOT NULL,
  jatuh_tempo TEXT NOT NULL,
  pokok INTEGER NOT NULL,          -- tagihan pokok
  jasa INTEGER NOT NULL,           -- tagihan jasa
  UNIQUE (pinjaman_id, angsuran_ke)
);
CREATE INDEX idx_angsuran_tempo ON angsuran(jatuh_tempo);
```

### pembayaran_angsuran
Pembayaran dicatat terpisah dari tagihan agar bayar sebagian dan pelunasan dipercepat bisa ditangani. Status angsuran dihitung dari tabel ini.
```sql
CREATE TABLE pembayaran_angsuran (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pinjaman_id INTEGER NOT NULL REFERENCES pinjaman(id),
  angsuran_id INTEGER REFERENCES angsuran(id),  -- NULL untuk pelunasan dipercepat
  tanggal TEXT NOT NULL,
  bayar_pokok INTEGER NOT NULL DEFAULT 0,
  bayar_jasa INTEGER NOT NULL DEFAULT 0,
  denda INTEGER NOT NULL DEFAULT 0,
  keterangan TEXT,
  membalik_id INTEGER REFERENCES pembayaran_angsuran(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_bayar_tanggal ON pembayaran_angsuran(tanggal);
CREATE INDEX idx_bayar_pinjaman ON pembayaran_angsuran(pinjaman_id);
```

### kas_transaksi
Buku kas. Transaksi dari simpanan/pinjaman/angsuran masuk **otomatis** (`sumber` != 'manual'). Pengeluaran lain (ATK, listrik, dsb.) dicatat manual.
```sql
CREATE TABLE kas_transaksi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tanggal TEXT NOT NULL,
  keterangan TEXT NOT NULL,
  masuk INTEGER NOT NULL DEFAULT 0,
  keluar INTEGER NOT NULL DEFAULT 0,
  sumber TEXT NOT NULL CHECK (sumber IN ('simpanan','pencairan','angsuran','biaya_admin','manual')),
  ref_id INTEGER,                     -- id baris asal (simpanan/pinjaman/pembayaran)
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  CHECK ((masuk > 0 AND keluar = 0) OR (keluar > 0 AND masuk = 0))
);
CREATE INDEX idx_kas_tanggal ON kas_transaksi(tanggal);
```

### closing
Satu baris per bulan yang sudah ditutup.
```sql
CREATE TABLE closing (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  periode TEXT NOT NULL UNIQUE,       -- 'YYYY-MM'
  tanggal_closing TEXT NOT NULL,
  saldo_kas_awal INTEGER NOT NULL,
  total_kas_masuk INTEGER NOT NULL,
  total_kas_keluar INTEGER NOT NULL,
  saldo_kas_akhir INTEGER NOT NULL,
  total_simpanan INTEGER NOT NULL,
  total_sisa_pokok_pinjaman INTEGER NOT NULL,
  total_jasa_diterima INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'tertutup' CHECK (status IN ('tertutup','dibuka_kembali')),
  catatan TEXT
);
```

### closing_saldo_anggota
Snapshot per anggota per akhir bulan, supaya histori bisa dibuka cepat tanpa menghitung ulang semuanya.
```sql
CREATE TABLE closing_saldo_anggota (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  closing_id INTEGER NOT NULL REFERENCES closing(id),
  anggota_id INTEGER NOT NULL REFERENCES anggota(id),
  saldo_pokok INTEGER NOT NULL DEFAULT 0,
  saldo_wajib INTEGER NOT NULL DEFAULT 0,
  saldo_sukarela INTEGER NOT NULL DEFAULT 0,
  sisa_pokok_pinjaman INTEGER NOT NULL DEFAULT 0,
  UNIQUE (closing_id, anggota_id)
);
```

### laporan_mingguan_log
Untuk pengingat "laporan mingguan belum dibuat".
```sql
CREATE TABLE laporan_mingguan_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tanggal_awal TEXT NOT NULL,
  tanggal_akhir TEXT NOT NULL,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (tanggal_awal, tanggal_akhir)
);
```

### draft
Menyimpan isian form yang belum selesai agar muncul lagi setelah aplikasi ditutup.
```sql
CREATE TABLE draft (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  jenis_form TEXT NOT NULL UNIQUE,    -- 'simpanan','angsuran','pinjaman','anggota'
  isi_json TEXT NOT NULL,
  diubah_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

### log_aktivitas
```sql
CREATE TABLE log_aktivitas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  waktu TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  aksi TEXT NOT NULL,                 -- 'tambah','ubah','balik','closing','buka_closing','impor','backup'
  tabel TEXT,
  ref_id INTEGER,
  detail TEXT                         -- ringkasan manusiawi, contoh: 'Input angsuran ke-3 Budi Rp 1.100.000'
);
CREATE INDEX idx_log_waktu ON log_aktivitas(waktu);
```

### View Transaksi Efektif (v_simpanan_efektif & v_pembayaran_angsuran_efektif)
Menyediakan status efektif terpusat: `'NORMAL'`, `'DIBATALKAN'`, atau `'PEMBALIK'`.
```sql
CREATE VIEW v_simpanan_efektif AS
SELECT st.*,
       CASE 
         WHEN st.id IN (SELECT membalik_id FROM simpanan_transaksi WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN st.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM simpanan_transaksi st;

CREATE VIEW v_pembayaran_angsuran_efektif AS
SELECT pa.*,
       CASE 
         WHEN pa.id IN (SELECT membalik_id FROM pembayaran_angsuran WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pa.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembayaran_angsuran pa;
```

### Pencarian cepat (opsional, tahap 6)
Gunakan tabel virtual FTS5 jika tersedia, atau `LIKE` dengan indeks pada nama.
```sql
CREATE VIRTUAL TABLE anggota_cari USING fts5(nama, no_anggota, nik_karyawan, content='anggota', content_rowid='id');
```

## Aturan Perhitungan (wajib diuji unit test)

1. **Jadwal flat**
   - `pokok_dasar = plafon // tenor`; `jasa_dasar = round(plafon * persen / 100)`
   - Angsuran ke-1..(n-1): pokok = `pokok_dasar`, jasa = `jasa_dasar`
   - Angsuran ke-n: pokok = `plafon - pokok_dasar * (n-1)` (menyerap sisa pembulatan)
   - Pastikan `SUM(pokok) == plafon`.
2. **Jatuh tempo**: tanggal_cair + k bulan. Jika tanggal tidak ada di bulan tujuan (mis. 31), pakai hari terakhir bulan itu.
3. **Saldo simpanan** = `SUM(setor) - SUM(tarik)` per anggota per jenis, memperhitungkan transaksi pembalik.
4. **Sisa pokok pinjaman** = `plafon - SUM(bayar_pokok)` (memperhitungkan pembalik).
5. **Status angsuran**: lunas jika pokok & jasa terbayar penuh; sebagian jika ada pembayaran tapi kurang; telat jika lewat jatuh tempo dan belum lunas.
6. **Saldo kas** = saldo awal periode + `SUM(masuk)` - `SUM(keluar)`.
7. **Periode terkunci**: tolak INSERT/UPDATE pada transaksi dengan `periode` yang sudah ada di `closing` berstatus `tertutup`.

---

## Modul 13: Fondasi Unit Toko (user_version = 4)

### supplier
```sql
CREATE TABLE supplier (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL,
  no_hp TEXT,
  alamat TEXT,
  catatan TEXT,
  aktif INTEGER NOT NULL DEFAULT 1,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_supplier_nama ON supplier(nama);
```

### penitip
```sql
CREATE TABLE penitip (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL,
  no_hp TEXT,
  alamat TEXT,
  catatan TEXT,
  aktif INTEGER NOT NULL DEFAULT 1,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_penitip_nama ON penitip(nama);
```

### pembeli
```sql
CREATE TABLE pembeli (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL,
  no_hp TEXT,
  alamat TEXT,
  catatan TEXT,
  aktif INTEGER NOT NULL DEFAULT 1,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_pembeli_nama ON pembeli(nama);
```

### barang
```sql
CREATE TABLE barang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kode TEXT NOT NULL UNIQUE,
  nama TEXT NOT NULL,
  kategori TEXT,
  satuan_dasar TEXT NOT NULL,
  kata_kunci TEXT,
  harga_jual INTEGER NOT NULL DEFAULT 0,
  jenis_kepemilikan TEXT NOT NULL DEFAULT 'milik_koperasi' CHECK (jenis_kepemilikan IN ('milik_koperasi', 'titipan')),
  penitip_id INTEGER REFERENCES penitip(id),
  stok_minimum INTEGER NOT NULL DEFAULT 0,
  stok_saat_ini INTEGER NOT NULL DEFAULT 0,
  aktif INTEGER NOT NULL DEFAULT 1,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_barang_nama ON barang(nama);
CREATE INDEX idx_barang_kode ON barang(kode);
```

### satuan_barang (Konversi Melekat pada Barang)
```sql
CREATE TABLE satuan_barang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  nama_satuan TEXT NOT NULL,
  isi_dalam_satuan_dasar INTEGER NOT NULL CHECK (isi_dalam_satuan_dasar > 0),
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (barang_id, nama_satuan)
);
CREATE INDEX idx_satuan_barang ON satuan_barang(barang_id);
```

### kas_toko_transaksi (TERPISAH dari Kas Simpan Pinjam)
```sql
CREATE TABLE kas_toko_transaksi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tanggal TEXT NOT NULL,
  keterangan TEXT NOT NULL,
  masuk INTEGER NOT NULL DEFAULT 0,
  keluar INTEGER NOT NULL DEFAULT 0,
  sumber TEXT NOT NULL CHECK (sumber IN ('modal_awal', 'pembelian', 'bayar_hutang', 'penjualan', 'manual')),
  ref_tabel TEXT,
  ref_id INTEGER,
  membalik_id INTEGER REFERENCES kas_toko_transaksi(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  CHECK ((masuk > 0 AND keluar = 0) OR (keluar > 0 AND masuk = 0))
);
CREATE INDEX idx_kas_toko_tanggal ON kas_toko_transaksi(tanggal);
```

### pembelian_faktur
```sql
CREATE TABLE pembelian_faktur (
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
CREATE INDEX idx_faktur_tanggal ON pembelian_faktur(tanggal);
CREATE INDEX idx_faktur_supplier ON pembelian_faktur(supplier_id);
```

### pembelian_detail (Snapshot Konversi)
```sql
CREATE TABLE pembelian_detail (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  faktur_id INTEGER NOT NULL REFERENCES pembelian_faktur(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  jumlah_input INTEGER NOT NULL CHECK (jumlah_input > 0),
  satuan_input TEXT NOT NULL,
  isi_per_satuan INTEGER NOT NULL CHECK (isi_per_satuan > 0),
  jumlah_dasar INTEGER NOT NULL CHECK (jumlah_dasar > 0),
  harga_per_satuan_input INTEGER NOT NULL CHECK (harga_per_satuan_input >= 0),
  total_biaya INTEGER NOT NULL CHECK (total_biaya >= 0)
);
CREATE INDEX idx_detail_faktur ON pembelian_detail(faktur_id);
CREATE INDEX idx_detail_barang ON pembelian_detail(barang_id);
```

### pembayaran_hutang_supplier
```sql
CREATE TABLE pembayaran_hutang_supplier (
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
```

### lot_stok (FIFO)
```sql
CREATE TABLE lot_stok (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  asal TEXT NOT NULL CHECK (asal IN ('pembelian', 'titipan', 'penyesuaian', 'koreksi')),
  ref_tabel TEXT,
  ref_id INTEGER,
  tanggal_masuk TEXT NOT NULL,
  supplier_id INTEGER REFERENCES supplier(id),
  penitip_id INTEGER REFERENCES penitip(id),
  qty_awal INTEGER NOT NULL CHECK (qty_awal >= 0),
  qty_sisa INTEGER NOT NULL CHECK (qty_sisa >= 0),
  total_biaya_awal INTEGER NOT NULL CHECK (total_biaya_awal >= 0),
  biaya_sisa INTEGER NOT NULL CHECK (biaya_sisa >= 0),
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_lot_barang ON lot_stok(barang_id, tanggal_masuk, id);
```

### mutasi_stok (Buku Mutasi Append-Only)
```sql
CREATE TABLE mutasi_stok (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  lot_id INTEGER REFERENCES lot_stok(id),
  tanggal TEXT NOT NULL,
  jenis TEXT NOT NULL CHECK (jenis IN (
    'masuk', 'keluar_jual', 'retur_supplier', 'retur_penitip',
    'rusak', 'hilang', 'kedaluwarsa', 'penyesuaian_opname', 'koreksi'
  )),
  qty INTEGER NOT NULL,
  biaya INTEGER NOT NULL DEFAULT 0,
  ref_tabel TEXT,
  ref_id INTEGER,
  membalik_id INTEGER REFERENCES mutasi_stok(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_mutasi_barang ON mutasi_stok(barang_id, tanggal);
CREATE INDEX idx_mutasi_lot ON mutasi_stok(lot_id);
```

### View Transaksi Efektif Toko
- `v_mutasi_stok_efektif`
- `v_pembelian_faktur_efektif`
- `v_kas_toko_efektif`
- `v_penjualan_efektif`
- `v_penitipan_efektif`
- `v_pembayaran_piutang_efektif`
- `v_pembayaran_penitip_efektif`

---

## Modul 14: Penjualan, Piutang Pembeli, dan Titipan Harian (PRAGMA user_version = 5)

### pembeli (Diperkaya kolom anggota_id)
```sql
CREATE TABLE pembeli (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL,
  no_hp TEXT,
  alamat TEXT,
  catatan TEXT,
  anggota_id INTEGER REFERENCES anggota(id),
  aktif INTEGER NOT NULL DEFAULT 1 CHECK (aktif IN (0, 1)),
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX idx_pembeli_nama ON pembeli(nama);
CREATE INDEX idx_pembeli_anggota ON pembeli(anggota_id);
```

### penitipan & penitipan_baris
```sql
CREATE TABLE penitipan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tanggal TEXT NOT NULL,
  penitip_id INTEGER NOT NULL REFERENCES penitip(id),
  status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif', 'selesai', 'batal')),
  catatan TEXT,
  membalik_id INTEGER REFERENCES penitipan(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE penitipan_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penitipan_id INTEGER NOT NULL REFERENCES penitipan(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  jumlah_input INTEGER NOT NULL CHECK (jumlah_input > 0),
  satuan_input TEXT NOT NULL,
  isi_per_satuan INTEGER NOT NULL CHECK (isi_per_satuan > 0),
  jumlah_dasar INTEGER NOT NULL CHECK (jumlah_dasar > 0),
  harga_titip_satuan_dasar INTEGER NOT NULL CHECK (harga_titip_satuan_dasar >= 0),
  harga_jual_satuan_dasar INTEGER NOT NULL CHECK (harga_jual_satuan_dasar >= 0),
  lot_id INTEGER NOT NULL REFERENCES lot_stok(id),
  selesai INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

### pembayaran_penitip & penyelesaian_titipan_baris
```sql
CREATE TABLE pembayaran_penitip (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penitip_id INTEGER NOT NULL REFERENCES penitip(id),
  tanggal TEXT NOT NULL,
  total_laku_terbayar INTEGER NOT NULL CHECK (total_laku_terbayar >= 0),
  kas_toko_transaksi_id INTEGER REFERENCES kas_toko_transaksi(id),
  keterangan TEXT,
  membalik_id INTEGER REFERENCES pembayaran_penitip(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE penyelesaian_titipan_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pembayaran_penitip_id INTEGER NOT NULL REFERENCES pembayaran_penitip(id),
  penitipan_baris_id INTEGER NOT NULL REFERENCES penitipan_baris(id),
  lot_id INTEGER NOT NULL REFERENCES lot_stok(id),
  qty_terjual INTEGER NOT NULL DEFAULT 0,
  harga_titip INTEGER NOT NULL DEFAULT 0,
  total_bayar INTEGER NOT NULL DEFAULT 0,
  qty_retur INTEGER NOT NULL DEFAULT 0,
  qty_tinggal INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

### penjualan, penjualan_baris, dan penjualan_lot
```sql
CREATE TABLE penjualan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_nota TEXT NOT NULL UNIQUE,
  tanggal TEXT NOT NULL,
  pembeli_id INTEGER NOT NULL REFERENCES pembeli(id),
  nama_pembeli_nota TEXT,
  metode TEXT NOT NULL CHECK (metode IN ('tunai', 'kredit')),
  total INTEGER NOT NULL CHECK (total >= 0),
  jatuh_tempo TEXT,
  status TEXT NOT NULL DEFAULT 'selesai' CHECK (status IN ('selesai', 'dibatalkan')),
  membalik_id INTEGER REFERENCES penjualan(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE penjualan_baris (
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
  laba INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE penjualan_lot (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  penjualan_baris_id INTEGER NOT NULL REFERENCES penjualan_baris(id),
  lot_id INTEGER NOT NULL REFERENCES lot_stok(id),
  qty INTEGER NOT NULL CHECK (qty > 0),
  biaya INTEGER NOT NULL CHECK (biaya >= 0),
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

### pembayaran_piutang & alokasi_piutang
```sql
CREATE TABLE pembayaran_piutang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pembeli_id INTEGER NOT NULL REFERENCES pembeli(id),
  tanggal TEXT NOT NULL,
  jumlah INTEGER NOT NULL CHECK (jumlah > 0),
  kas_toko_transaksi_id INTEGER REFERENCES kas_toko_transaksi(id),
  keterangan TEXT,
  membalik_id INTEGER REFERENCES pembayaran_piutang(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE alokasi_piutang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pembayaran_id INTEGER NOT NULL REFERENCES pembayaran_piutang(id),
  penjualan_id INTEGER NOT NULL REFERENCES penjualan(id),
  jumlah INTEGER NOT NULL CHECK (jumlah > 0),
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

---

## Modul 15: Kartu Barang, Retur, Stock Opname, Laporan Toko, Closing Toko (PRAGMA user_version = 6)

### retur_supplier & retur_supplier_baris
```sql
CREATE TABLE retur_supplier (
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

CREATE TABLE retur_supplier_baris (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  retur_supplier_id INTEGER NOT NULL REFERENCES retur_supplier(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  lot_id INTEGER NOT NULL REFERENCES lot_stok(id),
  jumlah_dasar INTEGER NOT NULL CHECK (jumlah_dasar > 0),
  biaya_per_satuan_dasar INTEGER NOT NULL CHECK (biaya_per_satuan_dasar >= 0),
  total_biaya INTEGER NOT NULL CHECK (total_biaya >= 0),
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
```

### retur_penjualan & retur_penjualan_baris
```sql
CREATE TABLE retur_penjualan (
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

CREATE TABLE retur_penjualan_baris (
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
```

### opname_sesi & opname_barang
```sql
CREATE TABLE opname_sesi (
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

CREATE TABLE opname_barang (
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
```

### closing_toko & closing_stok_barang
```sql
CREATE TABLE closing_toko (
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

CREATE TABLE closing_stok_barang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  closing_toko_id INTEGER NOT NULL REFERENCES closing_toko(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  stok_akhir_dasar INTEGER NOT NULL,
  nilai_persediaan INTEGER NOT NULL,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (closing_toko_id, barang_id)
);
```

### View Transaksi Efektif Modul 15
- `v_retur_supplier_efektif`
- `v_retur_penjualan_efektif`



