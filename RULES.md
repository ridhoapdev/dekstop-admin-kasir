# RULES.md — Aturan Tetap untuk Agent

> Aturan di sini mengikat. Jika ada konflik dengan permintaan di chat, tanyakan dulu sebelum melanggar.

## 1. Teknologi (jangan diganti tanpa izin)

- **Bahasa**: Python 3.11 atau 3.12 (64-bit).
- **GUI**: PySide6 (Qt Widgets, BUKAN QML, BUKAN WebEngine).
- **Database**: `sqlite3` bawaan Python. Tanpa ORM berat; boleh query SQL langsung dengan fungsi repositori yang rapi.
- **Ekspor Excel**: `openpyxl`. **Ekspor PDF**: `reportlab`. Hindari pustaka besar lain.
- **Pengemasan**: PyInstaller, mode **onedir** (BUKAN onefile, karena onefile lambat dibuka di PC lawas).
- **Tanpa**: Electron, browser/webview, server, Docker, koneksi internet, telemetri.
- Setiap dependensi baru harus dicatat di `requirements.txt` dan dibenarkan alasannya di `PROGRESS.md`.

## 2. Lingkungan Target

- Windows 10 Pro 64-bit, Intel Core i3-3220, **RAM 4 GB**.
- RAM aplikasi saat idle target < 150 MB. Startup target < 5 detik.
- Jangan muat semua data ke memori; gunakan query dengan `LIMIT`, paginasi, dan indeks.
- Hindari animasi berat dan efek bayangan/blur.
- Uji akhir wajib dilakukan di PC dengan spesifikasi setara.

## 3. Struktur Proyek

```
koperasi-app/
├─ SPEC.md  DATABASE.md  RULES.md  PROGRESS.md
├─ requirements.txt
├─ main.py                  # titik masuk
├─ app/
│  ├─ config.py             # path, konstanta
│  ├─ db/
│  │  ├─ koneksi.py         # buka DB + PRAGMA
│  │  ├─ skema.py           # CREATE TABLE + migrasi (user_version)
│  │  └─ repo_*.py          # query per modul (anggota, simpanan, ...)
│  ├─ logika/               # aturan bisnis MURNI (tanpa GUI)
│  │  ├─ angsuran_flat.py
│  │  ├─ closing.py
│  │  └─ laporan.py
│  ├─ ui/
│  │  ├─ jendela_utama.py
│  │  ├─ layar_*.py         # satu file per layar
│  │  └─ komponen/          # widget yang dipakai ulang
│  ├─ layanan/
│  │  ├─ backup.py
│  │  ├─ draft.py
│  │  ├─ ekspor_excel.py
│  │  ├─ ekspor_pdf.py
│  │  └─ impor_excel.py
│  └─ util/                 # format uang, tanggal, validasi
├─ tests/                   # pytest untuk app/logika dan app/db
├─ data/                    # koneksi koperasi.db (JANGAN di-commit)
├─ backup/                  # salinan otomatis
└─ build/                   # skrip PyInstaller
```

Pemisahan wajib: **logika bisnis tidak boleh mengimpor PySide6**. Semua hitungan uang harus bisa diuji tanpa membuka jendela.

## 4. Penyimpanan Data & Keandalan

1. **Tidak ada tombol "Simpan Semua".** Setiap transaksi disimpan ke database saat form dikonfirmasi (`COMMIT` langsung).
2. Gunakan transaksi database (`with conn:`) untuk operasi multi-tabel (contoh: pinjaman baru = insert pinjaman + semua angsuran + kas, semuanya sukses atau semuanya batal).
3. `PRAGMA journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`.
4. **Draft otomatis**: isian form yang belum disimpan dicatat ke tabel `draft` (debounce ±2 detik), dipulihkan saat form dibuka lagi, dihapus setelah transaksi tersimpan.
5. **Ingat posisi terakhir**: layar, filter, dan tanggal terakhir disimpan di `pengaturan` dan dipulihkan saat dibuka.
6. **Backup otomatis (tanpa aksi pengguna)**:
   - Saat aplikasi dibuka DAN saat ditutup: salin DB memakai `sqlite3.Connection.backup()` (BUKAN copy file mentah saat DB terbuka) ke `backup/koperasi_YYYY-MM-DD_HHMM.db`.
   - Simpan 30 backup terbaru, hapus yang lebih lama.
   - Backup tambahan otomatis sebelum closing dan sebelum impor Excel.
   - Jika `backup_folder_kedua` diatur (flash disk / folder cloud), salin juga ke sana; jika tidak tersedia, lanjut diam-diam dan catat di log (jangan munculkan error mengganggu).
   - Tampilkan di Ringkasan: "Backup terakhir: hari ini 08.12".
7. **Jangan pernah menghapus atau menimpa `koperasi.db`** dalam kode selain lewat prosedur restore yang eksplisit dan dikonfirmasi.
8. Tangani `sqlite3.OperationalError: database is locked` dengan retry singkat lalu pesan ramah.
9. Jika file DB rusak: tawarkan pulihkan dari backup terbaru.

## 5. Aturan Data Keuangan

- Uang = `int` rupiah. **Dilarang `float`** untuk uang. Untuk persen gunakan `decimal.Decimal`, lalu bulatkan ke int.
- **Tanpa DELETE/UPDATE bebas pada transaksi.** Koreksi lewat transaksi pembalik (`membalik_id`) dengan keterangan alasan.
- Periode yang sudah di-closing **terkunci** di level logika DAN dicek ulang di level database (trigger atau pemeriksaan di repositori).
- Setiap perubahan penting menulis `log_aktivitas` dengan ringkasan bahasa manusia.
- Validasi di logika, bukan hanya di UI: jumlah > 0, tanggal valid, anggota aktif, tidak bayar melebihi sisa tagihan tanpa konfirmasi.

## 6. Aturan Tampilan & Bahasa

- Semua teks UI dalam **Bahasa Indonesia** sederhana. Hindari istilah teknis (jangan tampilkan kata "database", "error", "exception", "NULL").
- Font dasar minimal 12 pt, tombol minimal tinggi 40 px, kontras tinggi.
- Format uang `Rp 1.250.000`, tanggal `14 Nov 2026`, titik sebagai pemisah ribuan.
- Maksimal 2 klik dari Ringkasan ke aksi utama.
- Keyboard-first: urutan Tab logis, Enter pada kolom terakhir = simpan, Esc = batal, fokus otomatis ke kolom pertama.
- Aksi berisiko (balik transaksi, closing, buka closing, restore) wajib ada dialog konfirmasi dengan kalimat yang jelas tentang akibatnya.
- Pesan error: jelaskan masalah dan cara memperbaiki. Contoh: "Jumlah angsuran belum diisi." Bukan: "ValueError".
- Jangan menampilkan jendela yang membekukan UI; operasi lama (ekspor, impor) pakai thread/progress.

## 7. Standar Kode

- Type hints dan docstring singkat berbahasa Indonesia atau Inggris, konsisten.
- Nama modul/fungsi: `snake_case`. Teks tampilan di satu tempat (mudah diubah).
- Satu fungsi satu tugas. Hindari file > 400 baris.
- Query SQL selalu **parameterized** (`?`), tidak pernah f-string dari input.
- Tangkap exception di batas UI, catat detail ke file `log/app.log` (rotasi, maks 5 MB), tampilkan pesan ramah ke pengguna.
- Jangan menelan error diam-diam pada operasi keuangan.

## 8. Pengujian

- `pytest` wajib untuk: jadwal angsuran flat (termasuk pembulatan & tenor 1), tanggal jatuh tempo akhir bulan, saldo simpanan dengan pembalik, sisa pokok, status angsuran, kunci periode, closing.
- Contoh uji minimum jadwal flat: plafon 10.000.000, tenor 10, jasa 1% per bulan, hasilnya pokok 1.000.000/bln, jasa 100.000/bln, total pokok = plafon.
- Contoh pembulatan: plafon 1.000.000 tenor 3 → pokok 333.333, 333.333, 333.334.
- Jalankan seluruh tes sebelum menandai modul selesai.
- Sediakan skrip `seed_demo.py` yang mengisi data FIKTIF untuk demo ke pengguna (ratusan anggota, ribuan transaksi) sekaligus uji performa.

## 9. Pengemasan (PyInstaller)

- Mode `--onedir`, tanpa konsol (`--noconsole`), ikon aplikasi.
- Hasil akhir: satu folder berisi `Koperasi.exe`; buat **pintasan di Desktop** supaya pengguna klik 2x.
- Data (`data/`, `backup/`) berada di folder terpisah yang TIDAK terhapus saat aplikasi diperbarui.
- Opsional: installer (Inno Setup) untuk memudahkan pemasangan.
- Uji di PC bersih tanpa Python terpasang.

## 10. Privasi & Keamanan

- Data anggota adalah data pribadi/keuangan: tidak ada pengiriman keluar, tidak ada telemetri, tidak ada layanan cloud tanpa izin eksplisit.
- Data contoh/demo harus **fiktif**. Jangan memasukkan data nyata ke repositori atau ke chat dengan AI.
- PIN disimpan sebagai hash (bukan teks biasa).
- Tambahkan `data/`, `backup/`, `log/`, `*.db` ke `.gitignore`.

## 11. Cara Kerja Agent

1. Mulai setiap sesi dengan membaca `SPEC.md`, `DATABASE.md`, `RULES.md`, `PROGRESS.md`.
2. Kerjakan **satu modul** dari urutan di `SPEC.md` per sesi. Jangan lompat atau melebar.
3. Sebelum mengubah skema database, jelaskan dampaknya dan buat migrasi (naikkan `user_version`), jangan edit tabel lama diam-diam.
4. Jika ada keputusan bisnis yang belum jelas (lihat bagian "Asumsi" di SPEC), **tanyakan atau jadikan pengaturan**, jangan menebak lalu hardcode.
5. Setelah selesai: jalankan tes, perbarui `PROGRESS.md`, ringkas apa yang berubah dan cara mencobanya.
