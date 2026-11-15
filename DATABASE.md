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
