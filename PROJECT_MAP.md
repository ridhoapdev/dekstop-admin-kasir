# PROJECT_MAP.md — Peta Arsitektur & Pemahaman Teknis Aplikasi Koperasi

> **Tujuan Dokumen**: Dokumen ini mendeskripsikan kondisi nyata implementasi kode sumber aplikasi Koperasi (Unit Simpan Pinjam dan Unit Usaha Toko) per 16 November 2026. Dokumen ini disusun untuk dibaca oleh AI atau pengembang independen tanpa akses langsung ke repositori, dengan prinsip objektivitas murni, akurasi baris kode, dan tanpa asumsi.

---

## 1. IDENTITAS TEKNIS

- **Bahasa Pemrograman**: Python 3.13 (Target OS: Windows 10/11 64-bit).
- **Framework UI**: PySide6 (`PySide6>=6.6.0`, Qt 6 Desktop).
- **Database Engine**: SQLite 3 (Database lokal pada file `data/koperasi.db`).
- **Pragma Database** (`app/db/koneksi.py:26-29`):
  - `journal_mode = WAL` (Write-Ahead Logging untuk konkurensi aman)
  - `foreign_keys = ON` (Integritas relasional tabel)
  - `synchronous = FULL` (Ketahanan data saat insiden listrik/crash)
  - `busy_timeout = 5000` (Timeout antrean kunci 5 detik)
- **Library Utama** (`requirements.txt:1-4`):
  - `PySide6`: Antarmuka grafis desktop (GUI).
  - `pytest`: Kerangka pengujian otomatis (76 test suite aktif).
  - `openpyxl`: Pemrosesan, pembacaan, dan pembuatan berkas lembar kerja Excel (.xlsx).
  - `reportlab`: Pembangkitan dokumen cetak dan kuitansi PDF format vektor.
- **Cara Menjalankan**:
  ```powershell
  python main.py
  ```
  Menjalankan test suite:
  ```powershell
  python -m pytest
  ```
- **Struktur Folder**:
  ```text
  d:\app-admin-mamah\
  ├── data\                      # Direktori penyimpanan basis data koperasi.db
  ├── backup\                    # Arsip cadangan berkas database otomatis (.db)
  ├── log\                       # Berkas pencatatan rotasi aktivitas sistem (app.log)
  ├── main.py                    # Titik masuk eksekusi GUI, logging rotasi, dan backup startup
  ├── seeder.py                  # Generator data simulasi demo (simpan pinjam & toko)
  ├── requirements.txt           # Deklarasi pustaka dependensi Python
  ├── app\
  │   ├── config.py              # Definisi konstanta konfigurasi jalur berkas dan versi sistem
  │   ├── aset\                  # Ikon visual antarmuka (panah, kontrol tabel)
  │   ├── db\                    # Modul DDL skema, migrasi user_version, dan repositori kueri SQL
  │   │   ├── koneksi.py         # Factory pembuka koneksi sqlite3 dan inisialisasi PRAGMA
  │   │   ├── skema.py           # DDL Unit Simpan Pinjam & pengatur migrasi user_version (v1-v6)
  │   │   ├── skema_toko.py      # DDL Unit Toko (Master barang, lot FIFO, kasir, piutang, titipan)
  │   │   ├── skema_modul15.py   # DDL Unit Toko Modul 15 (Retur, opname, closing toko)
  │   │   └── repo_*.py          # 23 file modul repositori SQL murni
  │   ├── layanan\               # Layanan bisnis lintas modul dan I/O berkas
  │   │   ├── backup.py          # Prosedur pencadangan online sqlite3 API dan rotasi 30 file
  │   │   ├── bus_sinyal.py      # Event bus sinkron in-memory untuk pembaruan antar-layar
  │   │   ├── cetak_kuitansi.py  # Pembuat PDF kuitansi simpanan & angsuran ukuran A5
  │   │   ├── ekspor_excel.py    # Generator rekap laporan mingguan format .xlsx
  │   │   ├── ekspor_pdf.py      # Generator rekap laporan mingguan format PDF reportlab
  │   │   ├── ekspor_laporan_periode.py # Ekspor laporan bulanan & tahunan SP ke Excel/PDF
  │   │   ├── ekspor_laporan_toko.py    # Ekspor laporan rekapitulasi toko ke Excel/PDF
  │   │   ├── impor_excel.py     # Generator template & parser impor data anggota/saldo/pinjaman
  │   │   └── layanan_stok.py    # Sumber kebenaran tunggal mutasi stok FIFO real-time
  │   ├── logika\                # Modul komputasi matematis & akuntansi murni (tanpa GUI)
  │   │   ├── angsuran_flat.py   # Algoritma cicilan pinjaman flat, bunga Decimal, serap cicilan akhir
  │   │   └── transaksi_efektif.py # Mesin klasifikasi transaksi normal vs pembalik lintas periode
  │   ├── ui\                    # Presentasi antarmuka pengguna PySide6
  │   │   ├── jendela_utama.py   # QMainWindow, sidebar navigasi vertikal, header pencarian global
  │   │   ├── tema.py            # Global Qt Style Sheet (QSS)
  │   │   ├── komponen\          # Widget input kustom (input_rupiah, grafik_batang_qt)
  │   │   └── layar_*.py         # Layar tampilan kerja per modul (23 modul layar UI)
  │   └── util\                  # Pembantu format teks, rupiah, tanggal, dan fuzzy matcher
  └── tests\                     # Kumpulan berkas pengujian unit pytest
  ```

---

## 2. DAFTAR HALAMAN / MENU / FITUR

Navigasi aplikasi berbasis `QStackedWidget` di `app/ui/jendela_utama.py:144-240`, dikendalikan melalui bilah samping (sidebar) vertikal.

| Nama Halaman | Kunci Navigasi / Indeks Stack | Batasan Peran | Fungsi Singkat | File Terkait |
|---|---|---|---|---|
| Ringkasan Koperasi | `ringkasan` (Stack 0) | Terbuka (Tanpa peran) | Dasbor metrik harian SP, kas saat ini, pengingat jatuh tempo, tunggakan, dan tombol cepat input. | `app/ui/layar_ringkasan.py` |
| Data Anggota | `anggota` (Stack 1) | Terbuka (Tanpa peran) | Manajemen master anggota, tambah, edit, nonaktifkan, pencarian fuzzy, proteksi hapus jika bertransaksi. | `app/ui/layar_anggota.py` |
| Transaksi Simpanan | `simpanan` (Stack 2) | Terbuka (Tanpa peran) | Input setoran/penarikan simpanan pokok/wajib/sukarela, cetak kuitansi, koreksi pembalik. | `app/ui/layar_simpanan.py` |
| Data Pinjaman | `pinjaman` (Stack 3) | Terbuka (Tanpa peran) | Pengajuan pinjaman, kalkulasi jadwal cicilan flat pratinjau, persetujuan pengurus, pencairan pinjaman. | `app/ui/layar_pinjaman.py` |
| Pembayaran Angsuran | `angsuran` (Stack 4) | Terbuka (Tanpa peran) | Pembayaran cicilan angsuran per tenor atau pelunasan dipercepat, denda, kuitansi, pembalik. | `app/ui/layar_angsuran.py` |
| Kartu Anggota | `kartu_anggota` (Stack 5) | Terbuka (Tanpa peran) | Riwayat komprehensif profil anggota, saldo simpanan, status pinjaman aktif, transaksi gabungan, piutang toko. | `app/ui/layar_kartu_anggota.py` |
| Filter Cepat Transaksi | `filter_cepat` (Stack 6) | Terbuka (Tanpa peran) | Penelusuran transaksi cepat 6 mode (hari ini, minggu ini, bulan ini, rentang, pinjaman aktif, menunggak). | `app/ui/layar_filter_cepat.py` |
| Laporan Mingguan SP | `laporan_mingguan` (Stack 7) | Terbuka (Tanpa peran) | Rekapitulasi kas dan transaksi mingguan (Senin-Minggu), pencatatan log pengingat, ekspor Excel/PDF. | `app/ui/layar_laporan.py` |
| Laporan Bulanan SP | `laporan_bulanan` (Stack 8) | Terbuka (Tanpa peran) | Rekapitulasi bulanan, arus kas bersih, simpanan per jenis, status closing vs sementara, ekspor. | `app/ui/layar_laporan_bulanan.py` |
| Laporan Tahunan SP | `laporan_tahunan` (Stack 9) | Terbuka (Tanpa peran) | Rekap komparatif 12 bulan simpan pinjam, tren grafik batang kas/jasa, ekspor tahunan. | `app/ui/layar_laporan_tahunan.py` |
| Closing Bulanan SP | `closing_sp` (Stack 10) | Otorisasi PIN Keamanan untuk Reopen | Validasi pra-closing, rekonsiliasi kas, snapshot saldo, kunci periode (`terkunci=1`), buka closing dengan PIN. | `app/ui/layar_closing.py` |
| Impor Data Excel | `impor` (Stack 11) | Terbuka (Tanpa peran) | Unduh template resmi Excel (.xlsx), validasi berkas multi-sheet pra-impor, eksekusi impor atomik. | `app/ui/layar_impor.py` |
| Buku Kas Operasional | `kas` (Stack 12) | Terbuka (Tanpa peran) | Pencatatan transaksi kas manual non-anggota (operasional masuk/keluar), koreksi pembalik kas. | `app/ui/layar_kas.py` |
| Dasbor Unit Toko | `ringkasan_toko` (Stack 13) | Terbuka (Tanpa peran) | Dasbor 6 metrik retail (penjualan hari ini, laba kotor, kas toko, piutang, hutang penitip, peringatan stok). | `app/ui/layar_ringkasan_toko.py` |
| Kasir Penjualan Toko | `penjualan` (Stack 14) | Terbuka (Tanpa peran) | Transaksi kasir penjualan cepat, keranjang belanja, kalkulasi konversi satuan, bayar tunai / kredit. | `app/ui/layar_penjualan.py` |
| Piutang Pembeli | `piutang` (Stack 15) | Terbuka (Tanpa peran) | Daftar debitur toko, monitoring jatuh tempo, terima pembayaran dengan alokasi otomatis FIFO nota tertua. | `app/ui/layar_piutang.py` |
| Penitipan Harian | `penitipan` (Stack 16) | Terbuka (Tanpa peran) | Penerimaan titipan pagi (lot titipan), setoran penyelesaian sore (bayar barang laku + retur/tinggal). | `app/ui/layar_penitipan.py` |
| Master Barang & Satuan | `barang` (Stack 17) | Terbuka (Tanpa peran) | Kelola katalog barang, satuan konversi per-barang bertingkat, proteksi kunci satuan terpakai. | `app/ui/layar_barang.py` |
| Pihak Terkait | `pihak` (Stack 18) | Terbuka (Tanpa peran) | Master data Supplier, Penitip, dan Pembeli (termasuk mapping relasi opsional ke ID Anggota SP). | `app/ui/layar_pihak.py` |
| Pembelian (Barang Masuk) | `pembelian` (Stack 19) | Terbuka (Tanpa peran) | Faktur pembelian multi-baris, snapshot konversi, bayar tunai (kas keluar) atau hutang dagang supplier. | `app/ui/layar_pembelian.py` |
| Daftar Stok FIFO | `stok` (Stack 20) | Terbuka (Tanpa peran) | Pemantauan inventori stok real-time, rincian lot FIFO aktif, verifikasi rekonsiliasi stok. | `app/ui/layar_daftar_stok.py` |
| Kartu Barang | `kartu_barang` (Stack 21) | Terbuka (Tanpa peran) | Riwayat buku mutasi kartu stok per barang, saldo berjalan, analisis pembeli dan supplier utama. | `app/ui/layar_kartu_barang.py` |
| Retur Barang Toko | `retur` (Stack 22) | Terbuka (Tanpa peran) | Retur barang ke supplier (potong hutang/kas masuk), retur penjualan konsumen (kembali kas/potong piutang). | `app/ui/layar_retur_toko.py` |
| Stock Opname Toko | `opname` (Stack 23) | Terbuka (Tanpa peran) | Sesi draft fisik opname, auto-save, finalisasi selisih kurang (potong FIFO) / lebih (lot penyesuaian). | `app/ui/layar_opname_toko.py` |
| Laporan Toko Retail | `laporan_toko` (Stack 24) | Terbuka (Tanpa peran) | Rekapitulasi per barang, rincian transaksi, ringkasan laba/HPP, laporan 12 bulan, barang mati. | `app/ui/layar_laporan_toko.py` |
| Closing Unit Toko | `closing_toko` (Stack 25) | Otorisasi PIN Keamanan untuk Reopen | Validasi pra-closing retail (stok, piutang, opname draft), snapshot persediaan & finansial toko, kunci periode. | `app/ui/layar_closing_toko.py` |

---

## 3. PERAN PENGGUNA (ROLE)

- **Kondisi Implementasi**: **TIDAK DITEMUKAN SISTEM MULTI-USER MAUPUN ROLE-BASED ACCESS CONTROL (RBAC)** di dalam kode.
- **Arsitektur Pengguna**: Sesuai `SPEC.md:17-20`, aplikasi dirancang sebagai aplikasi *single-user desktop* lokal untuk 1 orang operator administrasi (admin/kasir/pengurus menyatu tanpa sesi login).
- **Mekanisme Pembatasan Keamanan yang Ada**:
  1. **PIN Otorisasi Buka Kembali Periode Closing (Reopen)**:
     - Diterapkan pada pembukaan kembali closing simpan pinjam (`app/db/repo_closing.py:35-49`) dan closing toko (`app/db/repo_closing_toko.py:29-35`).
     - Kode verifikasi: Nilai string masukan di-hash menggunakan SHA-256 dan dicocokkan dengan nilai `pin_hash` pada tabel `pengaturan`. Apabila `pin_hash` kosong, kode menetapkan PIN default `'1234'`.
     - Dialog input PIN di antarmuka: `app/ui/layar_closing.py:155` dan `app/ui/layar_closing_toko.py:189`.
  2. **Proteksi Kunci Transaksi (`terkunci = 1`)**:
     - Dilakukan saat transaksi berada dalam periode yang telah berstatus closing tertutup. Operasi insert/pembalik dicegah secara programatik melalui `cek_periode_terkunci()` di `app/db/repo_simpanan.py:15-36`.

---

## 4. SKEMA DATA

Seluruh tabel SQLite dikonstruksi melalui DDL di `app/db/skema.py`, `app/db/skema_toko.py`, dan `app/db/skema_modul15.py`.

### Tabel 1: `pengaturan`
- **Lokasi**: `app/db/skema.py:15-18`
- **Kolom**:
  - `kunci` (TEXT, PRIMARY KEY)
  - `nilai` (TEXT, NOT NULL)

### Tabel 2: `anggota`
- **Lokasi**: `app/db/skema.py:21-34`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `no_anggota` (TEXT, NOT NULL UNIQUE)
  - `nama` (TEXT, NOT NULL)
  - `nik_karyawan` (TEXT, NULL)
  - `unit` (TEXT, NULL)
  - `no_hp` (TEXT, NULL)
  - `alamat` (TEXT, NULL)
  - `tanggal_masuk` (TEXT, NOT NULL)
  - `status` (TEXT, NOT NULL DEFAULT 'aktif', CHECK in ('aktif','keluar'))
  - `tanggal_keluar` (TEXT, NULL)
  - `catatan` (TEXT, NULL)
  - `dibuat_pada` (TEXT, NOT NULL DEFAULT `datetime('now','localtime')`)

### Tabel 3: `simpanan_transaksi`
- **Lokasi**: `app/db/skema.py:38-50`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `anggota_id` (INTEGER, NOT NULL REFERENCES `anggota(id)`)
  - `jenis` (TEXT, NOT NULL CHECK in ('pokok','wajib','sukarela'))
  - `arah` (TEXT, NOT NULL CHECK in ('setor','tarik'))
  - `jumlah` (**[UANG] INTEGER rupiah**, NOT NULL CHECK (`jumlah > 0`))
  - `tanggal` (TEXT, NOT NULL)
  - `keterangan` (TEXT, NULL)
  - `membalik_id` (INTEGER, NULL REFERENCES `simpanan_transaksi(id)`)
  - `periode` (TEXT, NOT NULL, format 'YYYY-MM')
  - `terkunci` (INTEGER, NOT NULL DEFAULT 0)
  - `dibuat_pada` (TEXT, NOT NULL DEFAULT `datetime('now','localtime')`)

### Tabel 4: `produk_pinjaman`
- **Lokasi**: `app/db/skema.py:55-64`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `nama` (TEXT, NOT NULL UNIQUE)
  - `jasa_persen_per_bulan` (REAL, NOT NULL)
  - `tenor_min` (INTEGER, NOT NULL DEFAULT 1)
  - `tenor_maks` (INTEGER, NOT NULL DEFAULT 60)
  - `plafon_maks` (**[UANG] INTEGER rupiah**, NULL)
  - `biaya_admin` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `aktif` (INTEGER, NOT NULL DEFAULT 1)

### Tabel 5: `pinjaman`
- **Lokasi**: `app/db/skema.py:67-83`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `no_pinjaman` (TEXT, NOT NULL UNIQUE)
  - `anggota_id` (INTEGER, NOT NULL REFERENCES `anggota(id)`)
  - `produk_id` (INTEGER, NULL REFERENCES `produk_pinjaman(id)`)
  - `plafon` (**[UANG] INTEGER rupiah**, NOT NULL CHECK (`plafon > 0`))
  - `tenor` (INTEGER, NOT NULL CHECK (`tenor > 0`))
  - `jasa_persen_per_bulan` (REAL, NOT NULL)
  - `biaya_admin` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `tanggal_cair` (TEXT, NULL)
  - `status` (TEXT, NOT NULL DEFAULT 'aktif', CHECK in ('diajukan','aktif','lunas','ditolak','batal'))
  - `tanggal_lunas` (TEXT, NULL)
  - `keperluan` (TEXT, NULL)
  - `periode` (TEXT, NOT NULL)
  - `terkunci` (INTEGER, NOT NULL DEFAULT 0)
  - `dibuat_pada` (TEXT, NOT NULL DEFAULT `datetime('now','localtime')`)

### Tabel 6: `angsuran`
- **Lokasi**: `app/db/skema.py:87-95`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `pinjaman_id` (INTEGER, NOT NULL REFERENCES `pinjaman(id)`)
  - `angsuran_ke` (INTEGER, NOT NULL)
  - `jatuh_tempo` (TEXT, NOT NULL)
  - `pokok` (**[UANG] INTEGER rupiah**, NOT NULL)
  - `jasa` (**[UANG] INTEGER rupiah**, NOT NULL)
  - *Constraint*: `UNIQUE (pinjaman_id, angsuran_ke)`

### Tabel 7: `pembayaran_angsuran`
- **Lokasi**: `app/db/skema.py:99-112`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `pinjaman_id` (INTEGER, NOT NULL REFERENCES `pinjaman(id)`)
  - `angsuran_id` (INTEGER, NULL REFERENCES `angsuran(id)`)
  - `tanggal` (TEXT, NOT NULL)
  - `bayar_pokok` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `bayar_jasa` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `denda` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `keterangan` (TEXT, NULL)
  - `membalik_id` (INTEGER, NULL REFERENCES `pembayaran_angsuran(id)`)
  - `periode` (TEXT, NOT NULL)
  - `terkunci` (INTEGER, NOT NULL DEFAULT 0)
  - `dibuat_pada` (TEXT, NOT NULL DEFAULT `datetime('now','localtime')`)

### Tabel 8: `kas_transaksi` (Buku Kas Simpan Pinjam & Operasional)
- **Lokasi**: `app/db/skema.py:117-129`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `tanggal` (TEXT, NOT NULL)
  - `keterangan` (TEXT, NOT NULL)
  - `masuk` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `keluar` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `sumber` (TEXT, NOT NULL CHECK in ('simpanan','pencairan','angsuran','biaya_admin','manual'))
  - `ref_id` (INTEGER, NULL)
  - `periode` (TEXT, NOT NULL)
  - `terkunci` (INTEGER, NOT NULL DEFAULT 0)
  - `dibuat_pada` (TEXT, NOT NULL DEFAULT `datetime('now','localtime')`)
  - *Constraint*: `CHECK ((masuk > 0 AND keluar = 0) OR (keluar > 0 AND masuk = 0))`

### Tabel 9: `closing`
- **Lokasi**: `app/db/skema.py:133-146`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `periode` (TEXT, NOT NULL UNIQUE)
  - `tanggal_closing` (TEXT, NOT NULL)
  - `saldo_kas_awal` (**[UANG] INTEGER rupiah**, NOT NULL)
  - `total_kas_masuk` (**[UANG] INTEGER rupiah**, NOT NULL)
  - `total_kas_keluar` (**[UANG] INTEGER rupiah**, NOT NULL)
  - `saldo_kas_akhir` (**[UANG] INTEGER rupiah**, NOT NULL)
  - `total_simpanan` (**[UANG] INTEGER rupiah**, NOT NULL)
  - `total_sisa_pokok_pinjaman` (**[UANG] INTEGER rupiah**, NOT NULL)
  - `total_jasa_diterima` (**[UANG] INTEGER rupiah**, NOT NULL)
  - `status` (TEXT, NOT NULL DEFAULT 'tertutup', CHECK in ('tertutup','dibuka_kembali'))
  - `catatan` (TEXT, NULL)

### Tabel 10: `closing_saldo_anggota`
- **Lokasi**: `app/db/skema.py:149-158`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `closing_id` (INTEGER, NOT NULL REFERENCES `closing(id)`)
  - `anggota_id` (INTEGER, NOT NULL REFERENCES `anggota(id)`)
  - `saldo_pokok` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `saldo_wajib` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `saldo_sukarela` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `sisa_pokok_pinjaman` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - *Constraint*: `UNIQUE (closing_id, anggota_id)`

### Tabel 11: `laporan_mingguan_log`
- **Lokasi**: `app/db/skema.py:161-167`
- **Kolom**: `id`, `tanggal_awal`, `tanggal_akhir`, `dibuat_pada` (`UNIQUE(tanggal_awal, tanggal_akhir)`).

### Tabel 12: `draft`
- **Lokasi**: `app/db/skema.py:170-175`
- **Kolom**: `id`, `jenis_form` (TEXT), `data_json` (TEXT), `diperbarui_pada` (TEXT).

### Tabel 13: `log_aktivitas`
- **Lokasi**: `app/db/skema.py:178-185`
- **Kolom**: `id`, `waktu`, `aksi` (TEXT), `tabel` (TEXT), `ref_id` (INTEGER), `detail` (TEXT).

### Tabel 14: `supplier`
- **Lokasi**: `app/db/skema_toko.py:16-24`
- **Kolom**: `id`, `nama` (TEXT NOT NULL), `no_hp`, `alamat`, `catatan`, `aktif` (INTEGER DEFAULT 1), `dibuat_pada`.

### Tabel 15: `penitip`
- **Lokasi**: `app/db/skema_toko.py:28-36`
- **Kolom**: `id`, `nama` (TEXT NOT NULL), `no_hp`, `alamat`, `catatan`, `aktif` (INTEGER DEFAULT 1), `dibuat_pada`.

### Tabel 16: `pembeli`
- **Lokasi**: `app/db/skema_toko.py:40-49`
- **Kolom**: `id`, `nama` (TEXT NOT NULL), `no_hp`, `alamat`, `catatan`, `anggota_id` (INTEGER REFERENCES `anggota(id)`), `aktif` (INTEGER DEFAULT 1), `dibuat_pada`.

### Tabel 17: `barang`
- **Lokasi**: `app/db/skema_toko.py:54-68`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `kode` (TEXT, NOT NULL UNIQUE)
  - `nama` (TEXT, NOT NULL)
  - `kategori` (TEXT, NULL)
  - `satuan_dasar` (TEXT, NOT NULL)
  - `kata_kunci` (TEXT, NULL)
  - `harga_jual` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `jenis_kepemilikan` (TEXT, NOT NULL DEFAULT 'milik_koperasi', CHECK in ('milik_koperasi', 'titipan'))
  - `penitip_id` (INTEGER, NULL REFERENCES `penitip(id)`)
  - `stok_minimum` (**[STOK] INTEGER kuantitas satuan dasar**, NOT NULL DEFAULT 0)
  - `stok_saat_ini` (**[STOK] INTEGER kuantitas satuan dasar (cache)**, NOT NULL DEFAULT 0)
  - `aktif` (INTEGER, NOT NULL DEFAULT 1)
  - `dibuat_pada` (TEXT, NOT NULL DEFAULT `datetime('now','localtime')`)

### Tabel 18: `satuan_barang`
- **Lokasi**: `app/db/skema_toko.py:74-82`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `barang_id` (INTEGER, NOT NULL REFERENCES `barang(id)`)
  - `nama_satuan` (TEXT, NOT NULL)
  - `isi_dalam_satuan_dasar` (**[STOK/KONVERSI] INTEGER**, NOT NULL CHECK (`isi_dalam_satuan_dasar > 0`))
  - `terkunci` (INTEGER, NOT NULL DEFAULT 0)
  - `dibuat_pada` (TEXT)
  - *Constraint*: `UNIQUE (barang_id, nama_satuan)`

### Tabel 19: `kas_toko_transaksi` (Buku Kas Mandiri Unit Toko)
- **Lokasi**: `app/db/skema_toko.py:86-100`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `tanggal` (TEXT, NOT NULL)
  - `keterangan` (TEXT, NOT NULL)
  - `masuk` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `keluar` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `sumber` (TEXT, NOT NULL CHECK in ('modal_awal','pembelian','bayar_hutang','penjualan','bayar_piutang','bayar_penitip','manual'))
  - `ref_tabel` (TEXT, NULL)
  - `ref_id` (INTEGER, NULL)
  - `membalik_id` (INTEGER, NULL REFERENCES `kas_toko_transaksi(id)`)
  - `periode` (TEXT, NOT NULL)
  - `terkunci` (INTEGER, NOT NULL DEFAULT 0)
  - `dibuat_pada` (TEXT)
  - *Constraint*: `CHECK ((masuk > 0 AND keluar = 0) OR (keluar > 0 AND masuk = 0))`

### Tabel 20: `pembelian_faktur`
- **Lokasi**: `app/db/skema_toko.py:104-116`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `no_faktur` (TEXT, NOT NULL UNIQUE)
  - `supplier_id` (INTEGER, NOT NULL REFERENCES `supplier(id)`)
  - `tanggal` (TEXT, NOT NULL)
  - `status_bayar` (TEXT, NOT NULL CHECK in ('tunai', 'belum_dibayar'))
  - `total_biaya` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `keterangan` (TEXT, NULL)
  - `membalik_id` (INTEGER, NULL REFERENCES `pembelian_faktur(id)`)
  - `periode` (TEXT, NOT NULL)
  - `terkunci` (INTEGER, NOT NULL DEFAULT 0)
  - `dibuat_pada` (TEXT)

### Tabel 21: `pembelian_detail`
- **Lokasi**: `app/db/skema_toko.py:121-131`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `faktur_id` (INTEGER, NOT NULL REFERENCES `pembelian_faktur(id)`)
  - `barang_id` (INTEGER, NOT NULL REFERENCES `barang(id)`)
  - `jumlah_input` (**[STOK] INTEGER**, NOT NULL CHECK (`jumlah_input > 0`))
  - `satuan_input` (TEXT, NOT NULL)
  - `isi_per_satuan` (**[STOK] INTEGER**, NOT NULL CHECK (`isi_per_satuan > 0`))
  - `jumlah_dasar` (**[STOK] INTEGER**, NOT NULL CHECK (`jumlah_dasar > 0`))
  - `harga_per_satuan_input` (**[UANG] INTEGER rupiah**, NOT NULL CHECK (`harga_per_satuan_input >= 0`))
  - `total_biaya` (**[UANG] INTEGER rupiah**, NOT NULL CHECK (`total_biaya >= 0`))

### Tabel 22: `pembayaran_hutang_supplier`
- **Lokasi**: `app/db/skema_toko.py:136-146`
- **Kolom**: `id`, `faktur_id` (REFERENCES `pembelian_faktur(id)`), `tanggal`, `jumlah_bayar` (**[UANG] INTEGER > 0**), `keterangan`, `membalik_id`, `periode`, `terkunci`, `dibuat_pada`.

### Tabel 23: `lot_stok` (FIFO Tracking)
- **Lokasi**: `app/db/skema_toko.py:150-165`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `barang_id` (INTEGER, NOT NULL REFERENCES `barang(id)`)
  - `asal` (TEXT, NOT NULL CHECK in ('pembelian', 'titipan', 'penyesuaian', 'koreksi'))
  - `ref_tabel` (TEXT, NULL)
  - `ref_id` (INTEGER, NULL)
  - `tanggal_masuk` (TEXT, NOT NULL)
  - `supplier_id` (INTEGER, NULL REFERENCES `supplier(id)`)
  - `penitip_id` (INTEGER, NULL REFERENCES `penitip(id)`)
  - `qty_awal` (**[STOK] INTEGER**, NOT NULL CHECK (`qty_awal >= 0`))
  - `qty_sisa` (**[STOK] INTEGER**, NOT NULL CHECK (`qty_sisa >= 0`))
  - `total_biaya_awal` (**[UANG] INTEGER rupiah**, NOT NULL CHECK (`total_biaya_awal >= 0`))
  - `biaya_sisa` (**[UANG] INTEGER rupiah**, NOT NULL CHECK (`biaya_sisa >= 0`))
  - `harga_jual_satuan_dasar` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `dibuat_pada` (TEXT)

### Tabel 24: `mutasi_stok` (Append-Only Inventory Ledger)
- **Lokasi**: `app/db/skema_toko.py:169-186`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `barang_id` (INTEGER, NOT NULL REFERENCES `barang(id)`)
  - `lot_id` (INTEGER, NULL REFERENCES `lot_stok(id)`)
  - `tanggal` (TEXT, NOT NULL)
  - `jenis` (TEXT, NOT NULL CHECK in ('masuk', 'keluar_jual', 'retur_supplier', 'retur_penitip', 'rusak', 'hilang', 'kedaluwarsa', 'penyesuaian_opname', 'koreksi'))
  - `qty` (**[STOK] INTEGER**, bertanda positif untuk penambahan atau negatif untuk pengurangan)
  - `biaya` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `ref_tabel` (TEXT, NULL)
  - `ref_id` (INTEGER, NULL)
  - `membalik_id` (INTEGER, NULL REFERENCES `mutasi_stok(id)`)
  - `periode` (TEXT, NOT NULL)
  - `terkunci` (INTEGER, NOT NULL DEFAULT 0)
  - `dibuat_pada` (TEXT)

### Tabel 25: `penitipan`
- **Lokasi**: `app/db/skema_toko.py:191-201`
- **Kolom**: `id`, `penitip_id` (REFERENCES `penitip(id)`), `tanggal`, `status` (CHECK in ('aktif','selesai','dibatalkan')), `catatan`, `membalik_id`, `periode`, `terkunci`, `dibuat_pada`.

### Tabel 26: `penitipan_baris`
- **Lokasi**: `app/db/skema_toko.py:205-217`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `penitipan_id` (INTEGER, NOT NULL REFERENCES `penitipan(id)`)
  - `barang_id` (INTEGER, NOT NULL REFERENCES `barang(id)`)
  - `jumlah_input` (**[STOK] INTEGER**, NOT NULL CHECK (`jumlah_input > 0`))
  - `satuan_input` (TEXT, NOT NULL)
  - `isi_per_satuan` (**[STOK] INTEGER**, NOT NULL CHECK (`isi_per_satuan > 0`))
  - `jumlah_dasar` (**[STOK] INTEGER**, NOT NULL CHECK (`jumlah_dasar > 0`))
  - `harga_titip_satuan_dasar` (**[UANG] INTEGER rupiah**, NOT NULL CHECK (`harga_titip_satuan_dasar >= 0`))
  - `harga_jual_satuan_dasar` (**[UANG] INTEGER rupiah**, NOT NULL CHECK (`harga_jual_satuan_dasar >= 0`))
  - `lot_id` (INTEGER, NULL REFERENCES `lot_stok(id)`)
  - `selesai` (INTEGER, NOT NULL DEFAULT 0)

### Tabel 27: `pembayaran_penitip`
- **Lokasi**: `app/db/skema_toko.py:222-232`
- **Kolom**: `id`, `penitip_id` (REFERENCES `penitip(id)`), `tanggal`, `total_laku_terbayar` (**[UANG] INTEGER rupiah**, DEFAULT 0), `keterangan`, `membalik_id`, `periode`, `terkunci`, `dibuat_pada`.

### Tabel 28: `penyelesaian_titipan_baris`
- **Lokasi**: `app/db/skema_toko.py:236-247`
- **Kolom**: `id`, `pembayaran_penitip_id` (REFERENCES `pembayaran_penitip(id)`), `penitipan_baris_id` (REFERENCES `penitipan_baris(id)`), `lot_id` (REFERENCES `lot_stok(id)`), `qty_terjual` (**[STOK] INTEGER**), `harga_titip` (**[UANG] INTEGER**), `subtotal_bayar` (**[UANG] INTEGER**), `qty_sisa_retur` (**[STOK] INTEGER**), `qty_sisa_tinggal` (**[STOK] INTEGER**), `dibuat_pada`.

### Tabel 29: `penjualan`
- **Lokasi**: `app/db/skema_toko.py:250-265`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `no_nota` (TEXT, NOT NULL UNIQUE)
  - `tanggal` (TEXT, NOT NULL)
  - `pembeli_id` (INTEGER, NOT NULL REFERENCES `pembeli(id)`)
  - `nama_pembeli_nota` (TEXT, NULL)
  - `metode_bayar` (TEXT, NOT NULL CHECK in ('tunai', 'kredit'))
  - `total` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `jatuh_tempo` (TEXT, NULL)
  - `status` (TEXT, NOT NULL DEFAULT 'selesai', CHECK in ('selesai', 'dibatalkan'))
  - `keterangan` (TEXT, NULL)
  - `membalik_id` (INTEGER, NULL REFERENCES `penjualan(id)`)
  - `periode` (TEXT, NOT NULL)
  - `terkunci` (INTEGER, NOT NULL DEFAULT 0)
  - `dibuat_pada` (TEXT)

### Tabel 30: `penjualan_baris`
- **Lokasi**: `app/db/skema_toko.py:270-282`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `penjualan_id` (INTEGER, NOT NULL REFERENCES `penjualan(id)`)
  - `barang_id` (INTEGER, NOT NULL REFERENCES `barang(id)`)
  - `jumlah_input` (**[STOK] INTEGER**, NOT NULL CHECK (`jumlah_input > 0`))
  - `satuan_input` (TEXT, NOT NULL)
  - `isi_per_satuan` (**[STOK] INTEGER**, NOT NULL CHECK (`isi_per_satuan > 0`))
  - `jumlah_dasar` (**[STOK] INTEGER**, NOT NULL CHECK (`jumlah_dasar > 0`))
  - `harga_jual_satuan_dasar` (**[UANG] INTEGER rupiah**, NOT NULL CHECK (`harga_jual_satuan_dasar >= 0`))
  - `total_baris` (**[UANG] INTEGER rupiah**, NOT NULL CHECK (`total_baris >= 0`))
  - `hpp_total` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `laba` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)

### Tabel 31: `penjualan_lot`
- **Lokasi**: `app/db/skema_toko.py:286-293`
- **Kolom**:
  - `id` (INTEGER, PRIMARY KEY AUTOINCREMENT)
  - `penjualan_baris_id` (INTEGER, NOT NULL REFERENCES `penjualan_baris(id)`)
  - `lot_id` (INTEGER, NULL REFERENCES `lot_stok(id)`)
  - `qty` (**[STOK] INTEGER**, NOT NULL CHECK (`qty > 0`))
  - `biaya` (**[UANG] INTEGER rupiah**, NOT NULL DEFAULT 0)
  - `penitip_id` (INTEGER, NULL REFERENCES `penitip(id)`)

### Tabel 32: `pembayaran_piutang`
- **Lokasi**: `app/db/skema_toko.py:298-308`
- **Kolom**: `id`, `pembeli_id` (REFERENCES `pembeli(id)`), `tanggal`, `jumlah` (**[UANG] INTEGER > 0**), `keterangan`, `membalik_id`, `periode`, `terkunci`, `dibuat_pada`.

### Tabel 33: `alokasi_piutang`
- **Lokasi**: `app/db/skema_toko.py:312-319`
- **Kolom**: `id`, `pembayaran_piutang_id` (REFERENCES `pembayaran_piutang(id)`), `penjualan_id` (REFERENCES `penjualan(id)`), `jumlah` (**[UANG] INTEGER > 0**), `membalik_id`, `dibuat_pada`.

### Tabel 34: `retur_supplier`
- **Lokasi**: `app/db/skema_modul15.py:12-26`
- **Kolom**: `id`, `no_retur` (UNIQUE), `tanggal`, `pembelian_faktur_id` (REFERENCES `pembelian_faktur(id)`), `supplier_id` (REFERENCES `supplier(id)`), `total_retur` (**[UANG] INTEGER >= 0**), `jenis_kompensasi` (CHECK in ('potong_hutang', 'kas_masuk')), `kas_toko_transaksi_id` (REFERENCES `kas_toko_transaksi(id)`), `alasan`, `membalik_id`, `periode`, `terkunci`, `dibuat_pada`.

### Tabel 35: `retur_supplier_baris`
- **Lokasi**: `app/db/skema_modul15.py:30-39`
- **Kolom**: `id`, `retur_supplier_id` (REFERENCES `retur_supplier(id)`), `barang_id` (REFERENCES `barang(id)`), `lot_id` (REFERENCES `lot_stok(id)`), `jumlah_dasar` (**[STOK] INTEGER > 0**), `biaya_per_satuan_dasar` (**[UANG] INTEGER >= 0**), `total_biaya` (**[UANG] INTEGER >= 0**), `dibuat_pada`.

### Tabel 36: `retur_penjualan`
- **Lokasi**: `app/db/skema_modul15.py:42-56`
- **Kolom**: `id`, `no_retur` (UNIQUE), `tanggal`, `penjualan_id` (REFERENCES `penjualan(id)`), `pembeli_id` (REFERENCES `pembeli(id)`), `total_retur` (**[UANG] INTEGER >= 0**), `jenis_kompensasi` (CHECK in ('kembali_kas', 'potong_piutang')), `kas_toko_transaksi_id` (REFERENCES `kas_toko_transaksi(id)`), `alasan`, `membalik_id`, `periode`, `terkunci`, `dibuat_pada`.

### Tabel 37: `retur_penjualan_baris`
- **Lokasi**: `app/db/skema_modul15.py:60-72`
- **Kolom**: `id`, `retur_penjualan_id` (REFERENCES `retur_penjualan(id)`), `penjualan_baris_id` (REFERENCES `penjualan_baris(id)`), `barang_id` (REFERENCES `barang(id)`), `lot_id` (REFERENCES `lot_stok(id)`), `jumlah_dasar` (**[STOK] INTEGER > 0**), `harga_jual_satuan_dasar` (**[UANG] INTEGER >= 0**), `total_harga` (**[UANG] INTEGER >= 0**), `hpp_satuan_dasar` (**[UANG] INTEGER DEFAULT 0**), `hpp_total` (**[UANG] INTEGER DEFAULT 0**), `dibuat_pada`.

### Tabel 38: `opname_sesi`
- **Lokasi**: `app/db/skema_modul15.py:75-88`
- **Kolom**: `id`, `kode_opname` (UNIQUE), `tanggal`, `status` (CHECK in ('draft', 'final')), `catatan`, `total_selisih_kurang_qty` (**[STOK] INTEGER**), `total_selisih_kurang_nilai` (**[UANG] INTEGER**), `total_selisih_lebih_qty` (**[STOK] INTEGER**), `total_selisih_lebih_nilai` (**[UANG] INTEGER**), `periode`, `terkunci`, `dibuat_pada`.

### Tabel 39: `opname_barang`
- **Lokasi**: `app/db/skema_modul15.py:90-102`
- **Kolom**: `id`, `opname_sesi_id` (REFERENCES `opname_sesi(id)`), `barang_id` (REFERENCES `barang(id)`), `stok_sistem` (**[STOK] INTEGER**), `stok_fisik` (**[STOK] INTEGER**), `selisih_qty` (**[STOK] INTEGER**), `harga_satuan_dasar` (**[UANG] INTEGER**), `selisih_nilai` (**[UANG] INTEGER**), `catatan`, `dibuat_pada`, `UNIQUE (opname_sesi_id, barang_id)`.

### Tabel 40: `closing_toko`
- **Lokasi**: `app/db/skema_modul15.py:105-125`
- **Kolom**: `id`, `periode` (UNIQUE), `tanggal`, `kas_toko_awal` (**[UANG] INTEGER**), `kas_toko_masuk` (**[UANG] INTEGER**), `kas_toko_keluar` (**[UANG] INTEGER**), `kas_toko_akhir` (**[UANG] INTEGER**), `total_penjualan` (**[UANG] INTEGER**), `total_hpp` (**[UANG] INTEGER**), `laba_kotor` (**[UANG] INTEGER**), `kerugian_persediaan` (**[UANG] INTEGER**), `nilai_persediaan` (**[UANG] INTEGER**), `total_piutang` (**[UANG] INTEGER**), `total_hutang_supplier` (**[UANG] INTEGER**), `total_hutang_penitip` (**[UANG] INTEGER**), `status` (CHECK in ('closed', 'dibuka_kembali')), `catatan`, `dibuat_pada`.

### Tabel 41: `closing_stok_barang`
- **Lokasi**: `app/db/skema_modul15.py:127-135`
- **Kolom**: `id`, `closing_toko_id` (REFERENCES `closing_toko(id)`), `barang_id` (REFERENCES `barang(id)`), `stok_akhir_dasar` (**[STOK] INTEGER**), `nilai_persediaan` (**[UANG] INTEGER**), `dibuat_pada`, `UNIQUE (closing_toko_id, barang_id)`.

### SQL Views (Efektivitas Transaksi Normal vs Pembalik)
- `v_simpanan_efektif` (`app/db/skema.py:188-195`)
- `v_pembayaran_angsuran_efektif` (`app/db/skema.py:197-204`)
- `v_mutasi_stok_efektif` (`app/db/skema_toko.py:323-330`)
- `v_pembelian_faktur_efektif` (`app/db/skema_toko.py:332-339`)
- `v_kas_toko_efektif` (`app/db/skema_toko.py:341-348`)
- `v_penjualan_efektif` (`app/db/skema_toko.py:350-357`)
- `v_penitipan_efektif` (`app/db/skema_toko.py:359-366`)
- `v_pembayaran_piutang_efektif` (`app/db/skema_toko.py:368-375`)
- `v_pembayaran_penitip_efektif` (`app/db/skema_toko.py:377-384`)
- `v_retur_supplier_efektif` (`app/db/skema_modul15.py:139-146`)
- `v_retur_penjualan_efektif` (`app/db/skema_modul15.py:148-155`)

---

## 5. ALUR DATA PER FITUR

### 5.1 Pendaftaran Anggota, Setoran, dan Tarik Simpanan
- **Pendaftaran Anggota** (`app/db/repo_anggota.py:27-80` `tambah_anggota`):
  - *Input*: `nama`, `nik_karyawan`, `unit`, `no_hp`, `alamat`, `tanggal_masuk`, `no_anggota` (opsional, jika kosong di-generate otomatis `A-0001` dst oleh `buat_nomor_anggota_berikutnya`).
  - *Validasi*: `nama` tidak boleh kosong; `no_anggota` harus unik di database.
  - *Tabel ditulis*: `anggota`, `log_aktivitas`.
  - *Tabel tidak berubah*: `simpanan_transaksi`, `kas_transaksi`, `pinjaman`.
- **Setoran & Tarik Simpanan** (`app/db/repo_simpanan.py:67-148` `tambah_transaksi_simpanan`):
  - *Input*: `anggota_id`, `jenis` (`pokok`/`wajib`/`sukarela`), `arah` (`setor`/`tarik`), `jumlah` (integer rupiah > 0), `tanggal` (YYYY-MM-DD), `keterangan`.
  - *Validasi*:
    1. `jenis` wajib in `('pokok', 'wajib', 'sukarela')`.
    2. `arah` wajib in `('setor', 'tarik')`.
    3. `jumlah > 0` dan bilangan bulat.
    4. Periode `tanggal[:7]` belum terkunci di `closing` atau `closing_toko` (`cek_periode_terkunci()`).
    5. Jika `arah == 'tarik'`: `jumlah` tidak boleh melebihi saldo simpanan jenis tersebut (`hitung_saldo_simpanan_anggota()`).
  - *Tabel ditulis (Atomik `with conn`)*:
    1. `simpanan_transaksi`: insert transaksi simpanan baru.
    2. `kas_transaksi`: insert arus kas (`masuk = jumlah` jika setor; `keluar = jumlah` jika tarik, `sumber = 'simpanan'`, `ref_id = simp_id`).
    3. `log_aktivitas`: insert catatan riwayat aksi.
  - *Tabel tidak berubah*: `anggota` (status dan saldo tidak disimpan di tabel anggota), `pinjaman`.

### 5.2 Pengajuan, Persetujuan, Pencairan Pinjaman, dan Jadwal Angsuran
- **Pengajuan Pinjaman** (`app/db/repo_pinjaman.py:49-97` `ajukan_pinjaman`):
  - *Input*: `no_pinjaman`, `anggota_id`, `produk_id`, `plafon`, `tenor`, `jasa_persen_per_bulan`, `biaya_admin`, `tanggal_pengajuan`, `keperluan`.
  - *Validasi*: `no_pinjaman` tidak kosong; `plafon > 0`; `tenor > 0`; status anggota harus `'aktif'`.
  - *Tabel ditulis*: `pinjaman` (status `'diajukan'`, `tanggal_cair` diisi tanggal pengajuan), `log_aktivitas`.
  - *Tabel tidak berubah*: `angsuran` (belum dibuat), `kas_transaksi` (belum keluar kas).
- **Persetujuan & Pencairan Pinjaman** (`app/db/repo_pinjaman.py:99-174` `setujui_dan_cairkan_pinjaman`):
  - *Input*: `pinjaman_id`, `tanggal_cair`.
  - *Validasi*: Pinjaman berstatus `'diajukan'`; status anggota peminjam `'aktif'`; periode `tanggal_cair[:7]` belum closing.
  - *Kalkulasi Jadwal*: Memanggil `hitung_jadwal_angsuran_flat(plafon, tenor, jasa_persen, tanggal_cair)` di `app/logika/angsuran_flat.py`.
  - *Tabel ditulis (Atomik `with conn`)*:
    1. `pinjaman`: update status menjadi `'aktif'`, `tanggal_cair = tanggal_cair`, `periode = tanggal_cair[:7]`.
    2. `angsuran`: insert N baris jadwal (`angsuran_ke`, `jatuh_tempo`, `pokok`, `jasa`).
    3. `kas_transaksi` (Pencairan): insert kas keluar (`keluar = plafon`, `sumber = 'pencairan'`, `ref_id = pinjaman_id`).
    4. `kas_transaksi` (Biaya Admin, jika ada): insert kas masuk (`masuk = biaya_admin`, `sumber = 'biaya_admin'`, `ref_id = pinjaman_id`).
    5. `log_aktivitas`: insert catatan pencairan.
  - *Tabel tidak berubah*: `simpanan_transaksi`.
- **Pembuatan Pinjaman Baru Langsung Cair** (`app/db/repo_pinjaman.py:189-208` `buat_pinjaman_baru`):
  - Menjalankan `ajukan_pinjaman` lalu langsung mengeksekusi `setujui_dan_cairkan_pinjaman` seketika.

### 5.3 Pembayaran Angsuran, Pelunasan, dan Keterlambatan/Denda
- **Pembayaran Angsuran** (`app/db/repo_angsuran.py:140-239` `bayar_angsuran`):
  - *Input*: `pinjaman_id`, `angsuran_id` (spesifik cicilan tenor atau `None` jika pelunasan langsung), `tanggal`, `bayar_pokok`, `bayar_jasa`, `denda`, `keterangan`.
  - *Validasi*:
    1. `bayar_pokok >= 0`, `bayar_jasa >= 0`, `denda >= 0`, total bayar > 0.
    2. Periode `tanggal[:7]` belum closing.
    3. Pinjaman tidak berstatus `'lunas'` atau `'batal'`.
    4. `bayar_pokok` tidak boleh melebihi sisa pokok pinjaman (`hitung_sisa_pokok_pinjaman()`).
  - *Tabel ditulis (Atomik `with conn`)*:
    1. `pembayaran_angsuran`: insert pembayaran (`bayar_pokok`, `bayar_jasa`, `denda`, `angsuran_id`).
    2. `kas_transaksi`: insert arus kas masuk (`masuk = total_bayar`, `sumber = 'angsuran'`, `ref_id = bayar_id`).
    3. `pinjaman`: jika `sisa_pokok_saat_ini - bayar_pokok == 0`, status pinjaman otomatis di-update menjadi `'lunas'`, dan `tanggal_lunas = tanggal`.
    4. `log_aktivitas`: insert catatan pembayaran.
  - *Tabel tidak berubah*: `angsuran` (jadwal tidak diubah; status angsuran dihitung dinamis dari akumulasi `pembayaran_angsuran`).

### 5.4 Penjualan Toko, Pembelian/Restock, Stok, Retur, dan Pembatalan
- **Pembelian / Restock Toko** (`app/db/repo_pembelian.py:27-169` `buat_faktur_pembelian`):
  - *Input*: `no_faktur`, `supplier_id`, `tanggal`, `status_bayar` (`'tunai'`/`'belum_dibayar'`), `items` (`barang_id`, `jumlah_input`, `satuan_input`, `isi_per_satuan`, `harga_per_satuan_input`), `keterangan`.
  - *Validasi*: `no_faktur` unik; periode belum closing; `jumlah_input > 0`; `isi_per_satuan > 0`; `harga_input >= 0`.
  - *Tabel ditulis (Atomik `with conn`)*:
    1. `pembelian_faktur`: insert faktur pembelian.
    2. `pembelian_detail`: insert rincian baris barang beserta snapshot konversi.
    3. `satuan_barang`: update `terkunci = 1` pada satuan yang digunakan (`kunci_satuan_barang_jika_dipakai`).
    4. `lot_stok`: insert lot baru via `tambah_stok_masuk` (`qty_awal = jumlah_dasar`, `qty_sisa = jumlah_dasar`, `total_biaya_awal = total_baris`, `biaya_sisa = total_baris`, `asal = 'pembelian'`).
    5. `mutasi_stok`: insert mutasi stok masuk (`jenis = 'masuk'`, `qty = jumlah_dasar`, `biaya = total_baris`).
    6. `barang`: update cache kolom `stok_saat_ini = stok_saat_ini + jumlah_dasar`.
    7. `kas_toko_transaksi`: jika `status_bayar == 'tunai'`, insert kas keluar (`keluar = total_biaya`, `sumber = 'pembelian'`). Jika `'belum_dibayar'`, kas toko TIDAK ditulis (menjadi hutang supplier).
    8. `log_aktivitas`: insert riwayat pembelian.
  - *Tabel tidak berubah*: `kas_transaksi` (kas unit simpan pinjam terpisah total dari kas toko).
- **Penjualan Kasir Toko** (`app/db/repo_penjualan.py:101-268` `simpan_penjualan`):
  - *Input*: `tanggal`, `pembeli_id`, `metode_bayar` (`'tunai'`/`'kredit'`), `items` (`barang_id`, `jumlah_input`, `satuan_input`, `isi_per_satuan`, `harga_jual_satuan_dasar`), `no_nota`, `nama_pembeli_nota`, `keterangan`.
  - *Validasi*:
    1. `items` tidak kosong; metode in `('tunai', 'kredit')`.
    2. Periode belum closing.
    3. Jika `metode_bayar == 'kredit'`: pembeli tidak boleh pembeli bernama "Umum" (`nama_pembeli.strip().lower() != 'umum'`).
    4. Ketersediaan stok fisik dicek di `kurangi_stok_fifo()`: jika `izinkan_stok_minus == 0` dan stok kurang, transaksi diblokir dengan pesan ramah.
  - *Tabel ditulis (Atomik `with conn`)*:
    1. `penjualan`: insert nota (`metode_bayar`, `jatuh_tempo = tanggal + 1 bulan` jika kredit).
    2. `lot_stok`: pemotongan kuantitas `qty_sisa` dan `biaya_sisa` berbasis FIFO (lot terlama dulu) melalui `kurangi_stok_fifo()`. Sisa biaya diserap habis pada cicilan terakhir lot.
    3. `mutasi_stok`: insert mutasi keluar (`jenis = 'keluar_jual'`, `qty = -jumlah_dasar`, `biaya = HPP lot terpakai`).
    4. `barang`: update cache `stok_saat_ini = stok_saat_ini - jumlah_dasar`.
    5. `penjualan_baris`: insert baris penjualan beserta HPP dan laba baris.
    6. `penjualan_lot`: insert alokasi lot terpakai (menyimpan `lot_id`, `qty`, `biaya`, `penitip_id`).
    7. `kas_toko_transaksi`: jika `metode_bayar == 'tunai'`, insert arus kas masuk (`masuk = total_nota`, `sumber = 'penjualan'`). Jika kredit, kas toko TIDAK ditulis (tercatat sebagai piutang).
    8. `log_aktivitas`: insert catatan penjualan.
  - *Tabel tidak berubah*: `kas_transaksi`, `closing_toko`.
- **Pembayaran Piutang Toko** (`app/db/repo_piutang.py:140-231` `bayar_piutang_pembeli`):
  - *Input*: `pembeli_id`, `tanggal`, `jumlah`, `keterangan`.
  - *Validasi*: `jumlah > 0`; periode belum closing; `jumlah` tidak boleh melebihi total seluruh utang pembeli.
  - *Tabel ditulis (Atomik `with conn`)*:
    1. `pembayaran_piutang`: insert pembayaran piutang.
    2. `alokasi_piutang`: mengalokasikan pembayaran ke nota kredit tertua terlebih dahulu secara otomatis (FIFO nota kredit).
    3. `kas_toko_transaksi`: insert arus kas toko masuk (`masuk = jumlah`, `sumber = 'bayar_piutang'`).
    4. `log_aktivitas`: insert log pembayaran.
  - *Tabel tidak berubah*: `penjualan` (saldo nota kredit dihitung dinamis dari total alokasi piutang efektif).
- **Penitipan Harian & Setoran Sore Penitip** (`app/db/repo_penitipan.py`):
  - *Penitipan Pagi* (`catat_penitipan_harian`): insert `penitipan`, `penitipan_baris`, `lot_stok` (asal `'titipan'`, biaya awal = harga titip * qty), `mutasi_stok` (`jenis = 'masuk'`), update `barang.stok_saat_ini`.
  - *Kewajiban Penitip*: Tercipta secara otomatis saat barang titipan laku terjual di kasir (terekam di `penjualan_lot.penitip_id`).
  - *Setoran Sore* (`selesaikan_setoran_penitip`): insert `pembayaran_penitip`, `penyelesaian_titipan_baris`; potong `kas_toko_transaksi` (`keluar = nominal_bayar`, `sumber = 'bayar_penitip'`); jika sisa barang dipilih `'retur'`, kurangi `lot_stok`, insert `mutasi_stok` (`jenis = 'retur_penitip'`), potong `barang.stok_saat_ini`.
- **Retur Barang Toko** (`app/db/repo_retur_toko.py`):
  - *Retur ke Supplier* (`catat_retur_supplier`): memotong `lot_stok.qty_sisa`, insert `mutasi_stok` (`jenis = 'retur_supplier'`, qty negatif), kurangi `barang.stok_saat_ini`, catat `retur_supplier` & `retur_supplier_baris`. Jika kompensasi `'kas_masuk'`, insert `kas_toko_transaksi` (masuk). Jika `'potong_hutang'`, mengurangi hutang faktur.
  - *Retur Penjualan Konsumen* (`catat_retur_penjualan`): mengembalikan kuantitas ke `lot_stok` asal (dari data `penjualan_lot`) dengan HPP sama persis, insert `mutasi_stok` (`jenis = 'masuk'`, ref `retur_penjualan`), tambah `barang.stok_saat_ini`, catat `retur_penjualan` & `retur_penjualan_baris`. Jika kompensasi `'kembali_kas'`, insert `kas_toko_transaksi` (keluar). Jika `'potong_piutang'`, mengurangi saldo piutang nota kredit.
- **Stock Opname Toko** (`app/db/repo_opname_toko.py`):
  - Draft di-auto-save ke `opname_sesi` & `opname_barang`.
  - Finalisasi (`finalisasi_sesi_opname`):
    - Selisih kurang (`selisih_qty < 0`): potong `lot_stok` FIFO terlama via `kurangi_stok_fifo(jenis_mutasi='penyesuaian_opname')`, dicatat sebagai kerugian persediaan.
    - Selisih lebih (`selisih_qty > 0`): buat lot baru di `lot_stok` via `tambah_stok_masuk(asal='penyesuaian')` dengan harga patokan.
    - Kunci sesi (`status = 'final'`, `terkunci = 1`).

### 5.5 Kas, Pembukuan, dan Jurnal
- **Buku Kas Simpan Pinjam & Operasional** (`kas_transaksi`):
  - Mencatat arus kas masuk dan keluar untuk transaksi unit SP dan operasional manual (`app/db/repo_kas.py:16-56` `tambah_kas_manual`).
  - Constraint ketat: `CHECK ((masuk > 0 AND keluar = 0) OR (keluar > 0 AND masuk = 0))`.
- **Buku Kas Unit Toko** (`kas_toko_transaksi`):
  - Sepenuhnya terpisah dari kas simpan pinjam (`app/db/repo_kas_toko.py:14-49` `tambah_kas_toko`).
  - Arus kas meliputi: modal awal, pembelian tunai, bayar hutang supplier, kasir penjualan tunai, pembayaran piutang, bayar laku penitip, dan manual.
- **Jurnal Akuntansi**:
  - **TIDAK DITEMUKAN BUKU BESAR ATAU JURNAL UMUM DEBET/KREDIT BERPASANGAN (DOUBLE ENTRY)**. Pembukuan berjalan berbasis buku kas tunggal (*single-entry cash ledger*) append-only yang ditopang oleh tabel transaksi pendukung dan rekonsiliasi dinamis.

### 5.6 Laporan Keuangan, Penutupan Periode (Closing), dan SHU
- **Laporan Mingguan SP**: Dihitung dinamis via `app/db/repo_laporan.py:53-106`.
- **Laporan Bulanan SP**: Dihitung dinamis atau membaca snapshot closing jika periode tertutup (`app/db/repo_laporan_periode.py:47-238`).
- **Closing Bulanan SP** (`app/db/repo_closing.py:208-300` `eksekusi_closing_bulanan`):
  1. Validasi pra-closing (rekonsiliasi saldo kas harus cocok 100%).
  2. Backup database otomatis ke folder `backup/`.
  3. Snapshot finansial ke tabel `closing`.
  4. Snapshot saldo simpanan & pinjaman per anggota ke `closing_saldo_anggota`.
  5. Penguncian transaksi: `terkunci = 1` pada `simpanan_transaksi`, `pembayaran_angsuran`, `pinjaman`, `kas_transaksi` untuk periode tersebut.
- **Closing Bulanan Toko** (`app/db/repo_closing_toko.py:124-210` `eksekusi_closing_toko`):
  1. Validasi pra-closing (opname draft harus bersih, setoran penitip selesai, rekonsiliasi stok = mutasi = lot, rekonsiliasi piutang).
  2. Backup database otomatis ke folder `backup/`.
  3. Snapshot finansial toko ke tabel `closing_toko`.
  4. Snapshot kuantitas dan nilai persediaan per barang ke `closing_stok_barang`.
  5. Penguncian transaksi toko: `terkunci = 1` pada 10 tabel transaksi unit toko.
- **Perhitungan & Pembagian Sisa Hasil Usaha (SHU)**:
  - **TIDAK DITEMUKAN FITUR PERHITUNGAN ATAU PEMBAGIAN SHU DI DALAM KODE**. Tidak ada tabel, query, formula, maupun tampilan antarmuka terkait SHU di seluruh basis kode.

### 5.7 Edit / Hapus Transaksi (Mekanisme Koreksi Transaksi Pembalik)
- **Aturan Keuangan Mutlak**: Sesuai `RULES.md` dan implementasi kode, **DILARANG MENGGUNAKAN SQL `DELETE` ATAU `UPDATE` PADA TRANSAKSI KEUANGAN YANG SUDAH TERCATAT**.
- **Koreksi Transaksi Dilakukan Menggunakan Transaksi Pembalik**:
  - *Simpanan*: `app/db/repo_simpanan.py:150-234` `balik_transaksi_simpanan`. Memasukkan baris simpanan baru dengan arah berlawanan, `membalik_id` merujuk ke ID transaksi asli, dan mencatat arus kas lawan di `kas_transaksi`.
  - *Angsuran*: `app/db/repo_angsuran.py:241-336` `balik_pembayaran_angsuran`. Memasukkan baris pembayaran baru dengan `membalik_id` merujuk transaksi asli, mencatat kas keluar (pengembalian uang), dan mengembalikan status pinjaman menjadi `'aktif'`.
  - *Kas Manual*: `app/db/repo_kas.py:86-136` `balik_kas_manual`. Memasukkan baris kas lawan dengan kolom `ref_id` menunjuk kas asli.
  - *Penjualan Toko*: `app/db/repo_penjualan.py:270-399` `batalkan_nota_penjualan`. Menolak pembatalan jika nota kredit sudah pernah dicicil; mengembalikan kuantitas dan biaya ke lot asal FIFO; mencatat mutasi penambah stok jenis `'koreksi'`; mengembalikan kas toko jika tunai; mencatat record pembalik di `penjualan`.
  - *Pembelian Toko*: `app/db/repo_pembelian.py:245-402` `balik_faktur_pembelian`. Membatalkan lot HANYA JIKA lot belum terpakai (`qty_sisa == qty_awal`); jika sudah terpakai sebagian, transaksi ditolak dan diarahkan ke retur; membalik mutasi stok, kas keluar tunai, dan pembayaran hutang.
  - *Piutang Toko*: `app/db/repo_piutang.py:233-289` `balik_pembayaran_piutang`. Membatalkan alokasi piutang, membalik kas masuk, dan menandai pembalik di `pembayaran_piutang`.

---

## 6. KATALOG RUMUS & PERHITUNGAN

### 6.1 Perhitungan Angsuran Pinjaman Flat
- **Lokasi**: `app/logika/angsuran_flat.py:68-95` dalam fungsi `hitung_jadwal_angsuran_flat`
- **Input**: `plafon` (int), `tenor` (int), `jasa_persen_per_bulan` (float), `tanggal_cair_iso` (str).
- **Potongan Kode Salinan Asli**:
  ```python
  # Hitung nilai dasar
  pokok_dasar = plafon // tenor

  # Hitung jasa memakai Decimal dengan pembulatan ROUND_HALF_UP ke integer rupiah
  d_plafon = Decimal(plafon)
  d_persen = Decimal(str(jasa_persen_per_bulan))
  d_jasa = (d_plafon * d_persen / Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
  jasa_dasar = int(d_jasa)

  jadwal: List[Dict[str, Any]] = []
  total_pokok_terhitung = 0

  for ke in range(1, tenor + 1):
      jatuh_tempo = tambah_bulan(tgl_cair, ke)
      
      if ke == tenor:
          # Cicilan terakhir menyerap selisih pembulatan
          pokok_cicilan = plafon - total_pokok_terhitung
      else:
          pokok_cicilan = pokok_dasar
          total_pokok_terhitung += pokok_cicilan

      jadwal.append({
          "angsuran_ke": ke,
          "jatuh_tempo": jatuh_tempo.strftime("%Y-%m-%d"),
          "pokok": pokok_cicilan,
          "jasa": jasa_dasar,
          "total_angsuran": pokok_cicilan + jasa_dasar
      })
  ```
- **Output**: List jadwal angsuran di mana `SUM(pokok) == plafon`.
- **Halaman Penampil**: `DialogPinjamanBaru` (`app/ui/layar_pinjaman.py:101-160`), `LayarKartuAnggota` (`app/ui/layar_kartu_anggota.py:120-140`).

### 6.2 Perhitungan Tanggal Jatuh Tempo Bertambah Bulan
- **Lokasi**: `app/logika/angsuran_flat.py:22-35` dalam fungsi `tambah_bulan`
- **Input**: `tgl_awal` (date), `jumlah_bulan` (int).
- **Potongan Kode Salinan Asli**:
  ```python
  tahun = tgl_awal.year + (tgl_awal.month + jumlah_bulan - 1) // 12
  bulan = (tgl_awal.month + jumlah_bulan - 1) % 12 + 1
  
  # Ambil hari maksimal di bulan target
  _, hari_maksimal = calendar.monthrange(tahun, bulan)
  hari = min(tgl_awal.day, hari_maksimal)
  
  return date(tahun, bulan, hari)
  ```
- **Output**: Tanggal `date` yang disesuaikan jika bulan target memiliki hari lebih sedikit (mis. 31 Jan -> 28/29 Feb).

### 6.3 Perhitungan Status Cicilan Angsuran
- **Lokasi**: `app/db/repo_angsuran.py:19-48` dalam fungsi `hitung_status_angsuran`
- **Input**: `tagihan_pokok`, `tagihan_jasa`, `total_bayar_pokok`, `total_bayar_jasa`, `jatuh_tempo_iso`, `tanggal_patokan_iso`.
- **Potongan Kode Salinan Asli**:
  ```python
  lunas = (total_bayar_pokok >= tagihan_pokok) and (total_bayar_jasa >= tagihan_jasa)
  if lunas:
      return "lunas"

  ada_bayar = (total_bayar_pokok > 0) or (total_bayar_jasa > 0)
  
  tgl_cek = tanggal_patokan_iso or date.today().strftime("%Y-%m-%d")
  lewat_tempo = tgl_cek > jatuh_tempo_iso

  if lewat_tempo:
      return "telat"
  if ada_bayar:
      return "sebagian"
  return "belum"
  ```
- **Output**: String status `'lunas'`, `'telat'`, `'sebagian'`, atau `'belum'`.
- **Halaman Penampil**: `LayarAngsuran`, `LayarKartuAnggota`.

### 6.4 Perhitungan Sisa Pokok Pinjaman
- **Lokasi**: `app/db/repo_angsuran.py:50-73` dalam fungsi `hitung_sisa_pokok_pinjaman`
- **Potongan Kode Salinan Asli**:
  ```python
  cur.execute(
      """
      SELECT COALESCE(SUM(bayar_pokok), 0)
      FROM v_pembayaran_angsuran_efektif
      WHERE pinjaman_id = ? AND status_efektif = 'NORMAL';
      """,
      (pinjaman_id,)
  )
  total_bayar = cur.fetchone()[0]
  sisa = plafon - total_bayar
  return max(0, sisa)
  ```
- **Output**: Integer rupiah sisa pokok yang belum terbayar.
- **Halaman Penampil**: `LayarRingkasan`, `LayarAngsuran`, `LayarKartuAnggota`.

### 6.5 Perhitungan Saldo Simpanan Anggota
- **Lokasi**: `app/db/repo_simpanan.py:39-64` dalam fungsi `hitung_saldo_simpanan_anggota`
- **Potongan Kode Salinan Asli**:
  ```python
  SELECT jenis,
         COALESCE(SUM(CASE WHEN arah = 'setor' THEN jumlah ELSE -jumlah END), 0) AS saldo
  FROM v_simpanan_efektif
  WHERE anggota_id = ? AND status_efektif = 'NORMAL'
  GROUP BY jenis;
  ```
- **Output**: Dict `{"pokok": int, "wajib": int, "sukarela": int, "total": int}`.
- **Halaman Penampil**: `LayarSimpanan`, `LayarKartuAnggota`, `DialogInputSimpanan`.

### 6.6 Perhitungan Alokasi Lot FIFO & Penyerapan Sisa Biaya Stok
- **Lokasi**: `app/layanan/layanan_stok.py:192-205` dalam fungsi `kurangi_stok_fifo`
- **Potongan Kode Salinan Asli**:
  ```python
  # Hitung biaya pemakaian
  if ambil == qty_sisa_lot:
      # Pemakaian terakhir menghabiskan lot -> serap semua sisa biaya tanpa selisih pembulatan
      biaya_ambil = biaya_sisa_lot
  else:
      # Proporsional dari total biaya awal atau sisa biaya
      biaya_ambil = int(round((ambil * lot["total_biaya_awal"]) / lot["qty_awal"]))
      if biaya_ambil > biaya_sisa_lot:
          biaya_ambil = biaya_sisa_lot

  # Update lot_stok
  baru_qty_sisa = qty_sisa_lot - ambil
  baru_biaya_sisa = biaya_sisa_lot - biaya_ambil
  ```
- **Output**: Pengurangan kuantitas dan biaya lot tanpa sisa rupiah pembulatan mengendap.
- **Halaman Penampil**: `LayarPenjualan`, `LayarDaftarStok`, `LayarKartuBarang`.

### 6.7 Perhitungan Laba Kotor & HPP Penjualan Kasir
- **Lokasi**: `app/db/repo_penjualan.py:190-208` dalam fungsi `simpan_penjualan`
- **Potongan Kode Salinan Asli**:
  ```python
  jml_dasar = jml_input * isi_per_satuan
  subtotal_baris = jml_dasar * hrg_jual_satuan
  total_nota += subtotal_baris

  # Eksekusi pengurangan stok FIFO real-time via modul 13
  mutasi_fifo = kurangi_stok_fifo(...)

  # Hitung HPP total dari alokasi lot
  hpp_total = sum(m["biaya"] for m in mutasi_fifo)
  laba_baris = subtotal_baris - hpp_total
  ```
- **Output**: Nilai `total_baris`, `hpp_total`, dan `laba` per item nota.
- **Halaman Penampil**: `LayarPenjualan`, `LayarRingkasanToko`, `LayarLaporanToko`.

### 6.8 Perhitungan Rekapitulasi Kas Bersih (Saling Meniadakan Pembalik Satu Periode)
- **Lokasi**: `app/logika/transaksi_efektif.py:207-270` dalam fungsi `hitung_rekap_kas_bersih_rentang`
- **Potongan Kode Salinan Asli**:
  ```python
  # 1. Jika termasuk pasangan yang ditiadakan dalam rentang yang sama -> lewati
  if r_id in daftar_ditiadakan_pasangan:
      continue

  # 2. Jika merupakan pembalik lintas periode (aslinya di luar rentang)
  if r_id in pembalik_ke_asli:
      jumlah_koreksi_lintas += 1
      if masuk > 0:
          koreksi_masuk_lintas += masuk
          total_kas_masuk += masuk
      else:
          koreksi_keluar_lintas += keluar
          total_kas_keluar += keluar
      continue

  # 3. Transaksi normal atau asli
  if masuk > 0:
      total_kas_masuk += masuk
  else:
      total_kas_keluar += keluar
  ```
- **Output**: `saldo_kas_awal + total_kas_masuk - total_kas_keluar = saldo_kas_akhir`.
- **Halaman Penampil**: `LayarRingkasan`, `LayarLaporan`, `LayarLaporanBulanan`, `LayarClosing`.

---

## 7. STATUS & SIKLUS HIDUP

### 7.1 Anggota (`anggota.status`)
- **Nilai Status**: `'aktif'`, `'keluar'`.
- **Siklus & Pemicu**:
  - Dibuat pertama kali: default `'aktif'` (`app/db/skema.py:30`).
  - Dinonaktifkan: Operator menekan tombol "Set Keluar" di Layar Anggota -> memicu `set_status_anggota(conn, anggota_id, 'keluar', tanggal_keluar)` (`app/db/repo_anggota.py:107-123`).
  - Diaktifkan kembali: Operator menekan tombol "Aktifkan Kembali" -> memicu `set_status_anggota(conn, anggota_id, 'aktif', None)`.

### 7.2 Pinjaman (`pinjaman.status`)
- **Nilai Status**: `'diajukan'`, `'aktif'`, `'lunas'`, `'ditolak'`, `'batal'`.
- **Siklus & Pemicu**:
  - `diajukan`: Operator mengajukan pinjaman melalui dialog pengajuan pinjaman (`app/db/repo_pinjaman.py:49-97` `ajukan_pinjaman`).
  - `diajukan` -> `aktif`: Operator / Pengurus menyetujui pinjaman -> memicu `setujui_dan_cairkan_pinjaman()` (`app/db/repo_pinjaman.py:99-174`). Jadwal cicilan di-generate dan kas dicairkan.
  - `diajukan` -> `ditolak`: Operator / Pengurus menolak pengajuan -> memicu `tolak_pengajuan_pinjaman()` (`app/db/repo_pinjaman.py:176-187`).
  - `aktif` -> `lunas`: Pembayaran angsuran pokok melunasi sisa pokok hingga 0 -> memicu update otomatis di `bayar_angsuran()` (`app/db/repo_angsuran.py:221-226`).
  - `lunas` -> `aktif`: Transaksi pembayaran angsuran terakhir dibalik (koreksi kesalahan) -> memicu pengembalian status pinjaman menjadi `'aktif'` di `balik_pembayaran_angsuran()` (`app/db/repo_angsuran.py:324-327`).
  - `batal`: Status cadangan constraint DDL (`app/db/skema.py:77`).

### 7.3 Cicilan Angsuran (Dihitung Dinamis / Runtime Status)
- **Nilai Status**: `'belum'`, `'sebagian'`, `'lunas'`, `'telat'`.
- **Siklus & Pemicu** (`app/db/repo_angsuran.py:19-48` `hitung_status_angsuran`):
  - `'belum'`: Belum ada pembayaran dan tanggal patokan <= jatuh tempo.
  - `'sebagian'`: Ada pembayaran parsial (pokok > 0 atau jasa > 0), tetapi belum memenuhi tagihan penuh.
  - `'telat'`: Belum lunas penuh dan tanggal patokan > tanggal jatuh tempo cicilan.
  - `'lunas'`: Akumulasi `bayar_pokok >= tagihan_pokok` dan `bayar_jasa >= tagihan_jasa`.

### 7.4 Closing Bulanan SP (`closing.status`)
- **Nilai Status**: `'tertutup'`, `'dibuka_kembali'`.
- **Siklus & Pemicu**:
  - Dibuat saat closing: Operator mengeksekusi closing bulanan -> status `'tertutup'` (`app/db/repo_closing.py:247`).
  - Reopen: Operator membuka kembali closing dengan memasukkan PIN keamanan yang valid -> status berubah menjadi `'dibuka_kembali'` (`app/db/repo_closing.py:333`).

### 7.5 Nota Penjualan Toko (`penjualan.status`)
- **Nilai Status**: `'selesai'`, `'dibatalkan'`.
- **Siklus & Pemicu**:
  - Dibuat saat transaksi kasir: default `'selesai'` (`app/db/skema_toko.py:259`).
  - Dibatalkan: Operator membatalkan nota di Layar Penjualan -> memicu `batalkan_nota_penjualan()` (`app/db/repo_penjualan.py:270-399`). Record pembalik baru dibuat dengan status `'dibatalkan'`.

### 7.6 Penitipan Harian (`penitipan.status` dan `penitipan_baris.selesai`)
- **Nilai Status Penitipan**: `'aktif'`, `'selesai'`, `'dibatalkan'`.
- **Status Baris (`penitipan_baris.selesai`)**: `0` (aktif/belum selesai), `1` (tuntas diselesaikan).
- **Siklus & Pemicu**:
  - Input titipan pagi: `penitipan.status = 'aktif'`, `penitipan_baris.selesai = 0`.
  - Setoran sore: Jika barang laku habis atau sisa barang dipilih diretur fisik, baris diubah menjadi `selesai = 1` (`app/db/repo_penitipan.py:342-344`).

### 7.7 Sesi Stock Opname (`opname_sesi.status`)
- **Nilai Status**: `'draft'`, `'final'`.
- **Siklus & Pemicu**:
  - Dibuat: default `'draft'` (`app/db/repo_opname_toko.py:101`).
  - Finalisasi: Operator mengunci hasil opname fisik -> status menjadi `'final'` dan `terkunci = 1` (`app/db/repo_opname_toko.py:268`).

### 7.8 Closing Toko (`closing_toko.status`)
- **Nilai Status**: `'closed'`, `'dibuka_kembali'`.
- **Siklus & Pemicu**:
  - Dibuat: status `'closed'` (`app/db/repo_closing_toko.py:159`).
  - Reopen: Operator memasukkan PIN keamanan -> status menjadi `'dibuka_kembali'` (`app/db/repo_closing_toko.py:232`).

---

## 8. KONFIGURASI & ATURAN YANG DI-HARDCODE

### 8.1 Nilai Awal Tabel `pengaturan`
Didefinisikan di `app/db/skema.py:207-218` dan dimasukkan saat inisialisasi basis data:
1. `nama_koperasi`: `"Koperasi Simpan Pinjam"`
2. `pin_hash`: `""` (Jika kosong, PIN fallback di kode adalah `'1234'`, lihat `app/db/repo_closing.py:45` dan `app/db/repo_closing_toko.py:34`)
3. `hari_awal_minggu`: `"senin"`
4. `backup_folder_kedua`: `""`
5. `tampilkan_transaksi_dibatalkan`: `"0"`
6. `izinkan_stok_minus`: `"0"` (Default blokir stok minus; dicek di `app/layanan/layanan_stok.py:21-27`)
7. `jatuh_tempo_kredit_bulan`: `"1"` (Offset jatuh tempo piutang default 1 bulan; `app/db/repo_penjualan.py:39`)
8. `format_no_nota`: `"NT-{YYYY}{MM}{DD}-{NO}"` (`app/db/repo_penjualan.py:56`)
9. `batas_piutang_peringatan`: `"0"`
10. `peringatan_piutang_jatuh_tempo`: `"0"`
11. `hari_barang_tidak_bergerak`: `"30"` (`app/db/skema.py:343`)
12. `format_no_retur_supplier`: `"RS-{YYYY}{MM}{DD}-{NO}"` (`app/db/skema.py:344`)
13. `format_no_retur_penjualan`: `"RJ-{YYYY}{MM}{DD}-{NO}"` (`app/db/skema.py:345`)
14. `format_kode_opname`: `"SO-{YYYY}{MM}{DD}-{NO}"` (`app/db/skema.py:346`)

### 8.2 Produk Pinjaman Awal
Didefinisikan di `app/db/skema.py:220-224`:
1. `Pinjaman Reguler`: Jasa `1.5%` per bulan, Tenor 1 s.d. 36 bulan, Plafon Maksimal `Rp 50.000.000`, Biaya Admin `Rp 0`.
2. `Pinjaman Khusus`: Jasa `1.0%` per bulan, Tenor 1 s.d. 60 bulan, Plafon Maksimal `Rp 100.000.000`, Biaya Admin `Rp 0`.

### 8.3 Nilai Default & Batas yang Tertanam di Kode
1. **Maksimal Penyimpanan File Backup**: `MAX_BACKUP_FILES = 30` file (`app/config.py:27`).
2. **Ukuran Rotasi Log Sistem**: Maksimal `5 MB`, cadangan rotasi `3` file (`main.py:21`).
3. **Format Nomor Anggota**: Prefix `A-` dengan angka 4 digit, default awal `A-0001` (`app/db/repo_anggota.py:16-24`).
4. **Format Nomor Pinjaman**: Prefix `P-` dengan angka 4 digit, default awal `P-0001` (`app/db/repo_pinjaman.py:32-47`).
5. **Format Entri Pembeli Default**: Pembeli ID dibuat otomatis bernama `'Umum'` untuk kasir tunai (`app/db/repo_pihak.py:59-71`).
6. **Ambang Hari Barang Mati**: Default `30` hari tanpa transaksi penjualan (`app/db/repo_laporan_toko.py:461`).

---

## 9. KONSISTENSI TRANSAKSI

- **Penggunaan Database Transaction**:
  - Seluruh fungsi repositori yang melakukan penulisan multi-langkah dibungkus menggunakan blok konteks transaksi SQLite bawaan Python: `with conn:`.
  - Contoh pada `app/db/repo_simpanan.py:110`: jika penulisan ke `kas_transaksi` atau `log_aktivitas` gagal, insert ke `simpanan_transaksi` otomatis di-rollback oleh konteks manager SQLite.
  - Contoh pada kasir `app/db/repo_penjualan.py:157`: pengurangan kuantitas lot stok FIFO, penulisan mutasi stok, pembuatan baris nota, alokasi `penjualan_lot`, dan pencatatan kas toko dibungkus dalam 1 blok transaksi atomik (`with conn:`). Jika stok barang ke-3 tidak cukup, pemotongan stok barang ke-1 dan ke-2 otomatis dibatalkan.
- **Log / Jejak Audit**:
  - Disediakan tabel khusus `log_aktivitas` (`app/db/skema.py:178-185`).
  - Seluruh mutasi data penting (tambah anggota, setor/tarik simpanan, pengajuan/cair pinjaman, bayar angsuran, faktur beli, nota jual kasir, retur, opname, closing, dan pembalik) secara konsisten mencatat entri audit dengan format: `(waktu, aksi, tabel, ref_id, detail)`.
- **Penanganan Error di Tengah Proses**:
  - Modul logika dan repositori melempar eksepsi `ValueError` dengan pesan bahasa Indonesia yang deskriptif ketika menemukan ketidakabsahan data atau pelanggaran aturan bisnis (mis. saldo tidak cukup, periode sudah closing, nomor nota duplikat).
  - Lapisan antarmuka pengguna PySide6 menangkap eksepsi tersebut dan menampilkannya kepada pengguna melalui dialog peringatan `QMessageBox.warning(self, "Peringatan", str(e))` tanpa menyebabkan aplikasi crash.

---

## 10. INTEGRASI & DEPENDENSI LUAR

- **Koneksi Jaringan / API Eksternal**:
  - **TIDAK ADA INTEGRASI API EKSTERNAL ATAU JARINGAN**. Aplikasi beroperasi 100% lokal *offline-first*.
- **Cetak & Ekspor Dokumen**:
  1. **Excel (.xlsx)**:
     - Menggunakan pustaka `openpyxl`.
     - Pembuatan template impor resmi 3-sheet (`app/layanan/impor_excel.py:34-108`).
     - Ekspor laporan mingguan SP (`app/layanan/ekspor_excel.py`).
     - Ekspor laporan bulanan dan tahunan SP (`app/layanan/ekspor_laporan_periode.py`).
     - Ekspor laporan toko rekapitulasi barang dan rincian transaksi (`app/layanan/ekspor_laporan_toko.py:17-195`).
  2. **PDF (.pdf)**:
     - Menggunakan pustaka `reportlab`.
     - Cetak bukti tanda terima kuitansi simpanan & pembayaran angsuran format A5 Landscape (`app/layanan/cetak_kuitansi.py`).
     - Ekspor dokumen laporan mingguan SP (`app/layanan/ekspor_pdf.py`).
     - Ekspor dokumen laporan bulanan & tahunan SP (`app/layanan/ekspor_laporan_periode.py`).
     - Ekspor dokumen rekapitulasi dan rincian transaksi unit toko (`app/layanan/ekspor_laporan_toko.py:198-384`).
- **Impor Data**:
  - Membaca file lembar kerja Excel (`.xlsx`) melalui `app/layanan/impor_excel.py:110-392` untuk migrasi data awal anggota, saldo awal simpanan, dan saldo pinjaman berjalan.
- **Tugas Terjadwal (Cron / Scheduler)**:
  - **TIDAK ADA CRON JOB ATAU BACKGROUND SERVICE**.
  - Pemeriksaan dan backup otomatis dipicu oleh event siklus hidup aplikasi:
    1. Backup otomatis saat aplikasi dibuka: dipicu pada fungsi `main()` di `main.py:40`.
    2. Backup otomatis sebelum closing bulanan: dipicu di dalam fungsi `eksekusi_closing_bulanan()` (`app/db/repo_closing.py:233`) dan `eksekusi_closing_toko()` (`app/db/repo_closing_toko.py:142`).
    3. Backup otomatis sebelum eksekusi impor data Excel: dipicu di `app/layanan/impor_excel.py:270`.
    4. Pengingat laporan mingguan & closing bulanan: dihitung saat dasbor dibuka (`app/db/repo_ringkasan.py:48-73`).

---

## 11. PERBEDAAN ANTARA DOKUMEN DAN KODE

| Topik | Dinyatakan di Dokumen (`SPEC.md` / `DATABASE.md`) | Realitas Implementasi di Kode Sumber |
|---|---|---|
| **Perhitungan & Pembagian SHU** | Sering diasosiasikan dengan siklus tahunan koperasi pada dokumen spesifikasi umum. | **TIDAK DITEMUKAN DI KODE**. Tidak ada modul, rumus, tabel, maupun menu terkait SHU di seluruh kode. |
| **Pemisahan Pengguna & Login** | `SPEC.md:116` menyebutkan: *"PIN/password masuk aplikasi (opsional, bisa diatur)"*. | **TIDAK ADA LOGIN SCREEN**. Aplikasi langsung membuka `JendelaUtama` tanpa autentikasi saat startup. PIN hanya diterapkan saat pembukaan kembali periode closing yang terkunci (*reopen*). |
| **Status Pinjaman** | `DATABASE.md` awal hanya mencantumkan status `'aktif'` dan `'lunas'`. | Skema database dimigrasi ke Versi 2 (`app/db/skema.py:260-286`) dengan penambahan status `'diajukan'`, `'ditolak'`, dan `'batal'` untuk mendukung workflow persetujuan rapat pengurus. |
| **Kompensasi Retur Supplier** | Dokumen awal perencanaan toko hanya mencatat pengurangan hutang. | Kode `app/db/skema_modul15.py:19` dan `app/db/repo_retur_toko.py:58` mendukung dua opsi kompensasi: `'potong_hutang'` atau `'kas_masuk'` (pengembalian uang kas langsung dari supplier). |
| **Perlakuan Sisa Barang Titipan** | Dokumen awal hanya mengasumsikan retur fisik sore hari. | Kode `app/db/repo_penitipan.py:242` mendukung dua opsi tindakan sisa barang titipan saat setoran sore: `'retur'` (stok dikembalikan dan lot dikosongkan) atau `'tinggal'` (stok tetap berada di toko untuk dijual hari berikutnya). |
| **Peringatan Saldo Kas Negatif** | Dokumen awal melarang keras saldo kas minus. | Pada kasir retail dan pembayaran penitip sore hari, jika uang kas laci fisik kurang, kode menampilkan dialog konfirmasi persetujuan kas minus ramah pengguna agar transaksi operasional nyata tidak macet (`app/ui/layar_penitipan.py:344-350`). |

---

## 12. CATATAN MENTAH

Catatan observasi faktual saat penelusuran kode sumber tanpa kesimpulan:
1. `app/db/skema.py:209`: Kunci `pin_hash` di tabel `pengaturan` diinisialisasi dengan string kosong `""`. Fungsi `cek_pin_closing` di `app/db/repo_closing.py:45` dan `_verifikasi_pin_keamanan` di `app/db/repo_closing_toko.py:34` secara eksplisit memeriksa: jika `pin_hash` kosong di database, string masukan dibandingkan langsung dengan teks mentah `"1234"`.
2. `app/db/repo_penjualan.py:148`: Pada transaksi kasir kredit (penjualan tempo/hutang), kode memeriksa `nama_pembeli.strip().lower() == "umum"`. Jika bernilai True, kode melempar `ValueError("Penjualan KREDIT (ngutang) mewajibkan memilih pembeli bernama (bukan 'Umum').")`.
3. `app/db/repo_penitipan.py:60`: Pada pencatatan penitipan harian, kode memeriksa apakah barang berjenis kepemilikan `'titipan'` dan apakah `penitip_id` pada tabel `barang` cocok dengan ID penitip yang sedang bertransaksi. Jika tidak cocok, transaksi ditolak.
4. `app/db/repo_pembelian.py:294-301`: Pembalikan faktur pembelian ditolak jika lot stok yang terbentuk dari detail faktur tersebut sudah terpakai sebagian (`qty_sisa < qty_awal`), dengan pesan yang mengarahkan pengguna untuk menggunakan fitur retur pembelian atau penyesuaian opname.
5. `app/db/repo_penjualan.py:313-317`: Pembatalan nota penjualan kredit ditolak jika nota kredit tersebut sudah pernah menerima pembayaran cicilan piutang (`alokasi_piutang > 0`). Pengguna diharuskan membatalkan pembayaran piutang terkait terlebih dahulu.
6. `app/db/repo_opname_toko.py:148-157`: Pada penentuan harga satuan patokan barang saat stock opname, query mengambil harga beli satuan dari pembelian terakhir (`pembelian_detail JOIN pembelian_faktur ORDER BY tanggal DESC, id DESC LIMIT 1`). Jika barang belum pernah dibeli (misal saldo awal/titipan tanpa riwayat faktur beli), harga patokan bernilai `0`.
7. `app/db/repo_simpanan.py:91-98`: Pengecekan saldo simpanan saat penarikan dilakukan per jenis simpanan (`pokok`, `wajib`, atau `sukarela`). Penarikan simpanan pokok atau wajib tidak dapat mengambil jatah saldo sukarela dan sebaliknya.
8. `app/logika/transaksi_efektif.py:207-210`: Pada perhitungan buku kas bersih rentang periode, jika transaksi asli dan transaksi pembaliknya sama-sama berada di dalam rentang periode yang dihitung, kedua baris transaksi tersebut dikeluarkan dari penjumlahan arus kas (`continue`) agar saling meniadakan secara bersih.

---

## 13. KETERBATASAN DOKUMEN INI

1. Dokumen ini mendeskripsikan struktur dan logika kode pada branch kerja lokal saat ini. Perubahan kode di masa depan atau file skrip migrasi yang belum dijalankan berada di luar cakupan dokumen ini.
2. Deskripsi antarmuka grafis (UI) difokuskan pada pemetaan rute halaman, dialog input, dan keterhubungannya dengan logika repositori database, tanpa merinci tata letak piksel visual atau lembar gaya QSS secara mendalam.
3. Seluruh 76 pengujian unit otomatis (`pytest`) berstatus lolos (`PASSED`), yang mengonfirmasi bahwa seluruh alur kalkulasi matematis uang dan stok yang didokumentasikan di atas telah terverifikasi secara fungsional.

---
*Dokumen ini selesai disusun secara komprehensif berdasarkan inspeksi langsung seluruh kode sumber aplikasi.*
