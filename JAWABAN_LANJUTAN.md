# JAWABAN_LANJUTAN.md — Klarifikasi & Pemahaman Teknis Mendalam

Dokumen ini menyajikan jawaban faktual terhadap 6 pertanyaan teknis mendalam mengenai sistem Simpan Pinjam dan Toko berdasarkan kode sumber yang benar-benar ada di aplikasi per 16 November 2026.

---

## P1. PELUNASAN PINJAMAN DAN JASA

### P1.a. Salin utuh fungsi `bayar_angsuran`. Di mana tepatnya kode memutuskan status pinjaman menjadi 'lunas'? Apakah ada pengecekan bahwa jasa (bunga) sudah terbayar?

#### Jawaban Faktual Singkat
Kode memutuskan status pinjaman menjadi `'lunas'` tepat pada baris **221–226**, yaitu saat `sisa_pokok_baru == 0` (dihitung dari `sisa_pokok_saat_ini - bayar_pokok`). **TIDAK ADA PENGECEKAN SAMA SEKALI BAHWA JASA (BUNGA) SUDAH TERBAYAR**. Status pinjaman lunas murni hanya memeriksa apakah seluruh pokok plafon sudah terbayar (sisa pokok = 0).

#### Kutipan Kode Asli
Lokasi: `app/db/repo_angsuran.py:139-238`
```python
def bayar_angsuran(
    conn: sqlite3.Connection,
    pinjaman_id: int,
    angsuran_id: Optional[int],
    tanggal: str,
    bayar_pokok: int,
    bayar_jasa: int,
    denda: int = 0,
    keterangan: Optional[str] = None
) -> int:
    """
    Menyimpan pembayaran angsuran.
    Mendukung pembayaran cicilan tertentu (angsuran_id ditentukan)
    maupun pelunasan dipercepat (angsuran_id = None).
    """
    if bayar_pokok < 0 or bayar_jasa < 0 or denda < 0:
        raise ValueError("Nominal pembayaran tidak boleh bernilai negatif.")
    
    total_bayar = bayar_pokok + bayar_jasa + denda
    if total_bayar <= 0:
        raise ValueError("Total pembayaran harus lebih dari Rp 0.")

    periode = tanggal[:7]
    if cek_periode_terkunci(conn, periode):
        raise ValueError(f"Periode {periode} sudah ditutup (closing). Pembayaran tidak dapat disimpan.")

    cur = conn.cursor()
    # Cek pinjaman
    cur.execute(
        """
        SELECT p.*, a.nama AS nama_anggota 
        FROM pinjaman p 
        JOIN anggota a ON p.anggota_id = a.id 
        WHERE p.id = ?;
        """,
        (pinjaman_id,)
    )
    pinj = cur.fetchone()
    if not pinj:
        raise ValueError("Pinjaman tidak ditemukan.")

    if pinj["status"] == "lunas":
        raise ValueError("Pinjaman ini sudah lunas.")
    if pinj["status"] == "batal":
        raise ValueError("Pinjaman ini berstatus batal.")

    # Cek sisa pokok keseluruhan
    sisa_pokok_saat_ini = hitung_sisa_pokok_pinjaman(conn, pinjaman_id)
    if bayar_pokok > sisa_pokok_saat_ini:
        raise ValueError(
            f"Pembayaran pokok ({format_rupiah(bayar_pokok)}) melebihi sisa pokok pinjaman ({format_rupiah(sisa_pokok_saat_ini)})."
        )

    ket_bersih = keterangan.strip() if keterangan else ""

    with conn:
        # 1. Simpan ke tabel pembayaran_angsuran
        cur = conn.execute(
            """
            INSERT INTO pembayaran_angsuran 
            (pinjaman_id, angsuran_id, tanggal, bayar_pokok, bayar_jasa, denda, keterangan, periode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (pinjaman_id, angsuran_id, tanggal, bayar_pokok, bayar_jasa, denda, ket_bersih or None, periode)
        )
        bayar_id = cur.lastrowid

        # 2. Catat kas masuk otomatis
        ket_kas = f"Angsuran pinjaman {pinj['no_pinjaman']} ({pinj['nama_anggota']})"
        if ket_bersih:
            ket_kas += f" - {ket_bersih}"
        
        conn.execute(
            """
            INSERT INTO kas_transaksi 
            (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
            VALUES (?, ?, ?, 0, 'angsuran', ?, ?);
            """,
            (tanggal, ket_kas, total_bayar, bayar_id, periode)
        )

        # 3. Cek apakah pinjaman kini sudah lunas
        sisa_pokok_baru = sisa_pokok_saat_ini - bayar_pokok
        if sisa_pokok_baru == 0:
            conn.execute(
                "UPDATE pinjaman SET status = 'lunas', tanggal_lunas = ? WHERE id = ?;",
                (tanggal, pinjaman_id)
            )

        # 4. Catat log aktivitas
        detail_log = (
            f"Bayar angsuran pinjaman {pinj['no_pinjaman']} ({pinj['nama_anggota']}): "
            f"Pokok {format_rupiah(bayar_pokok)}, Jasa {format_rupiah(bayar_jasa)}"
        )
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("tambah", "pembayaran_angsuran", bayar_id, detail_log)
        )

    return bayar_id
```

#### Lokasi
- `app/db/repo_angsuran.py:139-238`

#### Hal yang Tidak Ditemukan
- Pengecekan atau validasi bahwa total jasa telah terbayar lunas sebelum mengubah `status = 'lunas'`: **TIDAK DITEMUKAN**.

---

### P1.b. Apa yang terjadi jika sisa pokok menjadi 0 padahal total `bayar_jasa` masih kurang dari total jasa di jadwal angsuran? Apakah jasa yang kurang itu masih tercatat sebagai tagihan di layar mana pun?

#### Jawaban Faktual Singkat
Jika sisa pokok menjadi 0, status pinjaman berubah menjadi `'lunas'`.
Setelah status pinjaman menjadi `'lunas'`, pinjaman tersebut **hilang dari daftar pinjaman aktif** (karena query dropdown dan filter aktif hanya memfilter `WHERE status = 'aktif'`).
Akibatnya:
1. Di `LayarAngsuran` (dialog bayar): pinjaman tersebut tidak bisa dipilih lagi karena `ambil_daftar_pinjaman(status_filter='aktif')` mengecualikannya (`app/ui/layar_angsuran.py:131`).
2. Di `LayarRingkasan`: pinjaman lunas tidak diperiksa lagi untuk tunggakan/jatuh tempo karena query ringkasan hanya membaca `WHERE p.status = 'aktif'` (`app/db/repo_ringkasan.py:101`).
3. Di `LayarKartuAnggota`: bagian *Pinjaman Aktif* hanya menampilkan `WHERE p.status = 'aktif'` (`app/db/repo_kartu_anggota.py:112`). Sisa jasa tersebut **TIDAK MUNCUL LAGI SEBAGAI TAGIHAN AKTIF MAUPUN TUNGGAKAN DI LAYAR MANA PUN**. Sisa jasa hanya dapat terlihat jika pengguna membuka dialog detail jadwal pinjaman di `LayarPinjaman` melalui tombol "Lihat Jadwal" (`app/ui/layar_pinjaman.py:348`), di mana fungsi `ambil_daftar_angsuran_dengan_status` akan menghitung `sisa_jasa = max(0, tagihan_jasa - terbayar_jasa)` per baris cicilan lama.

#### Kutipan Kode Asli
Lokasi: `app/ui/layar_angsuran.py:131-134`
```python
    def _muat_pilihan_pinjaman(self) -> None:
        self.combo_pinjaman.clear()
        daftar = ambil_daftar_pinjaman(self.conn, status_filter="aktif", limit=300)
        for p in daftar:
            teks = f"{p['no_pinjaman']} - {p['nama_anggota']} (Plafon: {format_rupiah(p['plafon'])})"
            self.combo_pinjaman.addItem(teks, p["id"])
```
Lokasi: `app/db/repo_kartu_anggota.py:112`
```python
        WHERE p.anggota_id = ? AND p.status = 'aktif'
```
Lokasi: `app/db/repo_ringkasan.py:101`
```python
        WHERE p.status = 'aktif' AND a.jatuh_tempo >= ? AND a.jatuh_tempo <= ?
```

#### Lokasi
- `app/ui/layar_angsuran.py:131-134`
- `app/db/repo_kartu_anggota.py:112`
- `app/db/repo_ringkasan.py:101`

#### Hal yang Tidak Ditemukan
- Mekanisme penagihan terpisah atau peringatan sisa jasa pinjaman setelah status pinjaman menjadi `'lunas'`: **TIDAK DITEMUKAN**.

---

### P1.c. Bagaimana alur "pelunasan dipercepat" (`angsuran_id = None`)? Apakah UI menghitung otomatis nilai `bayar_pokok` dan `bayar_jasa`, atau operator mengetik manual? Salin kode perhitungannya kalau ada.

#### Jawaban Faktual Singkat
Alur pelunasan dipercepat dipicu ketika operator mencentang kotak `chk_pelunasan_dipercepat` pada dialog `DialogInputAngsuran`:
1. UI **mengisi otomatis** nilai `bayar_pokok` sebesar seluruh sisa pokok pinjaman (`sisa_pokok = hitung_sisa_pokok_pinjaman(self.conn, pinj_id)`), lalu mengunci field pokok (`self.input_pokok.setEnabled(False)`).
2. UI **mengisi otomatis perkiraan jasa 1 bulan berjalan** dengan rumus: `jasa_bln = int(round(pinj["plafon"] * pinj["jasa_persen_per_bulan"] / 100))`. Namun, field jasa **tetap aktif (enabled)** sehingga operator dapat mengubah atau mengetik manual jika ada kebijakan diskon jasa atau penyesuaian bunga.
3. Saat disimpan, karena checkbox dicentang, UI mengirim `angsuran_id = None` ke fungsi `bayar_angsuran`.

#### Kutipan Kode Asli
Lokasi: `app/ui/layar_angsuran.py:170-188`
```python
    def _mode_pelunasan_dipercepat_diubah(self) -> None:
        pinj_id = self.combo_pinjaman.currentData()
        if not pinj_id:
            return

        if self.chk_pelunasan_dipercepat.isChecked():
            sisa_pokok = hitung_sisa_pokok_pinjaman(self.conn, pinj_id)
            self.label_angsuran_target.setText("Pelunasan Dipercepat (Seluruh Sisa Pokok)")
            self.input_pokok.set_nilai(sisa_pokok)
            self.input_pokok.setEnabled(False)
            
            # Hitung perkiraan jasa 1 bulan berjalan
            pinj = ambil_pinjaman_by_id(self.conn, pinj_id)
            jasa_bln = int(round(pinj["plafon"] * pinj["jasa_persen_per_bulan"] / 100))
            self.input_jasa.set_nilai(jasa_bln)
        else:
            self.input_pokok.setEnabled(True)
            self._pinjaman_berubah()
```
Lokasi penyerahan `angsuran_id = None`: `app/ui/layar_angsuran.py:213-215`
```python
        angsuran_id = None if self.chk_pelunasan_dipercepat.isChecked() else (
            self.angsuran_aktif["id"] if self.angsuran_aktif else None
        )
```

#### Lokasi
- `app/ui/layar_angsuran.py:170-188`, `213-215`

#### Hal yang Tidak Ditemukan
- Penguncian field `input_jasa` saat pelunasan dipercepat (hanya field `input_pokok` yang di-disable; jasa tetap editable).

---

### P1.d. Apakah `bayar_pokok` atau `bayar_jasa` dibatasi terhadap tagihan angsuran tertentu (`angsuran_id`)? Apa yang terjadi jika dibayar lebih dari tagihan satu cicilan?

#### Jawaban Faktual Singkat
- **`bayar_pokok`**: **TIDAK DIBATASI TERHADAP TAGIHAN CICILAN TERTENTU**. Pembatasan yang ada di kode hanyalah terhadap total sisa pokok pinjaman secara keseluruhan (`bayar_pokok <= sisa_pokok_saat_ini`). Jika operator memasukkan bayar pokok lebih besar dari tagihan angsuran tertentu (misal tagihan pokok cicilan Rp 1.000.000, tapi dibayar Rp 2.500.000), kode tetap memprosesnya secara valid asalkan tidak melebihi sisa pokok pinjaman. Pada tabel `angsuran`, akumulasi pembayaran yang melebihi tagihan cicilan tersebut membuat baris cicilan itu berstatus `'lunas'` (`bayar_pokok >= tagihan_pokok`), namun sisa kelebihannya tidak otomatis dialokasikan ke baris `angsuran` berikutnya (karena pembayaran tercatat melekat pada `angsuran_id` tersebut).
- **`bayar_jasa`**: **TIDAK DIBATASI SAMA SEKALI** (hanya dibatasi `bayar_jasa >= 0`). Jika dibayar lebih besar dari tagihan jasa cicilan tersebut, uang diterima penuh dan masuk ke kas, tanpa ada batas maksimal.

#### Kutipan Kode Asli
Lokasi: `app/db/repo_angsuran.py:186-190`
```python
    # Cek sisa pokok keseluruhan
    sisa_pokok_saat_ini = hitung_sisa_pokok_pinjaman(conn, pinjaman_id)
    if bayar_pokok > sisa_pokok_saat_ini:
        raise ValueError(
            f"Pembayaran pokok ({format_rupiah(bayar_pokok)}) melebihi sisa pokok pinjaman ({format_rupiah(sisa_pokok_saat_ini)})."
        )
```

#### Lokasi
- `app/db/repo_angsuran.py:186-190`

#### Hal yang Tidak Ditemukan
- Pengecekan `bayar_pokok > tagihan_pokok_angsuran_ini`: **TIDAK DITEMUKAN**.
- Pengecekan `bayar_jasa > tagihan_jasa_angsuran_ini`: **TIDAK DITEMUKAN**.
- Alokasi otomatis sisa kelebihan bayar pokok ke angsuran berikutnya: **TIDAK DITEMUKAN**.

---

## P2. DENDA

### P2.a. Dari mana nilai denda berasal: dihitung otomatis (cari rumusnya) atau diketik operator? Cek juga nilai default di UI (`layar_angsuran.py`).

#### Jawaban Faktual Singkat
Nilai denda **DIKETIK MANUAL OLEH OPERATOR**. **TIDAK ADA RUMUS ATAU KALKULASI OTOMATIS DENDA DI SELURUH KODE**.
Nilai default di UI `layar_angsuran.py` adalah **0**.

#### Kutipan Kode Asli
Lokasi: `app/ui/layar_angsuran.py:83-88`
```python
        # Denda (opsional)
        self.input_denda = InputRupiah(self, placeholder="0")
        self.input_denda.setMinimumHeight(40)
        self.input_denda.set_nilai(0)
        self.input_denda.textChanged.connect(self._hitung_total_bayar)
        form_layout.addRow("Denda (Rp):", self.input_denda)
```

#### Lokasi
- `app/ui/layar_angsuran.py:83-88`

#### Hal yang Tidak Ditemukan
- Fungsi atau rumus perhitungan persentase/nominal denda otomatis berdasarkan jumlah hari terlambat: **TIDAK DITEMUKAN** di seluruh folder `app/logika/`, `app/db/`, maupun `app/ui/`.

---

### P2.b. Di `kas_transaksi`, denda masuk ke baris yang sama dengan pokok dan jasa (`masuk = total_bayar`)?

#### Jawaban Faktual Singkat
**YA**. Di tabel `kas_transaksi`, denda disatukan ke dalam satu baris transaksi arus kas masuk bersama dengan `bayar_pokok` dan `bayar_jasa`, di mana kolom `masuk` diisi nilai `total_bayar = bayar_pokok + bayar_jasa + denda` dengan `sumber = 'angsuran'`.

#### Kutipan Kode Asli
Lokasi: `app/db/repo_angsuran.py:157, 206-218`
```python
    total_bayar = bayar_pokok + bayar_jasa + denda
    ...
        # 2. Catat kas masuk otomatis
        ket_kas = f"Angsuran pinjaman {pinj['no_pinjaman']} ({pinj['nama_anggota']})"
        if ket_bersih:
            ket_kas += f" - {ket_bersih}"
        
        conn.execute(
            """
            INSERT INTO kas_transaksi 
            (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
            VALUES (?, ?, ?, 0, 'angsuran', ?, ?);
            """,
            (tanggal, ket_kas, total_bayar, bayar_id, periode)
        )
```

#### Lokasi
- `app/db/repo_angsuran.py:157, 206-218`

#### Hal yang Tidak Ditemukan
- Pemisahan baris kas tersendiri khusus pendapatan denda di tabel `kas_transaksi`: **TIDAK DITEMUKAN**.

---

### P2.c. Di laporan mingguan, bulanan, tahunan, dan ringkasan: denda ditampilkan sebagai baris sendiri, digabung ke jasa/pendapatan, atau tidak muncul terpisah? Salin kueri SQL-nya.

#### Jawaban Faktual Singkat
1. **Laporan Mingguan SP**: Denda **MUNCUL SEBAGAI BARIS SENDIRI** (`total_angsuran_denda`). Nilainya dipecah oleh mesin `app/logika/transaksi_efektif.py` dengan membaca tabel `pembayaran_angsuran`.
2. **Laporan Bulanan SP**: Denda **TIDAK MUNCUL TERPISAH SEBAGAI BARIS TERSENDIRI**. Denda hanya ikut terakumulasi di dalam total arus kas masuk (`total_kas_masuk`) dan total angsuran masuk pada kas, tetapi pada rincian pinjaman bulanan yang dilaporkan hanya pokok dan jasa.
3. **Laporan Tahunan SP**: Denda **TIDAK MUNCUL TERPISAH**. Laporan tahunan hanya menampilkan kolom Pokok, Jasa, Total Kas Masuk, Total Kas Keluar. Denda hanya terserap di dalam Total Kas Masuk.
4. **Layar Ringkasan (Dashboard)**: Denda **TIDAK MUNCUL TERPISAH**. Kartu ringkasan harian hanya menampilkan kartu "Angsuran Masuk Hari Ini" yang merupakan akumulasi pokok + jasa + denda.
5. **Closing Bulanan**: Tabel `closing` hanya memiliki kolom `total_jasa_diterima`, denda **TIDAK DICATAT TERPISAH** dalam snapshot closing.

#### Kutipan Kueri SQL Asli
Pemecahan denda dari referensi pembayaran angsuran di `app/logika/transaksi_efektif.py:224-271`:
```python
    cur.execute("SELECT id, bayar_pokok, bayar_jasa, denda, membalik_id FROM pembayaran_angsuran;")
    pa_rows = {r[0]: dict(r) for r in cur.fetchall()}
    ...
        elif sumber == "angsuran":
            # Alokasikan pokok, jasa, denda dari referensi pembayaran_angsuran
            pa = pa_rows.get(ref_id)
            if pa:
                angsuran_pokok_bersih += pa["bayar_pokok"]
                angsuran_jasa_bersih += pa["bayar_jasa"]
                angsuran_denda_bersih += pa["denda"]
```
Pengambilan di Laporan Mingguan (`app/db/repo_laporan.py:91-94`):
```python
        "total_angsuran_pokok": rekap["angsuran_pokok"],
        "total_angsuran_jasa": rekap["angsuran_jasa"],
        "total_angsuran_denda": rekap["angsuran_denda"],
        "total_angsuran_masuk": rekap["angsuran_total"],
```
Kueri Laporan Bulanan SP (`app/db/repo_laporan_periode.py:155-170`), denda tidak di-SELECT terpisah:
```python
    cur.execute("""
        SELECT 
            COALESCE(SUM(pa.bayar_pokok), 0) AS pokok_masuk,
            COALESCE(SUM(pa.bayar_jasa), 0) AS jasa_masuk
        FROM v_pembayaran_angsuran_efektif pa
        WHERE pa.status_efektif = 'NORMAL' AND pa.tanggal >= ? AND pa.tanggal <= ?;
    """, (tgl_awal, tgl_akhir))
    r_angs = cur.fetchone()
    angsuran_pokok_masuk = r_angs["pokok_masuk"] if r_angs else 0
    angsuran_jasa_masuk = r_angs["jasa_masuk"] if r_angs else 0
```

#### Lokasi
- `app/logika/transaksi_efektif.py:224-271`
- `app/db/repo_laporan.py:91-94`
- `app/db/repo_laporan_periode.py:155-170`

#### Hal yang Tidak Ditemukan
- Kolom denda pada tabel `closing` dan kueri laporan bulanan/tahunan: **TIDAK DITEMUKAN**.

---

### P2.d. Hal yang sama untuk `biaya_admin`: bagaimana ia muncul di laporan?

#### Jawaban Faktual Singkat
- Saat pinjaman dicairkan dengan biaya admin > 0, biaya admin dicatat ke `kas_transaksi` sebagai baris kas tersendiri dengan `sumber = 'biaya_admin'` (`app/db/repo_pinjaman.py:161-168`).
- **Laporan Mingguan SP**: Muncul sebagai baris sendiri: `"total_biaya_admin": rekap["biaya_admin"]` (`app/db/repo_laporan.py:96`).
- **Laporan Bulanan SP**: Muncul sebagai baris sendiri pada rincian pinjaman: `"biaya_admin": biaya_admin_bulan` (`app/db/repo_laporan_periode.py:172-179, 220`), dihitung dari `SUM(biaya_admin)` pinjaman cair pada bulan tersebut.
- **Layar Ringkasan**: Muncul di data metrik kas harian (`rekap_hari_ini["biaya_admin"]`).
- **Laporan Tahunan SP**: Tidak memiliki kolom khusus biaya admin, tetapi nilainya masuk ke kolom "Total Kas Masuk".
- **Closing Bulanan SP**: Tidak memiliki kolom snapshot khusus biaya admin (biaya admin masuk ke `total_kas_masuk` dan `saldo_kas_akhir`).

#### Kutipan Kueri SQL Asli
Pencatatan kas saat pencairan (`app/db/repo_pinjaman.py:161-168`):
```python
        # Kas masuk (biaya admin)
        if p["biaya_admin"] > 0:
            conn.execute(
                """
                INSERT INTO kas_transaksi (tanggal, keterangan, masuk, keluar, sumber, ref_id, periode)
                VALUES (?, ?, ?, 0, 'biaya_admin', ?, ?);
                """,
                (tanggal_cair, f"Biaya admin pinjaman {p['no_pinjaman']} - {p['nama_anggota']}", p["biaya_admin"], pinjaman_id, periode)
            )
```
Kueri Laporan Bulanan SP (`app/db/repo_laporan_periode.py:172-179`):
```python
    cur.execute("""
        SELECT COUNT(id) AS jml, COALESCE(SUM(plafon), 0) AS total_plafon, COALESCE(SUM(biaya_admin), 0) AS total_admin
        FROM pinjaman
        WHERE status IN ('aktif', 'lunas') AND tanggal_cair >= ? AND tanggal_cair <= ?;
    """, (tgl_awal, tgl_akhir))
    r_cair = cur.fetchone()
    biaya_admin_bulan = r_cair["total_admin"] if r_cair else 0
```

#### Lokasi
- `app/db/repo_pinjaman.py:161-168`
- `app/db/repo_laporan.py:96`
- `app/db/repo_laporan_periode.py:172-179, 220`

#### Hal yang Tidak Ditemukan
- Kolom biaya admin di tabel `closing`: **TIDAK DITEMUKAN**.

---

## P3. TARIK SIMPANAN DAN ANGGOTA KELUAR

### P3.a. Salin validasi arah 'tarik' di `tambah_transaksi_simpanan`. Apakah ada pembedaan aturan antara jenis pokok, wajib, dan sukarela, atau semuanya hanya dicek terhadap saldo jenisnya?

#### Jawaban Faktual Singkat
Validasi arah `'tarik'` **HANYA MEMERIKSA KECUKUPAN SALDO TERHADAP JENIS SIMPANAN ITU SENDIRI** (`jumlah > saldo_jenis`). **TIDAK ADA PEMBEDAAN ATURAN BISNIS KHUSUS** di kode antara simpanan pokok, wajib, maupun sukarela (misalnya: tidak ada larangan menarik simpanan pokok/wajib sebelum keluar, tidak ada syarat anggota harus berstatus keluar dulu). Siapa pun dan jenis simpanan apa pun dapat ditarik selama `jumlah <= saldo_jenis`.

#### Kutipan Kode Asli
Lokasi: `app/db/repo_simpanan.py:91-98`
```python
    # Cek kecukupan saldo jika penarikan
    if arah == "tarik":
        saldo_saat_ini = hitung_saldo_simpanan_anggota(conn, anggota_id)
        saldo_jenis = saldo_saat_ini.get(jenis, 0)
        if jumlah > saldo_jenis:
            raise ValueError(
                f"Saldo simpanan {jenis} tidak mencukupi. Saldo saat ini: {format_rupiah(saldo_jenis)}"
            )
```

#### Lokasi
- `app/db/repo_simpanan.py:91-98`

#### Hal yang Tidak Ditemukan
- Aturan pembatasan penarikan khusus simpanan pokok atau simpanan wajib (seperti syarat status anggota keluar atau persetujuan pengurus): **TIDAK DITEMUKAN**.

---

### P3.b. Salin `set_status_anggota`. Apakah ada pengecekan pinjaman aktif, tunggakan, atau saldo simpanan yang belum ditarik saat anggota di-set 'keluar'? Bagaimana UI menanganinya (cek `layar_anggota.py`)?

#### Jawaban Faktual Singkat
1. Pada fungsi `set_status_anggota` di database repositori: **TIDAK ADA PENGECEKAN PINJAMAN AKTIF, TUNGGAKAN, MAUPUN SALDO SIMPANAN SAMA SEKALI**. Fungsi langsung mengeksekusi `UPDATE anggota SET status = ?, tanggal_keluar = ?`.
2. Di UI `layar_anggota.py`: UI **HANYA MENAMPILKAN DIALOG KONFIRMASI TEKS BIASA** (`QMessageBox.question`) tanpa melakukan validasi terhadap pinjaman atau saldo simpanan anggota.

#### Kutipan Kode Asli
Lokasi: `app/db/repo_anggota.py:112-135`
```python
def set_status_anggota(
    conn: sqlite3.Connection,
    anggota_id: int,
    status: str,
    tanggal_keluar: Optional[str] = None
) -> None:
    """Mengubah status anggota ('aktif' atau 'keluar')."""
    if status not in ("aktif", "keluar"):
        raise ValueError("Status harus 'aktif' atau 'keluar'.")

    with conn:
        conn.execute(
            """
            UPDATE anggota
            SET status = ?, tanggal_keluar = ?
            WHERE id = ?;
            """,
            (status, tanggal_keluar if status == "keluar" else None, anggota_id)
        )
        conn.execute(
            "INSERT INTO log_aktivitas (aksi, tabel, ref_id, detail) VALUES (?, ?, ?, ?);",
            ("ubah", "anggota", anggota_id, f"Ubah status anggota menjadi {status}")
        )
```
Penanganan di UI `app/ui/layar_anggota.py:321-337`:
```python
        status_lama = anggota["status"]
        status_baru = "keluar" if status_lama == "aktif" else "aktif"
        tgl_hari_ini = datetime.now().strftime("%Y-%m-%d") if status_baru == "keluar" else None

        pesan = (
            f"Ubah status '{anggota['nama']}' menjadi '{status_baru.upper()}'?"
            if status_baru == "aktif"
            else f"Nonaktifkan '{anggota['nama']}' (status keluar)? Anggota yang keluar tidak bisa mengambil pinjaman baru."
        )

        jawaban = QMessageBox.question(
            self, "Konfirmasi Status", pesan,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if jawaban == QMessageBox.StandardButton.Yes:
            set_status_anggota(self.conn, anggota_id, status=status_baru, tanggal_keluar=tgl_hari_ini)
            self.muat_data()
```

#### Lokasi
- `app/db/repo_anggota.py:112-135`
- `app/ui/layar_anggota.py:321-337`

#### Hal yang Tidak Ditemukan
- Pengecekan saldo simpanan atau pinjaman aktif sebelum mengubah status anggota menjadi `'keluar'`: **TIDAK DITEMUKAN** (hanya ada pengecekan transaksi pada saat *menghapus* anggota secara permanen di `hapus_anggota_jika_tanpa_transaksi`).

---

### P3.c. Setelah anggota 'keluar', apakah transaksi baru (simpanan, pinjaman, angsuran) masih bisa dibuat atas namanya? Jelaskan per jenis transaksi.

#### Jawaban Faktual Singkat
1. **Pinjaman Baru**:
   - **TIDAK BISA**. Di repositori `ajukan_pinjaman` (`app/db/repo_pinjaman.py:72-75`) dicek ketat: `if not ang or ang["status"] != "aktif": raise ValueError("Anggota peminjam tidak aktif atau tidak dapat meminjam.")`. Selain itu, dropdown di UI `DialogPinjamanBaru` (`app/ui/layar_pinjaman.py:173`) hanya memuat `status_filter="aktif"`.
2. **Transaksi Simpanan**:
   - **Di Database Repositori**: Fungsi `tambah_transaksi_simpanan` (`app/db/repo_simpanan.py:102`) hanya memeriksa `if not anggota: raise ValueError(...)`, **TIDAK MEMERIKSA STATUS ANGGOTA**.
   - **Di UI**: Dropdown anggota pada `DialogInputSimpanan` (`app/ui/layar_simpanan.py:120`) memanggil `ambil_daftar_anggota(self.conn, status_filter="aktif", limit=500)`. Sehingga anggota berstatus `'keluar'` **tidak muncul di pilihan dropdown UI**.
3. **Pembayaran Angsuran**:
   - **BISA DIBAYAR**. Pilihan pembayaran angsuran didasarkan pada pinjaman yang sedang berjalan (`pinjaman.status = 'aktif'`). Jika anggota memiliki pinjaman aktif sebelum di-set keluar, pinjamannya tetap muncul di dropdown `DialogInputAngsuran` (`app/ui/layar_angsuran.py:131`), dan fungsi `bayar_angsuran` (`app/db/repo_angsuran.py:166-184`) tidak memblokir status anggota yang keluar, sehingga pelunasan cicilan pinjaman tetap dapat diselesaikan.

#### Kutipan Kode Asli
Pengecekan pinjaman aktif (`app/db/repo_pinjaman.py:72-75`):
```python
    cur.execute("SELECT nama, status FROM anggota WHERE id = ?;", (anggota_id,))
    ang = cur.fetchone()
    if not ang or ang["status"] != "aktif":
        raise ValueError("Anggota peminjam tidak aktif atau tidak dapat meminjam.")
```
Dropdown simpanan hanya memuat aktif (`app/ui/layar_simpanan.py:120`):
```python
        daftar = ambil_daftar_anggota(self.conn, status_filter="aktif", limit=500)
```

#### Lokasi
- `app/db/repo_pinjaman.py:72-75`
- `app/ui/layar_simpanan.py:120`
- `app/db/repo_simpanan.py:101-106`
- `app/ui/layar_angsuran.py:131`

#### Hal yang Tidak Ditemukan
- Pengecekan status `anggota.status == 'aktif'` di dalam fungsi repositori `tambah_transaksi_simpanan` dan `bayar_angsuran`: **TIDAK DITEMUKAN** (hanya dibatasi di level filter UI dropdown).

---

## P4. STOCK OPNAME: HARGA PATOKAN NOL

### P4.a. Salin kode penentuan `harga_satuan_dasar` di `repo_opname_toko.py` (sekitar baris 148-157) dan kode finalisasi selisih lebih yang membuat lot baru.

#### Jawaban Faktual Singkat
Kode mencari harga beli terakhir dari tabel `pembelian_detail JOIN pembelian_faktur`. Jika tidak ada riwayat faktur beli, nilai `hrg_patokan` menjadi `0`. Saat finalisasi selisih lebih, `total_biaya_lebih` dihitung dari `selisih_qty * hrg_dasar` (yang bernilai 0 jika patokan 0), lalu memanggil `tambah_stok_masuk(..., total_biaya=total_biaya_lebih)`.

#### Kutipan Kode Asli
Penentuan harga patokan (`app/db/repo_opname_toko.py:145-160`):
```python
            # Cari harga satuan dasar patokan (harga beli terakhir atau harga jual)
            cur.execute(
                """
                SELECT (pd.harga_per_satuan_input / pd.isi_per_satuan) AS hrg_beli
                FROM pembelian_detail pd
                JOIN pembelian_faktur pf ON pd.faktur_id = pf.id
                WHERE pd.barang_id = ?
                ORDER BY pf.tanggal DESC, pf.id DESC LIMIT 1;
                """,
                (b_id,)
            )
            row_hrg = cur.fetchone()
            hrg_patokan = row_hrg[0] if (row_hrg and row_hrg[0]) else 0

            selisih_nilai = selisih_qty * hrg_patokan
```
Kode finalisasi selisih lebih membuat lot baru (`app/db/repo_opname_toko.py:246-263`):
```python
            elif selisih_qty > 0:
                # Selisih lebih: buat lot stok baru
                hrg_dasar = ob["harga_satuan_dasar"]
                total_biaya_lebih = selisih_qty * hrg_dasar
                tambah_stok_masuk(
                    conn=conn,
                    barang_id=b_id,
                    qty=selisih_qty,
                    total_biaya=total_biaya_lebih,
                    asal="penyesuaian",
                    ref_tabel="opname",
                    ref_id=sesi_id,
                    tanggal=tgl,
                    harga_jual_satuan_dasar=0
                )
                tot_lebih_qty += selisih_qty
                tot_lebih_nilai += total_biaya_lebih
```

#### Lokasi
- `app/db/repo_opname_toko.py:145-160`
- `app/db/repo_opname_toko.py:246-263`

#### Hal yang Tidak Ditemukan
- Fallback ke `barang.harga_jual` jika harga beli di `pembelian_detail` tidak ditemukan (meskipun komentar baris 145 menyebut *"harga beli terakhir atau harga jual"*, kueri SQL hanya memeriksa `pembelian_detail`).

---

### P4.b. Jika harga patokan = 0: berapa `total_biaya_awal` dan `harga_jual_satuan_dasar` lot yang terbentuk? Saat barang dari lot itu dijual di kasir, berapa HPP dan laba yang tercatat?

#### Jawaban Faktual Singkat
1. **Pada `lot_stok` yang terbentuk**:
   - `total_biaya_awal = 0` (karena `selisih_qty * 0 = 0`).
   - `biaya_sisa = 0`.
   - `harga_jual_satuan_dasar = 0` (karena dipanggil dengan default `0`).
2. **Saat barang dijual di kasir**:
   - **HPP yang tercatat = Rp 0** (karena alokasi biaya FIFO dari lot tersebut adalah `0`).
   - **Laba yang tercatat = 100% dari total penjualan baris** (`laba = subtotal_baris - 0 = subtotal_baris`).

#### Kutipan Kode Asli
Lokasi HPP dan Laba kasir (`app/db/repo_penjualan.py:205-207`):
```python
            # Hitung HPP total dari alokasi lot
            hpp_total = sum(m["biaya"] for m in mutasi_fifo)
            laba_baris = subtotal_baris - hpp_total
```

#### Lokasi
- `app/db/repo_opname_toko.py:249-260`
- `app/db/repo_penjualan.py:205-207`

#### Hal yang Tidak Ditemukan
- Penanganan khusus pembagian/penetapan HPP minimum jika `total_biaya_awal == 0`.

---

### P4.c. Apakah ada peringatan atau validasi di UI untuk kasus harga patokan 0?

#### Jawaban Faktual Singkat
**TIDAK ADA PERINGATAN ATAU VALIDASI DI UI UNTUK KASUS HARGA PATOKAN 0**.
Pada `LayarOpnameToko` (`app/ui/layar_opname_toko.py:195-235`), antarmuka hanya memuat data dan kolom `Harga Satuan` serta `Selisih (Rp)` langsung menampilkan angka Rp 0 tanpa dialog konfirmasi atau peringatan teks merah. Tombol finalisasi opname juga mengeksekusi langsung tanpa memeriksa apakah ada barang dengan harga patokan Rp 0.

#### Kutipan Kode Asli
Lokasi: `app/ui/layar_opname_toko.py:205-208`
```python
            self.tbl_barang.setItem(idx, 4, QTableWidgetItem(str(r["selisih_qty"])))
            self.tbl_barang.setItem(idx, 5, QTableWidgetItem(format_rupiah(r["harga_satuan_dasar"])))
            self.tbl_barang.setItem(idx, 6, QTableWidgetItem(format_rupiah(r["selisih_nilai"])))
```

#### Lokasi
- `app/ui/layar_opname_toko.py:195-255`

#### Hal yang Tidak Ditemukan
- Validasi `if harga_satuan_dasar == 0:` atau peringatan di `app/ui/layar_opname_toko.py`: **TIDAK DITEMUKAN**.

---

### P4.d. Untuk selisih kurang: nilai kerugian dihitung dari mana (biaya lot FIFO atau harga patokan)?

#### Jawaban Faktual Singkat
Nilai kerugian selisih kurang saat finalisasi opname **DIHITUNG DARI BIAYA LOT FIFO SEBENARNYA** (`biaya_ambil` dari `lot_stok` terlama yang dipotong melalui `kurangi_stok_fifo`), **BUKAN DARI HARGA PATOKAN ESTIMASI DRAFT**.
Nilai `selisih_nilai` di draft awal hanyalah perkalian estimasi, tetapi saat dieksekusi finalisasi, kode memanggil `kurangi_stok_fifo(jenis_mutasi="penyesuaian_opname")` dan menjumlahkan `nilai_hilang = sum(h["biaya"] for h in hasil)`.

#### Kutipan Kode Asli
Lokasi: `app/db/repo_opname_toko.py:233-244`
```python
            if selisih_qty < 0:
                # Selisih kurang: kurangi stok lot FIFO terlama
                qty_hilang = abs(selisih_qty)
                hasil = kurangi_stok_fifo(
                    conn=conn,
                    barang_id=b_id,
                    qty_diminta=qty_hilang,
                    jenis_mutasi="penyesuaian_opname",
                    ref_tabel="opname",
                    ref_id=sesi_id,
                    tanggal=tgl
                )
                nilai_hilang = sum(h["biaya"] for h in hasil)
                tot_kurang_qty += qty_hilang
                tot_kurang_nilai += nilai_hilang
```

#### Lokasi
- `app/db/repo_opname_toko.py:233-244`

#### Hal yang Tidak Ditemukan
- Penggunaan `harga_satuan_dasar` pada selisih kurang saat finalisasi (hanya digunakan untuk selisih lebih).

---

## P5. STOK MINUS

### P5.a. Salin bagian `layanan_stok.py` yang membaca `izinkan_stok_minus` dan jalur kode ketika nilainya '1'.

#### Jawaban Faktual Singkat
Bagian yang membaca adalah `cek_izinkan_stok_minus()` yang memeriksa nilai konfigurasi `'izinkan_stok_minus'` pada tabel `pengaturan`. Ketika bernilai `'1'`, kondisi penolakan stok (`stok_saat_ini < qty_diminta and not izinkan_minus`) dilewati, dan bagian kuantitas yang tidak dapat dipenuhi oleh lot aktif dicatat sebagai mutasi stok tanpa lot (`lot_id = NULL`, `biaya = 0`).

#### Kutipan Kode Asli
Lokasi pembaca konfigurasi: `app/layanan/layanan_stok.py:21-27`
```python
def cek_izinkan_stok_minus(conn: sqlite3.Connection) -> bool:
    """Mengecek apakah pengaturan sistem mengizinkan stok minus."""
    cur = conn.cursor()
    cur.execute("SELECT nilai FROM pengaturan WHERE kunci = 'izinkan_stok_minus';")
    row = cur.fetchone()
    return row is not None and row[0] in ("1", "true", "True")
```
Jalur kode ketika bernilai `'1'` (diizinkan minus): `app/layanan/layanan_stok.py:242-265`
```python
    # Jika masih ada sisa_perlu dan diizinkan minus
    if sisa_perlu > 0 and izinkan_minus:
        # Catat mutasi stok minus tanpa lot (lot_id=None, biaya=0)
        cur_m = conn.execute(
            """
            INSERT INTO mutasi_stok (
                barang_id, lot_id, tanggal, jenis, qty, biaya,
                ref_tabel, ref_id, periode
            ) VALUES (?, NULL, ?, ?, ?, 0, ?, ?, ?);
            """,
            (
                barang_id, tanggal, jenis_mutasi, -sisa_perlu,
                ref_tabel, ref_id, periode
            )
        )
        mutasi_id = cur_m.lastrowid
        hasil_mutasi.append({
            "lot_id": None,
            "qty": sisa_perlu,
            "biaya": 0,
            "mutasi_id": mutasi_id
        })
        total_qty_berkurang += sisa_perlu
```

#### Lokasi
- `app/layanan/layanan_stok.py:21-27`, `242-265`

#### Hal yang Tidak Ditemukan
- Pembuatan lot fiktif negatif di tabel `lot_stok` (kode sengaja mengisi `lot_id = NULL`).

---

### P5.b. Jika diizinkan dan stok kurang: lot apa yang dibuat atau dipakai, berapa HPP bagian yang minus, dan apa nilai `barang.stok_saat_ini`? Bagaimana constraint `qty_sisa >= 0` pada `lot_stok` diperlakukan?

#### Jawaban Faktual Singkat
1. **Lot yang dibuat / dipakai**: **TIDAK ADA LOT YANG DIBUAT**. Lot yang ada dihabiskan sampai `qty_sisa = 0`. Bagian kekurangan kuantitas dicatat dengan `lot_id = NULL` di tabel `mutasi_stok`.
2. **HPP bagian yang minus**: **Rp 0** (`biaya = 0` pada entri mutasi dan HPP baris).
3. **Nilai `barang.stok_saat_ini`**: Nilai kolom di-update menjadi **BILANGAN NEGATIF** (`stok_saat_ini = stok_saat_ini - total_qty_berkurang`), karena kolom `stok_saat_ini` pada tabel `barang` bertipe `INTEGER NOT NULL DEFAULT 0` tanpa *CHECK constraint* `>= 0`.
4. **Constraint `qty_sisa >= 0` pada `lot_stok`**: **TIDAK DILANGGAR** karena tabel `lot_stok` tidak pernah di-insert atau di-update dengan nilai minus. Constraint `CHECK (qty_sisa >= 0)` tetap terpenuhi karena lot yang habis berhenti di angka `0`.

#### Kutipan Kode Asli
Lokasi update stok menjadi negatif (`app/layanan/layanan_stok.py:267-270`):
```python
    # Update cache stok_saat_ini
    conn.execute(
        "UPDATE barang SET stok_saat_ini = stok_saat_ini - ? WHERE id = ?;",
        (total_qty_berkurang, barang_id)
    )
```

#### Lokasi
- `app/layanan/layanan_stok.py:242-270`
- `app/db/skema_toko.py:65` (DDL `barang`)

#### Hal yang Tidak Ditemukan
- Lot bertanda negatif di `lot_stok`: **TIDAK DITEMUKAN**.

---

### P5.c. Ketika barang kemudian dibeli, bagaimana kekurangan tersebut ditutup? Apakah ada penyesuaian HPP penjualan sebelumnya?

#### Jawaban Faktual Singkat
1. **Penutupan Kekurangan**: Saat faktur pembelian masuk, fungsi `tambah_stok_masuk` (`app/layanan/layanan_stok.py:50-120`) membuat `lot_stok` baru dengan `qty_sisa = qty_beli` penuh dan menambahkan cache stok: `stok_saat_ini = stok_saat_ini + qty_beli`. Contoh: jika sebelumnya stok `-5` dan dibeli `20`, maka stok menjadi `15`. Namun, `lot_stok` baru tersebut tetap tercatat memiliki `qty_sisa = 20`.
2. **Penyesuaian HPP Penjualan Sebelumnya**: **TIDAK ADA PENYESUAIAN HPP SAMA SEKALI**. Penjualan yang sudah tercatat dengan HPP 0 tidak pernah di-update kembali.
3. **Dampak pada Rekonsiliasi**: Karena `lot_stok` baru tercatat `qty_sisa = 20` sedangkan `stok_saat_ini = 15`, maka terjadi selisih antara sisa lot (`20`) dengan `stok_saat_ini` (`15`). Hal ini akan terdeteksi sebagai selisih rekonsiliasi pada fungsi `rekonsiliasi_stok_barang()`.

#### Kutipan Kode Asli
Lokasi: `app/layanan/layanan_stok.py:82-117`
```python
        # 1. Insert lot_stok
        cur = conn.execute(
            """
            INSERT INTO lot_stok (
                barang_id, asal, ref_tabel, ref_id, tanggal_masuk,
                supplier_id, penitip_id, qty_awal, qty_sisa,
                total_biaya_awal, biaya_sisa, harga_jual_satuan_dasar
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                barang_id, asal, ref_tabel, ref_id, tanggal,
                supplier_id, penitip_id, qty, qty,
                total_biaya, total_biaya, harga_jual_satuan_dasar
            )
        )
        lot_id = cur.lastrowid
        ...
        # 3. Update cache stok_saat_ini
        conn.execute(
            "UPDATE barang SET stok_saat_ini = stok_saat_ini + ? WHERE id = ?;",
            (qty, barang_id)
        )
```

#### Lokasi
- `app/layanan/layanan_stok.py:82-117`

#### Hal yang Tidak Ditemukan
- Mekanisme pemotongan otomatis lot baru untuk menutupi mutasi minus sebelumnya atau penyesuaian retrospektif HPP penjualan lama: **TIDAK DITEMUKAN**.

---

### P5.d. Di UI mana pengaturan ini bisa diubah?

#### Jawaban Faktual Singkat
Pengaturan ini dapat diubah di layar **Daftar Stok FIFO** (`LayarDaftarStok`), melalui tombol aksi **"Izinkan Stok Minus (Aktif/Nonaktif)"** di bagian bawah layar.

#### Kutipan Kode Asli
Lokasi: `app/ui/layar_daftar_stok.py:187-202`
```python
    def _toggle_izinkan_stok_minus(self) -> None:
        status_sekarang = cek_izinkan_stok_minus(self.conn)
        status_baru_teks = "NONAKTIFKAN (Tolak Penjualan Jika Stok Habis)" if status_sekarang else "AKTIFKAN (Bolehkan Stok Minus)"
        
        jawaban = QMessageBox.question(
            self,
            "Konfirmasi Pengaturan Stok Minus",
            f"Apakah Anda yakin ingin mengubah aturan stok minus menjadi: {status_baru_teks}?\n\n"
            "Catatan: Disarankan tetap NONAKTIF agar inventori dan HPP selalu akurat.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if jawaban == QMessageBox.StandardButton.Yes:
            atur_izinkan_stok_minus(self.conn, not status_sekarang)
            self._perbarui_label_status_minus()
```

#### Lokasi
- `app/ui/layar_daftar_stok.py:187-202`

#### Hal yang Tidak Ditemukan
- Pengaturan stok minus di layar pengaturan khusus atau menu master barang (hanya ada di LayarDaftarStok).

---

## P6. CLOSING SILANG ANTAR UNIT

### P6.a. Salin utuh fungsi `cek_periode_terkunci` beserta semua fungsi lain yang memeriksa periode terkunci.

#### Jawaban Faktual Singkat
Fungsi utama pengecekan periode terkunci adalah `cek_periode_terkunci` di `app/db/repo_simpanan.py:15-36`. Selain itu, pada saat pra-closing, fungsi `jalankan_pemeriksaan_pra_closing` (SP) dan `periksa_pra_closing_toko` (Toko) memeriksa status tabel closing masing-masing.

#### Kutipan Kode Asli
Lokasi: `app/db/repo_simpanan.py:15-36`
```python
def cek_periode_terkunci(conn: sqlite3.Connection, periode: str) -> bool:
    """Mengecek apakah periode 'YYYY-MM' sudah di-closing di simpan pinjam atau toko."""
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM closing WHERE periode = ? AND status = 'tertutup' LIMIT 1;",
        (periode,)
    )
    if cur.fetchone() is not None:
        return True

    # Cek juga closing toko
    try:
        cur.execute(
            "SELECT 1 FROM closing_toko WHERE periode = ? AND status = 'closed' LIMIT 1;",
            (periode,)
        )
        if cur.fetchone() is not None:
            return True
    except sqlite3.OperationalError:
        pass

    return False
```
Pengecekan pra-closing SP (`app/db/repo_closing.py:76-79`):
```python
    cur.execute("SELECT status FROM closing WHERE periode = ?;", (periode,))
    row_c = cur.fetchone()
    sudah_closing = bool(row_c and row_c["status"] == "tertutup")
```
Pengecekan pra-closing Toko (`app/db/repo_closing_toko.py:49-53`):
```python
    cur.execute("SELECT id, status FROM closing_toko WHERE periode = ?;", (periode,))
    row_c = cur.fetchone()
    if row_c and row_c["status"] == "closed":
        masalah.append(f"Periode {periode} sudah di-closing sebelumnya dan saat ini berstatus terkunci.")
```

#### Lokasi
- `app/db/repo_simpanan.py:15-36`
- `app/db/repo_closing.py:76-79`
- `app/db/repo_closing_toko.py:49-53`

---

### P6.b. Tabel closing mana yang diperiksa saat ada transaksi: simpanan, pinjaman, angsuran, kas SP, dan di sisi toko (penjualan, pembelian, retur, opname, kas toko)? Buat tabel: jenis transaksi | tabel closing yang diperiksa | file:baris.

#### Jawaban Faktual Singkat
Karena **SEMUA** fungsi modul transaksi memanggil fungsi tunggal `cek_periode_terkunci()`, maka **KEDUA TABEL CLOSING (`closing` SP DAN `closing_toko`) SAMA-SAMA DIPERIKSA** pada setiap transaksi di bawah ini:

| Jenis Transaksi | Tabel Closing yang Diperiksa | File:Baris Pemanggilan |
|---|---|---|
| Setor / Tarik Simpanan | `closing` DAN `closing_toko` | `app/db/repo_simpanan.py:88` |
| Pembalik Simpanan | `closing` DAN `closing_toko` | `app/db/repo_simpanan.py:180` |
| Persetujuan & Pencairan Pinjaman | `closing` DAN `closing_toko` | `app/db/repo_pinjaman.py:129` |
| Bayar Angsuran Pinjaman | `closing` DAN `closing_toko` | `app/db/repo_angsuran.py:162` |
| Pembalik Pembayaran Angsuran | `closing` DAN `closing_toko` | `app/db/repo_angsuran.py:269` |
| Kas Manual SP | `closing` DAN `closing_toko` | `app/db/repo_kas.py:31, 106` |
| Pembelian Faktur Toko | `closing` DAN `closing_toko` | `app/db/repo_pembelian.py:58` |
| Bayar Hutang Supplier Toko | `closing` DAN `closing_toko` | `app/db/repo_pembelian.py:183` |
| Pembalik Faktur Pembelian | `closing` DAN `closing_toko` | `app/db/repo_pembelian.py:258` |
| Penjualan Kasir Toko | `closing` DAN `closing_toko` | `app/db/repo_penjualan.py:137` |
| Pembatalan Nota Penjualan | `closing` DAN `closing_toko` | `app/db/repo_penjualan.py:285` |
| Pembayaran Piutang Toko | `closing` DAN `closing_toko` | `app/db/repo_piutang.py:158` |
| Pembalik Pembayaran Piutang | `closing` DAN `closing_toko` | `app/db/repo_piutang.py:246` |
| Penitipan Harian Pagi | `closing` DAN `closing_toko` | `app/db/repo_penitipan.py:49` |
| Setoran Sore Penitip | `closing` DAN `closing_toko` | `app/db/repo_penitipan.py:259` |
| Retur Supplier Toko | `closing` DAN `closing_toko` | `app/db/repo_retur_toko.py:81` |
| Retur Penjualan Konsumen | `closing` DAN `closing_toko` | `app/db/repo_retur_toko.py:293` |
| Retur Penitip Insidental | `closing` DAN `closing_toko` | `app/db/repo_retur_toko.py:225` |
| Penyesuaian Manual (Rusak/Hilang) | `closing` DAN `closing_toko` | `app/db/repo_opname_toko.py:61` |
| Sesi Baru Opname & Finalisasi | `closing` DAN `closing_toko` | `app/db/repo_opname_toko.py:94, 212` |
| Tambah Stok Masuk (Layanan Stok) | `closing` DAN `closing_toko` | `app/layanan/layanan_stok.py:77` |
| Kurangi Stok FIFO (Layanan Stok) | `closing` DAN `closing_toko` | `app/layanan/layanan_stok.py:148` |
| Balik Mutasi Stok (Layanan Stok) | `closing` DAN `closing_toko` | `app/layanan/layanan_stok.py:289` |
| Kas Toko Transaksi Langsung | `closing` DAN `closing_toko` | `app/db/repo_kas_toko.py:32, 61` |

---

### P6.c. Apakah closing toko memblokir transaksi simpan pinjam, atau closing SP memblokir transaksi toko? Tunjukkan buktinya di kode.

#### Jawaban Faktual Singkat
**YA, KEDUANYA SALING MEMBLOKIR SECARA SILANG (MUTUAL BLOCKING)**.
- Jika **Unit Toko di-closing lebih dulu**, maka transaksi simpan pinjam pada periode tersebut **IKUT TERBLOKIR**.
- Jika **Unit Simpan Pinjam di-closing lebih dulu**, maka transaksi toko pada periode tersebut **IKUT TERBLOKIR**.

#### Bukti Kode Asli
Pada fungsi `cek_periode_terkunci` (`app/db/repo_simpanan.py:15-36`):
```python
def cek_periode_terkunci(conn: sqlite3.Connection, periode: str) -> bool:
    """Mengecek apakah periode 'YYYY-MM' sudah di-closing di simpan pinjam atau toko."""
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM closing WHERE periode = ? AND status = 'tertutup' LIMIT 1;",
        (periode,)
    )
    if cur.fetchone() is not None:
        return True

    # Cek juga closing toko
    try:
        cur.execute(
            "SELECT 1 FROM closing_toko WHERE periode = ? AND status = 'closed' LIMIT 1;",
            (periode,)
        )
        if cur.fetchone() is not None:
            return True
    except sqlite3.OperationalError:
        pass

    return False
```
Karena `tambah_transaksi_simpanan`, `bayar_angsuran`, `simpan_penjualan`, dan `buat_faktur_pembelian` semuanya memanggil fungsi di atas, jika salah satu tabel closing memiliki record aktif (`status = 'tertutup'` atau `status = 'closed'`), fungsi langsung mengembalikan `True`, dan transaksi di unit mana pun akan melempar error:
`ValueError(f"Periode {periode} sudah ditutup (closing). Transaksi tidak dapat disimpan.")`.

#### Lokasi
- `app/db/repo_simpanan.py:15-36`

---

### P6.d. Apakah pembalikan (koreksi) transaksi di periode yang sudah closing diizinkan? Jika ya, di periode mana pembaliknya dicatat?

#### Jawaban Faktual Singkat
**YA, PEMBALIKAN DIIZINKAN DENGAN SYARAT TANGGAL PEMBALIK BERADA DI PERIODE BERJALAN YANG BELUM CLOSING**.
- **Transaksi Asli di Periode yang Sudah Closing**: Tetap utuh, tidak diubah, dan tidak dihapus.
- **Pencatatan Transaksi Pembalik**: **DICATAT DI PERIODE BARU** sesuai tanggal pembalik yang dimasukkan oleh operator (`periode_balik = tanggal_balik[:7]`).
- **Validasi Kode**: Kode memvalidasi bahwa `periode_balik` belum terkunci (`if cek_periode_terkunci(conn, periode_balik): raise ValueError(...)`).
- Pada mesin buku kas `app/logika/transaksi_efektif.py`, kasus ini diakomodasi sebagai *"Koreksi Lintas Periode"*: periode lama tetap terkunci dan utuh, sedangkan transaksi pembalik di periode baru dicatat sebagai penyesuaian arus kas agar saldo kas berjalan tetap akurat.
- *Catatan Pengecualian*: Pada kas manual (`app/db/repo_kas.py:102`), ada pengecekan tambahan `if tx["terkunci"] or cek_periode_terkunci(conn, tx["periode"]): raise ValueError("Periode transaksi kas ini sudah terkunci.")`, sehingga khusus kas manual tidak dapat dibalik jika periode aslinya sudah terkunci.

#### Kutipan Kode Asli
Lokasi: `app/db/repo_simpanan.py:179-182, 210`
```python
    # Pastikan tanggal pembalik berada di periode berjalan yang belum terkunci
    periode_balik = tanggal_balik[:7]
    if cek_periode_terkunci(conn, periode_balik):
        raise ValueError(f"Periode pembalik {periode_balik} sudah ditutup (closing).")
    ...
    conn.execute(
        """
        INSERT INTO simpanan_transaksi 
        (anggota_id, jenis, arah, jumlah, tanggal, keterangan, membalik_id, periode)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (anggota_id, jenis, arah_lawan, jumlah, tanggal_balik, ket_balik, transaksi_id, periode_balik)
    )
```

#### Lokasi
- `app/db/repo_simpanan.py:179-182, 210`
- `app/db/repo_angsuran.py:268-271, 307`
- `app/logika/transaksi_efektif.py:240-252`

---

## TAMBAHAN (DOKUMEN DDL DARI KODE)

Salinan pernyataan `CREATE TABLE` dan `CREATE VIEW` apa adanya dari kode sumber:

### 1. CREATE TABLE `closing`
Lokasi: `app/db/skema.py:133-146`
```sql
CREATE TABLE IF NOT EXISTS closing (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  periode TEXT NOT NULL UNIQUE,
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

### 2. CREATE TABLE `closing_saldo_anggota`
Lokasi: `app/db/skema.py:149-158`
```sql
CREATE TABLE IF NOT EXISTS closing_saldo_anggota (
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

### 3. CREATE TABLE `closing_toko`
Lokasi: `app/db/skema_modul15.py:106-125`
```sql
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
```

### 4. CREATE TABLE `closing_stok_barang`
Lokasi: `app/db/skema_modul15.py:127-135`
```sql
CREATE TABLE IF NOT EXISTS closing_stok_barang (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  closing_toko_id INTEGER NOT NULL REFERENCES closing_toko(id),
  barang_id INTEGER NOT NULL REFERENCES barang(id),
  stok_akhir_dasar INTEGER NOT NULL,
  nilai_persediaan INTEGER NOT NULL,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (closing_toko_id, barang_id)
);
```

### 5. Definisi Seluruh VIEW (`v_*_efektif`)

#### `v_simpanan_efektif`
Lokasi: `app/db/skema.py:188-195`
```sql
CREATE VIEW IF NOT EXISTS v_simpanan_efektif AS
SELECT st.*,
       CASE 
         WHEN st.id IN (SELECT membalik_id FROM simpanan_transaksi WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN st.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM simpanan_transaksi st;
```

#### `v_pembayaran_angsuran_efektif`
Lokasi: `app/db/skema.py:197-204`
```sql
CREATE VIEW IF NOT EXISTS v_pembayaran_angsuran_efektif AS
SELECT pa.*,
       CASE 
         WHEN pa.id IN (SELECT membalik_id FROM pembayaran_angsuran WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pa.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembayaran_angsuran pa;
```

#### `v_mutasi_stok_efektif`
Lokasi: `app/db/skema_toko.py:323-330`
```sql
CREATE VIEW IF NOT EXISTS v_mutasi_stok_efektif AS
SELECT m.*,
       CASE 
         WHEN m.id IN (SELECT membalik_id FROM mutasi_stok WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN m.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM mutasi_stok m;
```

#### `v_pembelian_faktur_efektif`
Lokasi: `app/db/skema_toko.py:332-339`
```sql
CREATE VIEW IF NOT EXISTS v_pembelian_faktur_efektif AS
SELECT pf.*,
       CASE 
         WHEN pf.id IN (SELECT membalik_id FROM pembelian_faktur WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pf.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembelian_faktur pf;
```

#### `v_kas_toko_efektif`
Lokasi: `app/db/skema_toko.py:341-348`
```sql
CREATE VIEW IF NOT EXISTS v_kas_toko_efektif AS
SELECT k.*,
       CASE 
         WHEN k.id IN (SELECT membalik_id FROM kas_toko_transaksi WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN k.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM kas_toko_transaksi k;
```

#### `v_penjualan_efektif`
Lokasi: `app/db/skema_toko.py:350-357`
```sql
CREATE VIEW IF NOT EXISTS v_penjualan_efektif AS
SELECT pj.*,
       CASE 
         WHEN pj.id IN (SELECT membalik_id FROM penjualan WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pj.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM penjualan pj;
```

#### `v_penitipan_efektif`
Lokasi: `app/db/skema_toko.py:359-366`
```sql
CREATE VIEW IF NOT EXISTS v_penitipan_efektif AS
SELECT pt.*,
       CASE 
         WHEN pt.id IN (SELECT membalik_id FROM penitipan WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pt.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM penitipan pt;
```

#### `v_pembayaran_piutang_efektif`
Lokasi: `app/db/skema_toko.py:368-375`
```sql
CREATE VIEW IF NOT EXISTS v_pembayaran_piutang_efektif AS
SELECT pp.*,
       CASE 
         WHEN pp.id IN (SELECT membalik_id FROM pembayaran_piutang WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pp.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembayaran_piutang pp;
```

#### `v_pembayaran_penitip_efektif`
Lokasi: `app/db/skema_toko.py:377-384`
```sql
CREATE VIEW IF NOT EXISTS v_pembayaran_penitip_efektif AS
SELECT ppen.*,
       CASE 
         WHEN ppen.id IN (SELECT membalik_id FROM pembayaran_penitip WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN ppen.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembayaran_penitip ppen;
```

#### `v_retur_supplier_efektif`
Lokasi: `app/db/skema_modul15.py:139-146`
```sql
CREATE VIEW IF NOT EXISTS v_retur_supplier_efektif AS
SELECT rs.*,
       CASE 
         WHEN rs.id IN (SELECT membalik_id FROM retur_supplier WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN rs.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM retur_supplier rs;
```

#### `v_retur_penjualan_efektif`
Lokasi: `app/db/skema_modul15.py:148-155`
```sql
CREATE VIEW IF NOT EXISTS v_retur_penjualan_efektif AS
SELECT rp.*,
       CASE 
         WHEN rp.id IN (SELECT membalik_id FROM retur_penjualan WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN rp.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM retur_penjualan rp;
```
