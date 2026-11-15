# PROGRESS.md — Catatan Progres

> Agent: perbarui file ini setiap selesai satu tahap. Tulis singkat dan jujur (apa yang BELUM beres juga ditulis).

## Status Saat Ini

- Tahap berjalan: **Perbaikan Bug Kritis Transaksi Pembalik & Redesain UI Tuntas**
- Terakhir diperbarui: 14 Nov 2026

## Keputusan yang Sudah Final

| Tanggal | Keputusan |
|---|---|
| 14 Nov 2026 | Aplikasi desktop lokal, Python + PySide6 + SQLite, dikemas PyInstaller (onedir) |
| 14 Nov 2026 | Target PC: Win10 64-bit, i3-3220, RAM 4 GB |
| 14 Nov 2026 | Jasa pinjaman **flat** (dikonfirmasi pengguna) |
| 14 Nov 2026 | Simpanan **disetor langsung**, bukan potong gaji (dikonfirmasi pengguna) |
| 14 Nov 2026 | Ada laporan mingguan + closing akhir bulan (periode terkunci setelah closing) |
| 14 Nov 2026 | Backup otomatis saat buka/tutup + sebelum closing; tanpa tindakan pengguna |
| 14 Nov 2026 | Modul 1: Inisialisasi skema lengkap, PRAGMA WAL/synchronous/FK, backup online via SQLite API dengan rotasi 30 file |
| 14 Nov 2026 | Modul 2: Repositori anggota (CRUD, penomoran otomatis A-xxxx, proteksi hapus, filter, pagination, log aktivitas) & Layar Anggota PySide6 |
| 14 Nov 2026 | Modul 3: Repositori simpanan (setor/tarik, hitung saldo murni SUM, penulisan kas otomatis, transaksi pembalik koreksi, proteksi periode closing) & Layar Simpanan PySide6 |
| 14 Nov 2026 | Modul 4: Logika flat murni & pembulatan cicilan terakhir, kalkulasi jatuh tempo akhir bulan, repositori pinjaman atomik, form pratinjau & UI Layar Pinjaman |
| 14 Nov 2026 | Modul 5: Repositori angsuran (status cicilan, sisa pokok, bayar sebagian, pelunasan dipercepat, kas masuk otomatis, update status lunas pinjaman, pembalik koreksi), Form & Layar Angsuran PySide6 |
| 14 Nov 2026 | Modul 6: Pencarian global instan di bagian atas seluruh layar, Layar Kartu Anggota (profil, saldo, pinjaman aktif, tunggakan, riwayat transaksi gabungan), Layar Filter Cepat (6 mode) + Ekspor Excel openpyxl |
| 14 Nov 2026 | Modul 7: Layar Ringkasan (Dashboard Halaman Awal) dengan 4 kotak besar (simpanan, angsuran, pinjaman cair, posisi kas), dialog jatuh tempo minggu ini, dialog anggota menunggak, banner pengingat laporan mingguan & closing, serta tombol aksi cepat besar |
| 14 Nov 2026 | Modul 8: Repositori Laporan Mingguan (rentang Senin-Minggu, saldo awal, simpanan, angsuran, pencairan, arus kas masuk/keluar, saldo akhir), Layar Laporan PySide6, Ekspor Excel openpyxl dan Ekspor PDF reportlab |
| 14 Nov 2026 | Modul 9: Repositori Closing Bulanan (pemeriksaan pra-closing, backup otomatis, snapshot di tabel closing & closing_saldo_anggota, kunci transaksi terkunci=1, pembukaan kembali dengan PIN), UI Layar Closing PySide6 |
| 14 Nov 2026 | Modul 10: Layanan Impor Excel (template resmi 3 sheet: Anggota, Saldo Simpanan Awal, Pinjaman Berjalan; validasi ketat dan deteksi baris error; backup otomatis sebelum penulisan), UI Layar Impor PySide6 |
| 14 Nov 2026 | Fitur Tambahan Operasional: 1) Buku Kas Operasional Manual (masuk/keluar umum), 2) Cetak Kuitansi Tanda Terima PDF (A5 landscape siap cetak), 3) Workflow Pengajuan & Persetujuan Pinjaman Pengurus (status 'diajukan', 'ditolak', 'aktif') |
| 14 Nov 2026 | **Satu Sumber Kebenaran Transaksi Bersih**: `app/logika/transaksi_efektif.py` + SQL View `v_simpanan_efektif` & `v_pembayaran_angsuran_efektif`. Transaksi asli & pembalik dalam periode yang sama saling meniadakan secara bersih. Rekonsiliasi matematis saldo kas diuji pra-closing. Pembersihan teks UI dari karakter `&` (mnemonic) menjadi `dan`. |

## Pertanyaan Terbuka (menunggu jawaban Ibu)

- [ ] Persen jasa per bulan berapa? Apakah beda per jenis pinjaman? (Dapat diatur dinamis di tabel produk pinjaman)
- [ ] Ada biaya admin saat pinjaman cair? (Dapat diisi saat input pinjaman)
- [ ] Ada denda keterlambatan? (Default tidak aktif)
- [ ] Jenis simpanan apa saja? Setoran wajib jumlahnya tetap?
- [ ] Format laporan mingguan (minta foto contoh) dan hari pembuatannya
- [ ] Cara penomoran anggota dan pinjaman (default otomatis A-xxxx dan P-xxxx)
- [x] Template Excel untuk migrasi data lama (tersedia di menu Data -> Impor Data Excel)

## Checklist Modul

- [x] 1. Kerangka aplikasi + database + backup otomatis
- [x] 2. Data Anggota
- [x] 3. Simpanan
- [x] 4. Pinjaman + jadwal angsuran flat
- [x] 5. Angsuran / pembayaran
- [x] 6. Pencarian global + Kartu Anggota + filter cepat
- [x] 7. Layar Ringkasan + pengingat
- [x] 8. Laporan mingguan + ekspor Excel/PDF
- [x] 9. Closing bulanan + kunci periode
- [x] 10. Impor Excel
- [ ] 11. Pengemasan .exe + uji di PC target
- [ ] 12. Demo ke Ibu + kumpulkan masukan

## Catatan Teknis (diisi agent)

- `app/layanan/impor_excel.py`:
  - `buat_template_impor_excel`: menghasilkan file `.xlsx` siap pakai dengan 3 sheet standar (`Anggota`, `Saldo Simpanan Awal`, `Pinjaman Berjalan`) lengkap dengan contoh data.
  - `validasi_file_impor`: memeriksa duplikasi nomor anggota/pinjaman, mengecek keberadaan relasi anggota, memastikan uang integer >= 0, sanitasi tanggal ISO, dan menyusun laporan baris bermasalah.
  - `eksekusi_impor_data`: memicu backup otomatis pra-impor, memasukkan anggota, saldo awal simpanan, dan pinjaman berjalan (lengkap dengan penyesuaian sisa pokok pinjaman berjalan terdahulu).
- `app/ui/layar_impor.py`:
  - Terintegrasi di menu Data -> Impor Data Excel.
  - Menampilkan 4 tab: Pratinjau Anggota, Pratinjau Simpanan, Pratinjau Pinjaman, dan Laporan Masalah jika ada data tidak valid.
- Seluruh 47 unit test pytest lulus (100%).

## Masalah yang Diketahui / Utang Teknis

_Belum ada._

## Riwayat Sesi

| Tanggal | Yang dikerjakan | Hasil | Berikutnya |
|---|---|---|---|
| 14 Nov 2026 | Modul 1: Kerangka aplikasi, konfigurasi SQLite + PRAGMA, skema lengkap DATABASE.md, layanan backup otomatis & rotasi, jendela utama PySide6, unit test pytest | Selesai. 6 tes unit lulus. | Modul 2: Data Anggota |
| 14 Nov 2026 | Modul 2: Repositori anggota (CRUD, penomoran otomatis A-xxxx, proteksi hapus, filter, pagination, log aktivitas), Form & Layar Anggota PySide6, 6 unit test baru | Selesai. 12 tes unit lulus. | Modul 3: Simpanan |
| 14 Nov 2026 | Modul 3: Repositori simpanan (setor, tarik, hitung saldo, buku kas otomatis, pembalik koreksi, kunci periode), UI Layar Simpanan, 4 unit test baru | Selesai. 16 tes unit lulus. | Modul 4: Pinjaman + jadwal angsuran flat |
| 14 Nov 2026 | Modul 4: Logika flat murni & pembulatan cicilan terakhir, kalkulasi jatuh tempo akhir bulan, repositori pinjaman atomik, form pratinjau & UI Layar Pinjaman, 6 unit test baru | Selesai. 22 tes unit lulus. | Modul 5: Angsuran / Pembayaran |
| 14 Nov 2026 | Modul 5: Repositori angsuran (status cicilan, sisa pokok, bayar sebagian, pelunasan dipercepat, kas masuk otomatis, update status lunas pinjaman, pembalik koreksi), Form & Layar Angsuran PySide6, 6 unit test baru | Selesai. 28 tes unit lulus. | Modul 6: Pencarian global + Kartu Anggota + filter cepat |
| 14 Nov 2026 | Modul 6: Kotak pencarian global atas semua layar, Layar Kartu Anggota, Layar Filter Cepat (6 mode), Layanan Ekspor Excel (.xlsx), 3 unit test baru | Selesai. 31 tes unit lulus. | Modul 7: Layar Ringkasan + pengingat |
| 14 Nov 2026 | Modul 7: Repositori ringkasan dashboard, kalkulasi 4 kotak metrik, jatuh tempo minggu ini, deteksi anggota menunggak, banner pengingat mingguan & closing, UI Layar Ringkasan Halaman Awal, 3 unit test baru | Selesai. 34 tes unit lulus. | Modul 8: Laporan mingguan + ekspor Excel/PDF |
| 14 Nov 2026 | Modul 8: Repositori laporan mingguan (kalkulasi arus kas dan saldo kas awal/akhir), Layar Laporan Mingguan PySide6, Layanan Ekspor PDF reportlab & Excel openpyxl, 3 unit test baru | Selesai. 37 tes unit lulus. | Modul 9: Closing bulanan + kunci periode |
| 14 Nov 2026 | Modul 9: Repositori closing bulanan (pemeriksaan pra-closing, backup otomatis, snapshot di tabel closing & closing_saldo_anggota, kunci transaksi terkunci=1, pembukaan kembali dengan PIN), UI Layar Closing PySide6, 3 unit test baru | Selesai. 40 tes unit lulus. | Modul 10: Impor Excel |
| 14 Nov 2026 | Modul 10: Layanan impor Excel (pembuatan template .xlsx, validasi pratinjau, deteksi error, eksekusi impor atomik & backup otomatis), UI Layar Impor PySide6, 3 unit test baru | Selesai. 43 tes unit lulus. | Fitur Tambahan Operasional Admin |
| 14 Nov 2026 | Fitur Tambahan Admin: Buku Kas Operasional Manual (`app/db/repo_kas.py` & `app/ui/layar_kas.py`), Cetak Kuitansi Tanda Terima PDF (`app/layanan/cetak_kuitansi.py`), Workflow Pengajuan & Persetujuan Pinjaman Pengurus (`app/db/repo_pinjaman.py` & `app/ui/layar_pinjaman.py`), 4 unit test baru | Selesai. 47 tes unit lulus. | Penyempurnaan Efektifitas Kas & Redesain |
| 14 Nov 2026 | **Perbaikan Bug Kritis Transaksi Pembalik**: Implementasi Satu Sumber Kebenaran (`app/logika/transaksi_efektif.py`), SQL View `v_simpanan_efektif` & `v_pembayaran_angsuran_efektif` (user_version=3), rekonsiliasi kas pra-closing, audit migrasi closing lama, penataan ulang UI dan pembersihan karakter `&` menjadi `dan`. 5 unit test baru (total 52 lulus 100%). | Selesai. 52 tes unit lulus. | Pembuatan Modul Laporan Bulanan & Tahunan |
| 14 Nov 2026 | **Pembuatan Fitur Laporan Bulanan dan Laporan Tahunan**: 1) Satu Sumber Kebenaran `app/db/repo_laporan_periode.py` (konsistensi angka dengan Ringkasan, Mingguan, Closing; rekonsiliasi matematis saldo awal/akhir rantai 12 bulan; snapshot closing vs status sementara; perbandingan bulan lalu anti zero division). 2) Layanan ekspor multi-sheet Excel & PDF reportlab dengan grafik batang kas masuk vs keluar (`app/layanan/ekspor_laporan_periode.py`). 3) Komponen grafik ringan Qt berbasis QPainter (`app/ui/komponen/grafik_batang_qt.py`). 4) UI Layar Laporan Bulanan & Tahunan dengan worker thread non-blocking. 5) 5 unit test pengujian periode & benchmark 1 tahun 200 anggota (total 57 lulus 100%). | Selesai. 57 tes unit lulus. | Modul 11: Pengemasan .exe (PyInstaller) |

---
