"""
tests/test_closing.py — Unit test untuk modul Closing Bulanan dan Kunci Periode (Modul 9).
"""
import pytest
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import tambah_anggota
from app.db.repo_simpanan import tambah_transaksi_simpanan
from app.db.repo_pinjaman import buat_pinjaman_baru
from app.db.repo_angsuran import bayar_angsuran
from app.db.repo_closing import (
    jalankan_pemeriksaan_pra_closing, hitung_ringkasan_closing,
    eksekusi_closing_bulanan, buka_kembali_closing, cek_pin_closing, atur_pin_closing
)


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_closing.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_pin_keamanan_closing(db_conn):
    # Default PIN '1234'
    assert cek_pin_closing(db_conn, "1234") is True
    assert cek_pin_closing(db_conn, "0000") is False

    # Ganti PIN baru
    atur_pin_closing(db_conn, "9876")
    assert cek_pin_closing(db_conn, "1234") is False
    assert cek_pin_closing(db_conn, "9876") is True


def test_alur_closing_dan_kunci_periode(db_conn):
    periode_uji = "2026-10"
    id_a = tambah_anggota(db_conn, "A-0001", "Pak Joko", None, None, None, None, "2026-10-01")

    # Transaksi Simpanan 500rb
    tambah_transaksi_simpanan(db_conn, id_a, "pokok", "setor", 500000, tanggal="2026-10-05")

    # Pinjaman 1jt cair 10 Okt (biaya admin 20rb)
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_a, 1, plafon=1000000, tenor=2,
        jasa_persen_per_bulan=1.0, biaya_admin=20000, tanggal_cair="2026-10-10"
    )

    # Bayar angsuran ke-1 (pokok 500rb + jasa 10rb) pada 25 Okt
    bayar_angsuran(
        db_conn, pinjaman_id=pinj_id, angsuran_id=None, tanggal="2026-10-25",
        bayar_pokok=500000, bayar_jasa=10000
    )

    # 1. Jalankan pra-closing
    pra = jalankan_pemeriksaan_pra_closing(db_conn, periode_uji)
    assert pra["sudah_closing"] is False
    # Kas masuk: Simpanan 500rb + Admin 20rb + Angsuran 510rb = 1.030.000
    # Kas keluar: Pinjaman cair 1.000.000
    # Kas akhir = 30.000
    assert pra["kas_akhir"] == 30000

    # 2. Eksekusi closing bulanan
    closing_id = eksekusi_closing_bulanan(
        db_conn, periode=periode_uji, catatan="Closing Oktober", backup_dulu=False
    )
    assert closing_id > 0

    # 3. Verifikasi snapshot tersimpan
    cur = db_conn.cursor()
    cur.execute("SELECT * FROM closing WHERE id = ?;", (closing_id,))
    row_c = cur.fetchone()
    assert row_c["status"] == "tertutup"
    assert row_c["saldo_kas_akhir"] == 30000
    assert row_c["total_simpanan"] == 500000
    assert row_c["total_sisa_pokok_pinjaman"] == 500000
    assert row_c["total_jasa_diterima"] == 10000

    # Verifikasi snapshot saldo per anggota
    cur.execute("SELECT * FROM closing_saldo_anggota WHERE closing_id = ?;", (closing_id,))
    row_sa = cur.fetchone()
    assert row_sa["anggota_id"] == id_a
    assert row_sa["saldo_pokok"] == 500000
    assert row_sa["sisa_pokok_pinjaman"] == 500000

    # 4. Verifikasi transaksi periode terkunci: coba simpan transaksi di 2026-10 harus ditolak
    with pytest.raises(ValueError, match="sudah ditutup"):
        tambah_transaksi_simpanan(db_conn, id_a, "wajib", "setor", 50000, tanggal="2026-10-28")


def test_buka_kembali_closing_dengan_pin(db_conn):
    periode_uji = "2026-10"
    id_a = tambah_anggota(db_conn, "A-0001", "Pak Budi", None, None, None, None, "2026-10-01")
    tambah_transaksi_simpanan(db_conn, id_a, "pokok", "setor", 100000, tanggal="2026-10-05")

    eksekusi_closing_bulanan(db_conn, periode=periode_uji, backup_dulu=False)

    # Salah PIN harus gagal
    with pytest.raises(ValueError, match="PIN otorisasi"):
        buka_kembali_closing(db_conn, periode_uji, pin="salah", alasan="Koreksi data")

    # Buka kembali dengan PIN benar
    sukses = buka_kembali_closing(db_conn, periode_uji, pin="1234", alasan="Koreksi setor pokok Budi")
    assert sukses is True

    cur = db_conn.cursor()
    cur.execute("SELECT status FROM closing WHERE periode = ?;", (periode_uji,))
    assert cur.fetchone()[0] == "dibuka_kembali"

    # Sekarang transaksi di periode 2026-10 boleh kembali dilakukan
    tx_id = tambah_transaksi_simpanan(db_conn, id_a, "pokok", "setor", 50000, tanggal="2026-10-20")
    assert tx_id > 0

