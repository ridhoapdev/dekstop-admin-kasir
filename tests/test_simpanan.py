"""
tests/test_simpanan.py — Unit test untuk modul Simpanan.
"""
import sqlite3
import pytest
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import tambah_anggota
from app.db.repo_simpanan import (
    tambah_transaksi_simpanan, hitung_saldo_simpanan_anggota,
    balik_transaksi_simpanan, ambil_riwayat_simpanan
)


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_simpanan.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_setor_dan_hitung_saldo(db_conn):
    id_ang = tambah_anggota(
        db_conn, "A-0001", "Hasan Basri", None, None, None, None, "2026-11-01"
    )

    # Setor Pokok 100.000
    tambah_transaksi_simpanan(
        db_conn, id_ang, jenis="pokok", arah="setor", jumlah=100000, tanggal="2026-11-01"
    )
    # Setor Wajib 50.000
    tambah_transaksi_simpanan(
        db_conn, id_ang, jenis="wajib", arah="setor", jumlah=50000, tanggal="2026-11-02"
    )
    # Setor Sukarela 25.000
    tambah_transaksi_simpanan(
        db_conn, id_ang, jenis="sukarela", arah="setor", jumlah=25000, tanggal="2026-11-03"
    )

    saldo = hitung_saldo_simpanan_anggota(db_conn, id_ang)
    assert saldo["pokok"] == 100000
    assert saldo["wajib"] == 50000
    assert saldo["sukarela"] == 25000
    assert saldo["total"] == 175000

    # Cek kas_transaksi otomatis mencatat 3 setoran
    cur = db_conn.cursor()
    cur.execute("SELECT SUM(masuk), SUM(keluar) FROM kas_transaksi WHERE sumber = 'simpanan';")
    kas = cur.fetchone()
    assert kas[0] == 175000
    assert kas[1] == 0


def test_penarikan_simpanan_dan_validasi_saldo(db_conn):
    id_ang = tambah_anggota(
        db_conn, "A-0001", "Rina", None, None, None, None, "2026-11-01"
    )

    # Setor sukarela 100.000
    tambah_transaksi_simpanan(
        db_conn, id_ang, jenis="sukarela", arah="setor", jumlah=100000, tanggal="2026-11-01"
    )

    # Coba tarik 150.000 (harus gagal karena saldo tidak mencukupi)
    with pytest.raises(ValueError, match="tidak mencukupi"):
        tambah_transaksi_simpanan(
            db_conn, id_ang, jenis="sukarela", arah="tarik", jumlah=150000, tanggal="2026-11-05"
        )

    # Tarik 40.000 sukses
    tambah_transaksi_simpanan(
        db_conn, id_ang, jenis="sukarela", arah="tarik", jumlah=40000, tanggal="2026-11-05"
    )

    saldo = hitung_saldo_simpanan_anggota(db_conn, id_ang)
    assert saldo["sukarela"] == 60000
    assert saldo["total"] == 60000

    # Kas transaksi tercatat keluar 40.000
    cur = db_conn.cursor()
    cur.execute("SELECT keluar FROM kas_transaksi WHERE sumber = 'simpanan' AND keluar > 0;")
    assert cur.fetchone()[0] == 40000


def test_transaksi_pembalik_koreksi(db_conn):
    id_ang = tambah_anggota(
        db_conn, "A-0001", "Farhan", None, None, None, None, "2026-11-01"
    )

    # Salah input setor wajib 100.000
    tx_id = tambah_transaksi_simpanan(
        db_conn, id_ang, jenis="wajib", arah="setor", jumlah=100000, tanggal="2026-11-10"
    )
    assert hitung_saldo_simpanan_anggota(db_conn, id_ang)["wajib"] == 100000

    # Lakukan pembalik karena salah input
    pembalik_id = balik_transaksi_simpanan(
        db_conn, tx_id, alasan="Salah nominal oleh admin", tanggal_balik="2026-11-10"
    )

    # Saldo setelah pembalik harus kembali 0
    saldo = hitung_saldo_simpanan_anggota(db_conn, id_ang)
    assert saldo["wajib"] == 0

    # Mencoba membalik lagi transaksi yang sama harus gagal
    with pytest.raises(ValueError, match="sudah pernah dibalik"):
        balik_transaksi_simpanan(
            db_conn, tx_id, alasan="Coba balik kedua", tanggal_balik="2026-11-10"
        )

    # Mencoba membalik transaksi pembalik itu sendiri harus gagal
    with pytest.raises(ValueError, match="merupakan transaksi pembalik"):
        balik_transaksi_simpanan(
            db_conn, pembalik_id, alasan="Coba balik pembalik", tanggal_balik="2026-11-10"
        )


def test_tolak_transaksi_pada_periode_terkunci(db_conn):
    id_ang = tambah_anggota(
        db_conn, "A-0001", "Tono", None, None, None, None, "2026-10-01"
    )

    # Simulasikan closing periode 2026-10
    with db_conn:
        db_conn.execute("""
            INSERT INTO closing (
                periode, tanggal_closing, saldo_kas_awal, total_kas_masuk,
                total_kas_keluar, saldo_kas_akhir, total_simpanan,
                total_sisa_pokok_pinjaman, total_jasa_diterima, status
            ) VALUES (
                '2026-10', '2026-10-31', 0, 1000000, 500000, 500000, 1000000, 0, 0, 'tertutup'
            );
        """)

    # Mencoba transaksi di periode 2026-10 harus ditolak
    with pytest.raises(ValueError, match="sudah ditutup"):
        tambah_transaksi_simpanan(
            db_conn, id_ang, jenis="wajib", arah="setor", jumlah=50000, tanggal="2026-10-25"
        )

    # Transaksi di periode berjalan 2026-11 harus sukses
    tambah_transaksi_simpanan(
        db_conn, id_ang, jenis="wajib", arah="setor", jumlah=50000, tanggal="2026-11-01"
    )
    assert hitung_saldo_simpanan_anggota(db_conn, id_ang)["wajib"] == 50000

