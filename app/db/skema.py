"""
app/db/skema.py — Definisi skema tabel SQLite dan migrasi versi (PRAGMA user_version).
Sesuai DATABASE.md & RULES.md.
"""
import sqlite3

# Versi skema saat ini dinaikkan ke 3 untuk mendukung View Transaksi Efektif
SKEMA_VERSI_TERKINI = 3

DDL_SKEMA_V1 = """
-- 1. Pengaturan
CREATE TABLE IF NOT EXISTS pengaturan (
  kunci TEXT PRIMARY KEY,
  nilai TEXT NOT NULL
);

-- 2. Anggota
CREATE TABLE IF NOT EXISTS anggota (
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
CREATE INDEX IF NOT EXISTS idx_anggota_nama ON anggota(nama);

-- 3. Simpanan Transaksi
CREATE TABLE IF NOT EXISTS simpanan_transaksi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  anggota_id INTEGER NOT NULL REFERENCES anggota(id),
  jenis TEXT NOT NULL CHECK (jenis IN ('pokok','wajib','sukarela')),
  arah TEXT NOT NULL CHECK (arah IN ('setor','tarik')),
  jumlah INTEGER NOT NULL CHECK (jumlah > 0),
  tanggal TEXT NOT NULL,
  keterangan TEXT,
  membalik_id INTEGER REFERENCES simpanan_transaksi(id),
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_simp_anggota ON simpanan_transaksi(anggota_id, tanggal);
CREATE INDEX IF NOT EXISTS idx_simp_tanggal ON simpanan_transaksi(tanggal);

-- 4. Produk Pinjaman
CREATE TABLE IF NOT EXISTS produk_pinjaman (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL UNIQUE,
  jasa_persen_per_bulan REAL NOT NULL,
  tenor_min INTEGER NOT NULL DEFAULT 1,
  tenor_maks INTEGER NOT NULL DEFAULT 60,
  plafon_maks INTEGER,
  biaya_admin INTEGER NOT NULL DEFAULT 0,
  aktif INTEGER NOT NULL DEFAULT 1
);

-- 5. Pinjaman (Mendukung status 'diajukan', 'aktif', 'lunas', 'ditolak', 'batal')
CREATE TABLE IF NOT EXISTS pinjaman (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  no_pinjaman TEXT NOT NULL UNIQUE,
  anggota_id INTEGER NOT NULL REFERENCES anggota(id),
  produk_id INTEGER REFERENCES produk_pinjaman(id),
  plafon INTEGER NOT NULL CHECK (plafon > 0),
  tenor INTEGER NOT NULL CHECK (tenor > 0),
  jasa_persen_per_bulan REAL NOT NULL,
  biaya_admin INTEGER NOT NULL DEFAULT 0,
  tanggal_cair TEXT,
  status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('diajukan','aktif','lunas','ditolak','batal')),
  tanggal_lunas TEXT,
  keperluan TEXT,
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_pinjaman_anggota ON pinjaman(anggota_id, status);

-- 6. Angsuran
CREATE TABLE IF NOT EXISTS angsuran (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pinjaman_id INTEGER NOT NULL REFERENCES pinjaman(id),
  angsuran_ke INTEGER NOT NULL,
  jatuh_tempo TEXT NOT NULL,
  pokok INTEGER NOT NULL,
  jasa INTEGER NOT NULL,
  UNIQUE (pinjaman_id, angsuran_ke)
);
CREATE INDEX IF NOT EXISTS idx_angsuran_tempo ON angsuran(jatuh_tempo);

-- 7. Pembayaran Angsuran
CREATE TABLE IF NOT EXISTS pembayaran_angsuran (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pinjaman_id INTEGER NOT NULL REFERENCES pinjaman(id),
  angsuran_id INTEGER REFERENCES angsuran(id),
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
CREATE INDEX IF NOT EXISTS idx_bayar_tanggal ON pembayaran_angsuran(tanggal);
CREATE INDEX IF NOT EXISTS idx_bayar_pinjaman ON pembayaran_angsuran(pinjaman_id);

-- 8. Kas Transaksi
CREATE TABLE IF NOT EXISTS kas_transaksi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tanggal TEXT NOT NULL,
  keterangan TEXT NOT NULL,
  masuk INTEGER NOT NULL DEFAULT 0,
  keluar INTEGER NOT NULL DEFAULT 0,
  sumber TEXT NOT NULL CHECK (sumber IN ('simpanan','pencairan','angsuran','biaya_admin','manual')),
  ref_id INTEGER,
  periode TEXT NOT NULL,
  terkunci INTEGER NOT NULL DEFAULT 0,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  CHECK ((masuk > 0 AND keluar = 0) OR (keluar > 0 AND masuk = 0))
);
CREATE INDEX IF NOT EXISTS idx_kas_tanggal ON kas_transaksi(tanggal);

-- 9. Closing
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

-- 10. Closing Saldo Anggota (Snapshot)
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

-- 11. Laporan Mingguan Log
CREATE TABLE IF NOT EXISTS laporan_mingguan_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tanggal_awal TEXT NOT NULL,
  tanggal_akhir TEXT NOT NULL,
  dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (tanggal_awal, tanggal_akhir)
);

-- 12. Draft Input Form
CREATE TABLE IF NOT EXISTS draft (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  jenis_form TEXT NOT NULL,
  data_json TEXT NOT NULL,
  diperbarui_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- 13. Log Aktivitas
CREATE TABLE IF NOT EXISTS log_aktivitas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  waktu TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  aksi TEXT NOT NULL,
  tabel TEXT NOT NULL,
  ref_id INTEGER,
  detail TEXT
);

-- 14. View Transaksi Efektif
CREATE VIEW IF NOT EXISTS v_simpanan_efektif AS
SELECT st.*,
       CASE 
         WHEN st.id IN (SELECT membalik_id FROM simpanan_transaksi WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN st.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM simpanan_transaksi st;

CREATE VIEW IF NOT EXISTS v_pembayaran_angsuran_efektif AS
SELECT pa.*,
       CASE 
         WHEN pa.id IN (SELECT membalik_id FROM pembayaran_angsuran WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
         WHEN pa.membalik_id IS NOT NULL THEN 'PEMBALIK'
         ELSE 'NORMAL'
       END AS status_efektif
FROM pembayaran_angsuran pa;
"""

DATA_AWAL_PENGATURAN = [
    ("nama_koperasi", "Koperasi Simpan Pinjam"),
    ("pin_hash", ""),  # PIN closing default '1234' jika kosong
    ("hari_awal_minggu", "senin"),
    ("backup_folder_kedua", ""),
    ("tampilkan_transaksi_dibatalkan", "0")
]

DATA_AWAL_PRODUK = [
    ("Pinjaman Reguler", 1.5, 1, 36, 50000000, 0, 1),
    ("Pinjaman Khusus", 1.0, 1, 60, 100000000, 0, 1)
]


def inisialisasi_skema(conn: sqlite3.Connection) -> None:
    """
    Memeriksa dan mengeksekusi inisialisasi skema serta migrasi berbasis PRAGMA user_version.
    """
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version;")
    versi_sekarang = cursor.fetchone()[0]

    if versi_sekarang == 0:
        with conn:
            conn.executescript(DDL_SKEMA_V1)
            for kunci, nilai in DATA_AWAL_PENGATURAN:
                conn.execute(
                    "INSERT OR IGNORE INTO pengaturan (kunci, nilai) VALUES (?, ?);",
                    (kunci, nilai)
                )
            for nama, jasa, t_min, t_max, plafon_max, admin, aktif in DATA_AWAL_PRODUK:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO produk_pinjaman 
                    (nama, jasa_persen_per_bulan, tenor_min, tenor_maks, plafon_maks, biaya_admin, aktif)
                    VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (nama, jasa, t_min, t_max, plafon_max, admin, aktif)
                )
            conn.execute(f"PRAGMA user_version = {SKEMA_VERSI_TERKINI};")
    else:
        # Migrasi ke versi 2 jika masih versi 1
        if versi_sekarang == 1:
            conn.execute("PRAGMA foreign_keys = OFF;")
            try:
                with conn:
                    conn.execute("""
                        CREATE TABLE IF NOT EXISTS pinjaman_baru (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          no_pinjaman TEXT NOT NULL UNIQUE,
                          anggota_id INTEGER NOT NULL REFERENCES anggota(id),
                          produk_id INTEGER REFERENCES produk_pinjaman(id),
                          plafon INTEGER NOT NULL CHECK (plafon > 0),
                          tenor INTEGER NOT NULL CHECK (tenor > 0),
                          jasa_persen_per_bulan REAL NOT NULL,
                          biaya_admin INTEGER NOT NULL DEFAULT 0,
                          tanggal_cair TEXT,
                          status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('diajukan','aktif','lunas','ditolak','batal')),
                          tanggal_lunas TEXT,
                          keperluan TEXT,
                          periode TEXT NOT NULL,
                          terkunci INTEGER NOT NULL DEFAULT 0,
                          dibuat_pada TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                        );
                    """)
                    conn.execute("INSERT OR IGNORE INTO pinjaman_baru SELECT * FROM pinjaman;")
                    conn.execute("DROP TABLE pinjaman;")
                    conn.execute("ALTER TABLE pinjaman_baru RENAME TO pinjaman;")
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_pinjaman_anggota ON pinjaman(anggota_id, status);")
                    conn.execute("PRAGMA user_version = 2;")
                    versi_sekarang = 2
            finally:
                conn.execute("PRAGMA foreign_keys = ON;")

        # Migrasi ke versi 3: Buat View v_simpanan_efektif dan v_pembayaran_angsuran_efektif
        if versi_sekarang == 2:
            with conn:
                conn.execute("""
                    CREATE VIEW IF NOT EXISTS v_simpanan_efektif AS
                    SELECT st.*,
                           CASE 
                             WHEN st.id IN (SELECT membalik_id FROM simpanan_transaksi WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
                             WHEN st.membalik_id IS NOT NULL THEN 'PEMBALIK'
                             ELSE 'NORMAL'
                           END AS status_efektif
                    FROM simpanan_transaksi st;
                """)
                conn.execute("""
                    CREATE VIEW IF NOT EXISTS v_pembayaran_angsuran_efektif AS
                    SELECT pa.*,
                           CASE 
                             WHEN pa.id IN (SELECT membalik_id FROM pembayaran_angsuran WHERE membalik_id IS NOT NULL) THEN 'DIBATALKAN'
                             WHEN pa.membalik_id IS NOT NULL THEN 'PEMBALIK'
                             ELSE 'NORMAL'
                           END AS status_efektif
                    FROM pembayaran_angsuran pa;
                """)
                conn.execute(f"PRAGMA user_version = {SKEMA_VERSI_TERKINI};")
