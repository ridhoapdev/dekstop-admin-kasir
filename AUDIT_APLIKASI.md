# Audit Aplikasi Koperasi Simpan Pinjam dan Unit Toko

**Tanggal audit:** 19 November 2026  
**Hasil singkat:** aplikasi sudah memiliki cakupan fitur yang luas, tetapi ditemukan beberapa cacat yang dapat menghilangkan/menampilkan saldo salah, mengizinkan pembayaran silang antar pinjaman, menggagalkan koreksi transaksi, serta memblokir operasional lintas unit. **Jangan mengandalkan saldo piutang toko, hasil stock opname selisih lebih, atau laporan periode historis sebagai angka final sebelum temuan P1 diperbaiki dan direkonsiliasi.**

## Ruang lingkup dan metode

- Menelaah spesifikasi, aturan proyek, skema/migrasi, repositori transaksi, layar utama, kartu anggota/toko, laporan, closing, dan tes.
- Menjalankan seluruh tes yang tersedia (`76 passed`), `compileall`, dan pemeriksaan diagnostik workspace (`No errors found`).
- Membuat database sintetis sementara (tanpa membaca isi `data/koperasi.db` maupun berkas backup) untuk mereproduksi beberapa alur berisiko. Database sintetis dibersihkan setelah uji.
- Audit ini menilai kode dan alur, bukan merekonsiliasi data produksi atau memberikan pendapat hukum. Ada perubahan lokal yang belum dikomit di worktree; audit dilakukan pada versi kerja saat ini dan tidak membatalkan perubahan tersebut.

> Semua temuan di bawah adalah kandidat perbaikan. P1 berarti harus ditangani sebelum saldo/closing terkait dipercaya; P2 berarti masalah operasional, UX, keamanan, atau kelengkapan.

## Temuan P1 — integritas uang dan stok

### P1-1 — Utang toko di Kartu Anggota gagal dihitung

`ambil_daftar_nota_kredit_pembeli()` mengembalikan saldo setiap nota dengan nama `sisa`, sedangkan `ambil_ringkasan_piutang_anggota()` membaca `sisa_piutang`. Jika pembeli anggota memiliki nota kredit, fungsi melempar `KeyError: 'sisa_piutang'`. Layar Kartu Anggota menangkap semua exception lalu mengganti nilai utang dengan `-`, sehingga masalah tampak seperti data toko tidak ada, bukan sebagai kegagalan.

**Reproduksi sintetis:** anggota ditautkan ke pembeli, dibuat penjualan kredit, lalu pemanggilan ringkasan utang menghasilkan `KeyError: 'sisa_piutang'`.

Rujukan: [repo_piutang.py](./app/db/repo_piutang.py#L92), [repo_kartu_toko.py](./app/db/repo_kartu_toko.py#L537), [layar_kartu_anggota.py](./app/ui/layar_kartu_anggota.py#L197).

### P1-2 — Pembeli toko tidak dapat ditautkan ke anggota lewat UI

Skema dan repositori mendukung `pembeli.anggota_id`, tetapi form Master Pihak tidak menyediakan pemilih anggota dan saat menyimpan tidak mengirim `anggota_id`. Akibatnya pembeli baru yang dibuat melalui aplikasi tidak dapat dikaitkan dengan anggota; ringkasan utang toko di kartu anggota tidak akan menemukan pembeli tersebut meskipun nama orangnya sama. Pencocokan nama otomatis juga tidak aman untuk identitas/utang.

Selain itu, `anggota_id` tidak unik dan ringkasan memakai `fetchone()`. Bila seorang anggota mempunyai lebih dari satu profil pembeli tertaut, hanya satu yang dipakai—tanpa aturan agregasi atau urutan yang jelas—sehingga saldo bisa kurang.

Rujukan: [layar_pihak.py](./app/ui/layar_pihak.py#L100), [repo_pihak.py](./app/db/repo_pihak.py#L69), [repo_kartu_toko.py](./app/db/repo_kartu_toko.py#L543), [skema_toko.py](./app/db/skema_toko.py#L40).

### P1-3 — Pembayaran angsuran dapat ditautkan ke cicilan pinjaman lain

`bayar_angsuran()` memvalidasi saldo pokok terhadap `pinjaman_id`, tetapi tidak memastikan `angsuran_id` memang milik pinjaman tersebut. Status cicilan dihitung dengan menghubungkan pembayaran ke `angsuran_id`, sementara sisa pokok dihitung dari `pinjaman_id`. Satu pembayaran dengan demikian bisa mengurangi pokok pinjaman A tetapi membuat jadwal pinjaman B terlihat lunas.

**Reproduksi sintetis:** pembayaran dicatat untuk pinjaman anggota pertama dengan `angsuran_id` pinjaman anggota kedua; hasilnya sisa pokok pinjaman pertama menjadi nol dan cicilan pinjaman kedua berstatus lunas.

Rujukan: [repo_angsuran.py](./app/db/repo_angsuran.py#L139), khususnya validasi dan insert di sekitar baris 187–205 serta query status cicilan di sekitar baris 79–98.

### P1-4 — Pembatalan pembayaran piutang toko gagal di constraint database

Pembalik alokasi piutang dibuat dengan `jumlah=-jml`, tetapi tabel `alokasi_piutang` mewajibkan `jumlah > 0`. Karena itu pembatalan pembayaran yang sudah dialokasikan melempar `sqlite3.IntegrityError: CHECK constraint failed: jumlah > 0` dan transaksi database dibatalkan; kas dan saldo piutang tidak terkoreksi.

**Reproduksi sintetis:** jual kredit, terima pembayaran, lalu batalkan pembayaran; operasi gagal dengan constraint tersebut. Jalur pembalik ini tidak tercakup tes yang ada.

Ada masalah lanjutan pada perhitungan: saldo nota/total piutang hanya menjumlahkan baris dengan `membalik_id IS NULL`. Jika desain pembalik diubah menjadi transaksi positif, query tetap akan menghitung alokasi asli sebagai pembayaran kecuali aturan efektivitasnya juga diperbaiki. Rujukan: [repo_piutang.py](./app/db/repo_piutang.py#L233), [repo_piutang.py](./app/db/repo_piutang.py#L265), [repo_piutang.py](./app/db/repo_piutang.py#L312), [skema_toko.py](./app/db/skema_toko.py#L312).

### P1-5 — Closing simpan pinjam dan toko saling mengunci periode

`cek_periode_terkunci()` mengembalikan terkunci jika **salah satu** dari `closing` SP atau `closing_toko` berstatus tertutup. Fungsi yang sama dipakai kedua domain. Jadi closing SP bulan tertentu dapat memblokir transaksi toko bulan yang sama, dan closing toko dapat memblokir transaksi SP, padahal spesifikasi menetapkan closing masing-masing unit terpisah.

Rujukan: [repo_simpanan.py](./app/db/repo_simpanan.py#L15); pemanggil dari [layanan_stok.py](./app/layanan/layanan_stok.py#L14) serta repositori simpan pinjam/toko lain.

### P1-6 — Retur supplier “potong hutang” hanya tersimpan sebagai retur, tidak mengurangi hutang

Untuk kompensasi `potong_hutang`, cabang repositori hanya berisi `pass`. Perhitungan hutang supplier di kartu supplier dan laporan menghitung nilai faktur dikurangi pembayaran saja, tanpa pengurangan retur. Pengguna dapat memilih potong hutang, tetapi saldo hutang dan laporan akan tetap menunjukkan jumlah sebelum retur.

Rujukan: [repo_retur_toko.py](./app/db/repo_retur_toko.py#L192), [repo_kartu_toko.py](./app/db/repo_kartu_toko.py#L341), [repo_laporan_toko.py](./app/db/repo_laporan_toko.py#L311).

### P1-7 — Stock opname dengan selisih lebih tidak dapat difinalisasi

`finalisasi_sesi_opname()` memanggil `tambah_stok_masuk()` dengan argumen `qty_masuk` dan `catatan`; fungsi layanan menerima `qty` dan tidak mempunyai parameter `catatan`. Begitu opname menemukan stok fisik lebih besar dari stok sistem, finalisasi gagal dengan `TypeError` dan sesi tetap belum selesai.

**Reproduksi sintetis:** stok sistem 10, fisik 11; finalisasi menghasilkan `TypeError: tambah_stok_masuk() got an unexpected keyword argument 'qty_masuk'`.

Rujukan: [repo_opname_toko.py](./app/db/repo_opname_toko.py#L196), [layanan_stok.py](./app/layanan/layanan_stok.py#L50), [test_toko_modul15.py](./tests/test_toko_modul15.py#L1) (tes opname menguji selisih kurang, bukan selisih lebih).

### P1-8 — Ringkasan laporan toko memakai saldo saat ini untuk periode lampau

Laporan menerima rentang tanggal, tetapi nilai persediaan diambil dari seluruh `lot_stok` saat ini; piutang dihitung total terkini; hutang supplier dan hutang penitip juga diambil dari keadaan terkini. Karena itu laporan bulan lalu dapat menampilkan saldo persediaan/piutang/hutang setelah transaksi bulan-bulan berikutnya. Nilai ini juga dipakai ketika menghitung ringkasan pra-closing, sehingga closing periode yang lebih lama berisiko menyimpan snapshot yang bukan keadaan akhir periode tersebut.

Rujukan: [repo_laporan_toko.py](./app/db/repo_laporan_toko.py#L210), terutama query nilai stok (sekitar baris 295–301), piutang (305), hutang supplier (308–317), dan hutang penitip (sekitar 320 ke atas).

## Temuan P2 — kelengkapan, UX, keamanan, dan performa

### P2-1 — Kartu Anggota belum menampilkan seluruh pinjaman dan riwayat toko

Repositori mengembalikan semua pinjaman aktif, tetapi UI hanya merender `pinj_list[0]`; anggota yang memiliki beberapa pinjaman aktif kehilangan rincian pinjaman selain yang pertama (meski total tunggakan dijumlahkan). Riwayat yang disebut “seluruh transaksi” hanya mengambil simpanan dan pembayaran angsuran. Utang toko ditampilkan sebagai satu angka terpisah—tidak ada nota, tanggal jatuh tempo, pembayaran toko, maupun riwayat transaksi toko pada kartu anggota.

Rujukan: [layar_kartu_anggota.py](./app/ui/layar_kartu_anggota.py#L178), [repo_kartu_anggota.py](./app/db/repo_kartu_anggota.py#L158).

### P2-2 — Hasil pencarian pihak toko tidak membuka entitas yang dipilih

Klik hasil pencarian supplier/penitip/pembeli hanya membuka layar umum Pihak/Penitipan/Piutang dan tidak meneruskan ID entitas ke form atau detail terpilih. Pengguna harus mencari ulang. Fungsi data kartu supplier, penitip, dan pembeli ada di repositori, tetapi alur UI pencarian tidak menavigasi ke detail kartu tersebut.

Rujukan: [jendela_utama.py](./app/ui/jendela_utama.py#L482).

### P2-3 — Dropdown kasir menjanjikan pencarian yang tidak dibangun sebagai pencarian

Placeholder menyuruh pengguna mengetik nama/kode lalu Enter, tetapi `QComboBox` kasir tidak dibuat editable dan tidak ada completer/filter pencarian. Daftar hanya memuat maksimal 500 barang dari nama/kode; alias `kata_kunci` yang didukung pencarian barang tidak dipakai di dropdown. Untuk pengguna awam, placeholder menjanjikan kemampuan yang berbeda dari perilaku kontrol.

Rujukan: [layar_penjualan.py](./app/ui/layar_penjualan.py#L81), [layar_penjualan.py](./app/ui/layar_penjualan.py#L203).

### P2-4 — Pencarian global tidak toleran salah ketik dan dapat gagal diam-diam

Spesifikasi menjanjikan toleransi salah ketik ringan, tetapi pencarian memakai `LIKE '%teks%'`; tidak ada fuzzy matching untuk pencarian global. Pemanggilan pencarian toko juga dibungkus `except Exception: pass`, jadi kegagalan skema/query hanya menghilangkan hasil toko tanpa pesan atau log. Hasil dicari pada setiap perubahan teks secara sinkron di UI.

Rujukan: [repo_kartu_anggota.py](./app/db/repo_kartu_anggota.py#L21), [repo_kartu_anggota.py](./app/db/repo_kartu_anggota.py#L72), [jendela_utama.py](./app/ui/jendela_utama.py#L466).

### P2-5 — Tombol Keluar terhubung dua kali

Tombol Keluar menambahkan koneksi `clicked` ke handler konfirmasi dua kali. Satu klik dapat menjalankan konfirmasi lebih dari sekali. Widget juga dimasukkan ke layout dua kali.

Rujukan: [sidebar.py](./app/ui/komponen/sidebar.py#L629).

### P2-6 — Kegagalan backup penting ditelan

Saat aplikasi ditutup, exception backup ditangkap tanpa log/pemberitahuan; closing toko juga meneruskan closing jika backup pra-closing gagal. Ini bertentangan dengan tujuan backup sebelum operasi penting dan membuat operator menyangka salinan aman sudah tersedia.

Rujukan: [jendela_utama.py](./app/ui/jendela_utama.py#L713), [repo_closing_toko.py](./app/db/repo_closing_toko.py#L106).

### P2-7 — Perlindungan data pribadi dan PIN belum cukup untuk data operasional nyata

Database dan backup berisi identitas serta informasi simpanan/utang. Tidak ditemukan login aplikasi; PIN closing default `1234` diterima ketika hash belum diatur. Proteksi akhirnya bergantung pada akun Windows, akses folder, serta perlindungan file backup. Ini perlu dipastikan untuk penggunaan nyata, khususnya saat komputer dipakai bersama atau backup dipindahkan.

Rujukan: [repo_closing_toko.py](./app/db/repo_closing_toko.py#L36), [skema.py](./app/db/skema.py#L222), [RULES.md](./RULES.md#L102).

### P2-8 — Kartu barang memuat seluruh mutasi sebelum memotong halaman

Kartu barang mengambil semua mutasi ke memori, menghitung saldo kumulatif, baru melakukan slicing untuk paginasi. Selain biaya memori/waktu yang tumbuh, filter tanggal/jenis diterapkan sebelum saldo berjalan dihitung sehingga saldo awal pada baris pertama hasil filter menjadi nol, bukan saldo sebelum periode filter.

Rujukan: [repo_kartu_toko.py](./app/db/repo_kartu_toko.py#L245), [repo_kartu_toko.py](./app/db/repo_kartu_toko.py#L290).

### P2-9 — Navigasi berpotensi membebani pengguna, tetapi jumlah halaman bukan bug dengan sendirinya

Sidebar berisi enam grup dan sekitar dua puluh lebih tujuan karena fitur SP dan toko masing-masing memiliki layar transaksi, master, laporan, dan closing. Ini tidak otomatis “terlalu banyak” untuk cakupan fitur tersebut, tetapi untuk target satu admin awam, operasi inti dan administrasi/periodik sebaiknya dibedakan. Jangan menghapus fitur CRUD; sederhanakan pintu masuk, gunakan aksi kontekstual/dashboard, serta kurangi duplikasi jalur.

Khususnya, menu pengaturan lama hanya disiapkan di `_buat_menu`, sementara menu bar disembunyikan dan halaman pengaturan masih berupa pesan placeholder; asumsi bisnis yang disebut “dapat diatur” belum tentu bisa diubah oleh admin.

Rujukan: [sidebar.py](./app/ui/komponen/sidebar.py#L640), [jendela_utama.py](./app/ui/jendela_utama.py#L67), [jendela_utama.py](./app/ui/jendela_utama.py#L300).

## Riset regulasi dan konteks operasional

Sumber primer yang ditinjau:

- [Permenkop UKM No. 8 Tahun 2023 — Usaha Simpan Pinjam Oleh Koperasi](https://peraturan.bpk.go.id/Details/260414/permenkop-ukm-no-8-tahun-2023): halaman BPK menyatakan berlaku dan cakupannya termasuk perizinan, standar operasional manajemen, kegiatan usaha, permodalan, pengenalan pengguna jasa, pengawasan, serta pelaporan. Karena itu aplikasi operasional saja belum membuktikan pemenuhan izin, SOP, KYC, dan kewajiban pelaporan. Penerapan tepatnya bergantung pada bentuk dan status usaha koperasi.
- [Permenkop UKM No. 2 Tahun 2024 — Kebijakan Akuntansi Koperasi](https://peraturan.bpk.go.id/Details/308465/permenkop-ukm-no-2-tahun-2024): halaman BPK menyatakan berlaku dan menggantikan pedoman akuntansi koperasi sebelumnya yang disebut di halaman tersebut. Aplikasi memiliki buku kas, stok, piutang, dan laporan operasional, tetapi tidak memiliki jurnal umum/paket laporan keuangan lengkap menurut standar akuntansi. Ini sesuai batasan eksplisit SPEC, sehingga aplikasi sebaiknya diposisikan sebagai **sistem operasional**, bukan satu-satunya sumber laporan keuangan resmi.
- [UU No. 4 Tahun 2023 tentang P2SK](https://peraturan.bpk.go.id/Details/240203/uu-no-4-tahun-2023) dan [perubahannya, UU No. 4 Tahun 2026](https://peraturan.bpk.go.id/Details/350166/uu-no-4-tahun-2026): regulasi sektor keuangan koperasi telah berubah; jangan hanya mengandalkan ringkasan peraturan lama untuk menentukan apakah suatu KSP/USP termasuk pengawasan/izin tertentu. Minta konfirmasi berdasarkan klasifikasi koperasi dan skala usahanya.
- [UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi](https://peraturan.bpk.go.id/Details/229798/uu-no-27-tahun-2022): relevan karena aplikasi memproses data identitas dan informasi keuangan anggota. Langkah minimum operasional: akses Windows terbatas, backup terenkripsi/terkendali, retensi dan pemulihan backup yang jelas, serta prosedur penanganan kehilangan perangkat.

**Implikasi untuk unit toko:** pemisahan kas toko dan kas SP sudah merupakan batas domain yang baik, tetapi harus tetap direkonsiliasi. Retur, piutang pembeli, hutang supplier/penitip, stok FIFO, kas, dan nilai persediaan harus mempunyai saldo efektif yang konsisten dan laporan periode yang benar-benar “as of” tanggal akhir, bukan saldo hari ini. Saat ini ada beberapa pelanggaran alur tersebut (P1-4, P1-6, P1-8).

## Urutan perbaikan yang disarankan

1. Perbaiki tautan anggota–pembeli dan ringkasan utang anggota; jangan menelan exception integrasi.
2. Tegakkan keterikatan `angsuran_id` ke `pinjaman_id`, dan tambahkan tes lintas-pinjamannya.
3. Rancang ulang pembalik piutang agar selaras dengan constraint database; tes pembayaran, pembalik, saldo nota, total piutang, dan kas.
4. Implementasikan dampak retur supplier terhadap hutang secara eksplisit; tes pilihan `potong_hutang` dan `kas_masuk`.
5. Perbaiki finalisasi stock opname selisih lebih dan tes kedua arah (lebih/kurang) serta atomisitas.
6. Pisahkan pemeriksaan kunci periode SP dan toko; tutup satu unit tanpa memblokir unit lain.
7. Hitung snapshot historis pada tanggal akhir periode dan rekonsiliasikan closing lama sebelum dipakai sebagai laporan resmi.
8. Setelah data core benar, perbaiki pencarian/dropdown, kartu anggota lengkap, navigasi, logging error, dan proteksi lokal.
9. Jalankan migrasi/perbaikan hanya setelah backup yang dapat dibuka diverifikasi; cocokkan hasil saldo dengan dokumen sumber koperasi, bukan hanya tes unit.

## Batas audit

Tes yang ada lulus, tetapi belum mencakup skenario-skenario yang direproduksi di atas. Audit ini tidak membuka database/backup operasional untuk menjaga privasi; jadi belum mengukur berapa banyak transaksi nyata yang sudah terpengaruh, dan tidak menyatakan legalitas/kepatuhan koperasi. Sebelum koreksi data produksi, perlu inventaris transaksi pembalik, nota kredit, retur supplier, closing, dan pemetaan anggota–pembeli dalam salinan database terpisah.
