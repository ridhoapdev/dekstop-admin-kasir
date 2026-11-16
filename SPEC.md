# SPEC.md — Aplikasi Administrasi Simpan Pinjam Koperasi

> Baca file ini PERTAMA sebelum mengerjakan apa pun. Lihat juga `RULES.md`, `DATABASE.md`, `PROGRESS.md`.

## 1. Tujuan

Aplikasi desktop Windows untuk SATU pengguna (admin koperasi simpan pinjam karyawan) yang menggantikan tumpukan file Excel.
Pengguna tidak paham teknis, mudah lupa, dan hanya mau **klik 2x lalu langsung jalan**.

Masalah yang diselesaikan:
- Data tersebar di banyak file Excel (per sesi / per bulan), sulit dicari.
- Input ulang berkali-kali, rawan salah.
- Laporan mingguan dan closing bulanan dihitung manual.

## 2. Pengguna & Lingkungan

- Pengguna: 1 orang admin, usia dewasa, awam teknologi, bahasa Indonesia.
- PC: Windows 10 Pro 64-bit, Intel Core i3-3220, **RAM 4 GB**, tanpa internet wajib.
- Berjalan 100% lokal, tanpa server, tanpa hosting, tanpa instalasi database.
- Tidak ada akun online, tidak ada pengiriman data keluar.

## 3. Aturan Bisnis (sudah dikonfirmasi pengguna)

| Hal | Aturan |
|---|---|
| Jasa pinjaman | **Flat**: jasa dihitung dari plafon awal, sama setiap bulan |
| Simpanan | **Disetor langsung** oleh anggota ke koperasi (BUKAN potong gaji) |
| Laporan | **Mingguan** + **Closing akhir bulan** |

### Rumus angsuran flat
```
pokok_per_bulan = plafon / tenor
jasa_per_bulan  = plafon x persen_jasa_per_bulan
angsuran        = pokok_per_bulan + jasa_per_bulan
```
- Semua uang disimpan sebagai **bilangan bulat rupiah** (tanpa desimal).
- Pembulatan: selisih sisa ditanggung **angsuran terakhir** agar total pokok pas = plafon.
- `persen_jasa_per_bulan` DAPAT DIATUR per produk pinjaman (lihat tabel `produk_pinjaman`). Jangan hardcode.

### ASUMSI (belum dikonfirmasi — buat bisa diubah lewat menu Pengaturan)
- Jenis simpanan: Pokok, Wajib, Sukarela.
- Denda keterlambatan: default TIDAK ada (opsi bisa diaktifkan nanti).
- Pelunasan dipercepat: bayar sisa pokok + jasa bulan berjalan (aturan bisa diubah).
- Ada biaya admin pencairan: default 0, bisa diatur.
- Tanggal jatuh tempo angsuran = tanggal cair + n bulan.

## 4. Fitur

### 4.1 Layar Ringkasan (halaman awal)
Kotak besar berisi:
- Simpanan masuk hari ini
- Angsuran masuk hari ini
- Pinjaman cair hari ini
- Posisi kas saat ini
- Angsuran jatuh tempo minggu ini (jumlah + tombol lihat)
- Anggota menunggak (jumlah + tombol lihat)
- **Pengingat**: "Laporan mingguan belum dibuat", "Closing bulan ini belum dilakukan"
- Tombol besar: Input Simpanan, Input Angsuran, Pinjaman Baru, Cari Anggota, Laporan, Closing

### 4.2 Data Anggota
- Tambah/ubah/nonaktifkan anggota (tidak ada hapus permanen jika sudah punya transaksi).
- Field: no_anggota, nama, NIK karyawan, unit/bagian, no HP, alamat singkat, tanggal masuk, status (aktif/keluar).

### 4.3 Simpanan
- Input setoran/penarikan: pilih anggota, jenis, jumlah, tanggal, keterangan.
- Saldo dihitung otomatis dari transaksi.
- Koreksi kesalahan = transaksi pembalik (lihat RULES), bukan edit/hapus bebas.

### 4.4 Pinjaman
- Pinjaman baru: pilih anggota, produk, plafon, tenor, tanggal cair.
- Aplikasi langsung membuat **jadwal angsuran** otomatis dan menampilkan pratinjau sebelum disimpan.
- Satu anggota boleh punya lebih dari satu pinjaman aktif (aturan pembatasan bisa diatur).

### 4.5 Angsuran
- Input pembayaran: pilih pinjaman/anggota, aplikasi menampilkan angsuran berikutnya yang harus dibayar, jumlah terisi otomatis.
- Mendukung bayar sebagian dan pelunasan dipercepat.
- Status per angsuran: belum, lunas, sebagian, telat.

### 4.6 Pencarian (PRIORITAS TINGGI)
**A. Kotak cari global** di bagian atas semua layar. Ketik nama / no anggota / no pinjaman, hasil muncul langsung saat mengetik (toleran salah ketik ringan, tidak peka huruf besar-kecil).

**B. Kartu Anggota** (hasil klik pencarian), satu layar berisi:
- Data diri
- Saldo simpanan per jenis + total
- Pinjaman aktif: plafon, sisa pokok, angsuran ke-berapa, jatuh tempo berikutnya, tunggakan
- Riwayat seluruh transaksi urut tanggal, dengan filter

**C. Tombol filter cepat** (tanpa mengetik):
Hari ini | Minggu ini | Bulan ini | Pilih tanggal | Pinjaman aktif | Menunggak.
Hasil berupa tabel + baris total + tombol **Ekspor Excel** dan **Cetak**.

### 4.7 Laporan Mingguan
- Pilih minggu (default minggu berjalan, Senin–Minggu; hari awal bisa diatur).
- Isi: total simpanan masuk/keluar, angsuran pokok & jasa masuk, pinjaman cair, kas masuk/keluar, saldo kas awal & akhir, daftar transaksi rinci.
- Ekspor ke Excel (.xlsx) dan PDF.
- Mencatat tanggal terakhir laporan dibuat (untuk pengingat).

### 4.8 Closing Akhir Bulan
Alur:
1. Pengguna klik **Closing Bulan Ini**.
2. Aplikasi menjalankan **pemeriksaan**: ada angsuran tanpa tanggal bayar yang sudah lewat? ada input draft belum selesai? saldo kas cocok dengan jumlah transaksi?
3. Tampilkan **ringkasan closing** untuk dikonfirmasi.
4. **Backup otomatis** sebelum closing.
5. Simpan snapshot: saldo akhir simpanan, sisa pokok pinjaman, saldo kas, total jasa diterima.
6. **Kunci** semua transaksi periode itu (tidak bisa diubah).
7. Saldo akhir menjadi saldo awal bulan berikutnya.

Membuka kembali periode terkunci: hanya lewat menu khusus dengan PIN/password, tercatat di log aktivitas.

### 4.9 Impor Excel
- Impor data lama (anggota, saldo simpanan awal, pinjaman berjalan) dari file Excel/CSV.
- Ada langkah **pratinjau & validasi** sebelum benar-benar masuk, laporan baris yang bermasalah.
- Format kolom ditentukan nanti setelah ada contoh Excel asli; sediakan template yang bisa diunduh.

### 4.10 Keamanan & Keandalan
- PIN/password masuk aplikasi (opsional, bisa diatur).
- **Log aktivitas**: siapa/apa/kapan untuk setiap perubahan.
- Konfirmasi sebelum aksi berisiko.
- Backup otomatis (detail di `RULES.md`).
- Draft otomatis dan memori posisi terakhir (detail di `RULES.md`).

### 4.11 Fondasi Unit Toko (Modul 13)
- **Master Data**:
  - `barang`: kode, nama, kategori, satuan_dasar, kata_kunci, harga_jual default, jenis_kepemilikan (`milik_koperasi` / `titipan`), penitip_id, stok_minimum, stok_saat_ini (cache), aktif. Tanpa hapus permanen jika sudah ada transaksi.
  - `satuan_barang`: Konversi melekat per barang (Dilarang tabel konversi global). Kolom: barang_id, nama_satuan, isi_dalam_satuan_dasar (integer > 0). Otomatis terkunci jika sudah pernah dipakai transaksi.
  - Pihak Terkait: `supplier`, `penitip`, `pembeli` (nama, no_hp, alamat, catatan, aktif).
  - Peringatan nama mirip (fuzzy match) saat menambah entitas baru.
  - Pencarian barang toleran huruf besar-kecil dan kata kunci / kode / nama.
- **Pembelian (Barang Masuk)**:
  - Faktur multi-baris: no_faktur, supplier_id, tanggal, status_bayar (`tunai` / `belum_dibayar`).
  - Baris menyimpan snapshot konversi: jumlah_input, satuan_input, isi_per_satuan, jumlah_dasar, harga_per_satuan_input, total_biaya.
  - Tampilan live konversi ("3 dus = 60 pcs") dan total biaya.
  - Hutang dagang supplier dan pencatatan pelunasan / cicilan via kas toko.
- **Stok FIFO Real-Time & Kas Toko**:
  - `lot_stok`: barang_id, asal, ref_tabel, ref_id, tanggal_masuk, supplier_id/penitip_id, qty_awal, qty_sisa, total_biaya_awal, biaya_sisa. Urut pemakaian selalu tanggal masuk terlama (FIFO) lalu id terkecil.
  - `mutasi_stok`: append-only (masuk, keluar_jual, retur_supplier, retur_penitip, rusak, hilang, kedaluwarsa, penyesuaian_opname, koreksi).
  - Kas Toko Mandiri: `kas_toko_transaksi` TERPISAH dari kas simpan pinjam.
  - Pembulatan: selisih sisa diserap pada pemakaian terakhir lot.
  - Satu fungsi layanan tunggal `app/layanan/layanan_stok.py` untuk perubahan stok.
  - Rekonsiliasi stok: `stok_saat_ini == SUM(mutasi) == SUM(qty_sisa lot)`.
  - Opsi stok minus (default blokir; jika diizinkan, restock menutup minus).
  - Pembalik pembelian: hanya jika lot belum terpakai.

### 4.12 Modul 14: Penjualan Kasir, Piutang Pembeli, dan Titipan Harian (Unit Toko)
- **Master Pembeli**:
  - Kolom: nama, no_hp, alamat, catatan, relasi opsional `anggota_id` (hubungan ke anggota simpan pinjam).
  - Pembeli default "Umum" untuk transaksi tunai.
  - Penjualan kredit mewajibkan pembeli terdaftar (bukan "Umum").
  - Pengaturan peringatan batas utang pembeli dan peringatan nota jatuh tempo (hanya peringatan ramah, tanpa memblokir).
- **Kasir Penjualan Cepat**:
  - Input cepat keyboard-friendly (pencarian nama/kode/kata kunci, Enter masukkan keranjang, Tab pindah kolom).
  - Menampilkan konversi satuan langsung, sisa stok, subtotal, dan total.
  - Tombol aksi besar **TUNAI** dan **KREDIT**.
  - Tunai: menampilkan kolom uang diterima dan kembalian, langsung mencatat kas toko masuk.
  - Kredit: tidak menulis kas toko, otomatis membuat piutang dengan tanggal jatuh tempo (+1 bulan default).
  - Berkurang stok secara atomik real-time menggunakan layanan stok FIFO Modul 13 dengan pencatatan `penjualan_lot` untuk presisi pembalik.
  - Pembalik nota: mengembalikan stok ke lot asal, membalik kas masuk / piutang, dan membalik kewajiban penitip.
- **Piutang Pembeli**:
  - Alokasi pembayaran piutang otomatis ke nota kredit tertua terlebih dahulu (FIFO).
  - Pembayaran piutang mencatat arus kas toko masuk.
  - Layar daftar pembeli, saldo utang, status jatuh tempo, rincian nota kredit, dan tombol "Terima Pembayaran".
- **Titipan Harian**:
  - Lot penitipan harian fleksibel (harga titip dan harga jual dicatat per penitipan dan per hari).
  - Barang titipan terikat ke 1 penitip, nama barang otomatis menyertakan nama penitip.
  - Kewajiban ke penitip tercipta saat laku (terjual), baik tunai maupun kredit.
  - Layar setoran sore hari: pembayaran hasil laku (kas toko keluar, konfirmasi kas minus jika perlu), dan opsi tindakan sisa barang (retur fisik atau tetap tinggal di toko).
- **Dasbor Ringkasan Toko**:
  - 6 kartu metrik: Penjualan Hari Ini, Laba Kotor Hari Ini, Posisi Kas Toko Saat Ini, Total Piutang Pembeli, Hutang ke Penitip Hari Ini, dan Perhatian/Peringatan (nota telat & stok menipis).
  - Tombol aksi cepat besar menuju Kasir, Piutang, Penitipan, Pembelian, dan Stok.

### 4.13 Modul 15: Kartu Barang dan Pencarian Global, Retur, Stock Opname, Laporan Toko, dan Closing Toko
- **Pencarian Cepat Global & Kartu Terpadu**:
  - Pencarian cepat di bagian atas menemukan Barang, Supplier, Penitip, Pembeli dengan label jenis jelas.
  - Kartu Barang: info dasar, stok dasar + representasi satuan besar ("47 pcs = 2 dus + 7 pcs"), nilai persediaan, urutan lot FIFO aktif, laba per periode, riwayat kartu stok dengan saldo berjalan, supplier terakhir, pembeli terbanyak, tombol cepat tambah stok / rusak / ubah harga.
  - Kartu Supplier, Penitip, Pembeli: hutang dagang, barang titipan & laba koperasi, utang pembeli & nota jatuh tempo.
  - Kartu Anggota SP menampilkan ringkasan utang toko secara terpisah (tidak mencemari saldo simpan pinjam).
- **Transaksi Retur**:
  - Retur ke supplier: validasi sisa lot stok, memotong hutang atau kas masuk.
  - Retur penjualan: mengembalikan kuantitas ke lot asal FIFO dengan biaya sama persis, pengembalian uang atau pemotongan piutang.
  - Validasi ketat: retur tidak boleh melebihi sisa lot atau kuantitas faktur/nota asal.
- **Penyesuaian Manual & Stock Opname**:
  - Rusak, hilang, kedaluwarsa memotong lot FIFO terlama dan diakui sebagai kerugian persediaan.
  - Sesi stock opname berkala dengan fitur auto-save draft.
  - Finalisasi opname: selisih kurang memotong lot FIFO terlama (kerugian persediaan), selisih lebih membentuk lot baru asal penyesuaian. Mengunci sesi permanen.
- **Laporan Toko Komprehensif**:
  - Rekapitulasi per barang: stok awal dihitung dinamis dari SUM mutasi sebelum periode, stok awal + masuk - keluar +/- penyesuaian = stok akhir. Total penjualan, HPP, laba kotor, margin %.
  - Rincian transaksi, laporan tahunan 12 bulan (gabungan snapshot closing vs sementara), laporan barang tidak bergerak (> 30 hari), dan stok menipis.
  - Ekspor Excel (.xlsx) dengan formula/angka asli dan PDF (.pdf) rapi.
- **Closing Toko Bulanan**:
  - Terpisah dari closing simpan pinjam.
  - Pemeriksaan pra-closing ketat (opname draft, setoran penitip aktif, rekonsiliasi stok = mutasi = lot, rekonsiliasi piutang, kas toko).
  - Snapshot finansial dan persediaan barang per periode, mengunci seluruh transaksi toko pada periode tersebut.
  - Pembukaan kembali closing (reopen) hanya dengan otorisasi PIN keamanan.

## 5. Prinsip Tampilan

- Bahasa Indonesia, istilah koperasi yang lazim (bukan istilah teknis).
- Font besar (min. 12–14 pt), tombol besar, kontras jelas.
- Maksimal 2 klik dari layar Ringkasan ke aksi utama.
- Format uang: `Rp 1.250.000`; format tanggal: `14 Nov 2026`.
- Input dioptimalkan untuk keyboard: Tab/Enter berpindah kolom, Enter menyimpan.
- Pesan error ramah, tanpa kode teknis. Contoh: "Jumlah angsuran belum diisi."

## 6. Di Luar Cakupan (jangan dibuat dulu)

- Multi-pengguna / jaringan, aplikasi web, mobile.
- Integrasi sistem Astra / payroll / bank.
- Notifikasi WhatsApp/email.
- Pembukuan akuntansi lengkap (jurnal umum, neraca).

## 7. Urutan Pengerjaan (satu modul per sesi)

1. Kerangka aplikasi + database + backup otomatis
2. Data Anggota
3. Simpanan
4. Pinjaman + jadwal angsuran (flat)
5. Angsuran / pembayaran
6. Pencarian global + Kartu Anggota + filter cepat
7. Layar Ringkasan + pengingat
8. Laporan mingguan + ekspor
9. Closing bulanan + kunci periode
10. Impor Excel
11. Pengemasan `.exe` + uji di PC i3/4GB
12. Demo & kumpulkan masukan
13. Fondasi Unit Toko (barang, satuan, pihak, pembelian, stok FIFO real-time)
14. Penjualan Kasir, Piutang Pembeli, dan Titipan Harian (Unit Toko)
15. Kartu Barang dan Pencarian Global, Retur, Stock Opname, Laporan Toko, dan Closing Toko

Setiap modul selesai harus: berjalan, ada tes dasar untuk perhitungan uang, dan `PROGRESS.md` diperbarui.

