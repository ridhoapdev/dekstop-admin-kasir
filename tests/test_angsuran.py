"""
tests/test_angsuran.py — Unit test untuk modul Pembayaran Angsuran.
Menguji:
- Perhitungan status angsuran (lunas, sebagian, telat, belum)
- Pembayaran angsuran normal dan otomatis update status
- Bayar sebagian (status menjadi 'sebagian')
- Pelunasan dipercepat (sisa pokok dilunasi sekaligus)
- Status pinjaman berubah otomatis menjadi 'lunas'
- Validasi tidak boleh bayar pokok melebihi sisa pokok
- Transaksi pembalik pembayaran angsuran
"""
import pytest
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import tambah_anggota
from app.db.repo_pinjaman import buat_pinjaman_baru, ambil_pinjaman_by_id
from app.db.repo_angsuran import (
    hitung_status_angsuran, hitung_sisa_pokok_pinjaman,
    ambil_daftar_angsuran_dengan_status, ambil_angsuran_berikutnya_yang_harus_dibayar,
    bayar_angsuran, balik_pembayaran_angsuran
)


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_angsuran.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_hitung_status_angsuran_logika():
    # Belum jatuh tempo, belum bayar
    assert hitung_status_angsuran(1000000, 100000, 0, 0, "2026-12-14", "2026-11-14") == "belum"
    
    # Lewat jatuh tempo, belum bayar -> telat
    assert hitung_status_angsuran(1000000, 100000, 0, 0, "2026-11-10", "2026-11-14") == "telat"

    # Bayar sebagian sebelum jatuh tempo
    assert hitung_status_angsuran(1000000, 100000, 500000, 50000, "2026-12-14", "2026-11-14") == "sebagian"

    # Lunas penuh
    assert hitung_status_angsuran(1000000, 100000, 1000000, 100000, "2026-12-14", "2026-11-14") == "lunas"


def test_pembayaran_angsuran_berjalan(db_conn):
    id_ang = tambah_anggota(db_conn, "A-0001", "Pak Budi", None, None, None, None, "2026-11-01")
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_ang, 1, plafon=3000000, tenor=3,
        jasa_persen_per_bulan=1.0, biaya_admin=0, tanggal_cair="2026-11-01"
    )

    assert hitung_sisa_pokok_pinjaman(db_conn, pinj_id) == 3000000

    # Ambil cicilan berikutnya (ke-1)
    c1 = ambil_angsuran_berikutnya_yang_harus_dibayar(db_conn, pinj_id)
    assert c1 is not None
    assert c1["angsuran_ke"] == 1
    assert c1["tagihan_pokok"] == 1000000
    assert c1["tagihan_jasa"] == 30000

    # Bayar lunas angsuran ke-1
    bayar_angsuran(
        db_conn, pinjaman_id=pinj_id, angsuran_id=c1["id"],
        tanggal="2026-11-02", bayar_pokok=1000000, bayar_jasa=30000
    )

    # Cek sisa pokok berkurang jadi 2jt
    assert hitung_sisa_pokok_pinjaman(db_conn, pinj_id) == 2000000

    # Cicilan berikutnya harus angsuran ke-2
    c2 = ambil_angsuran_berikutnya_yang_harus_dibayar(db_conn, pinj_id)
    assert c2["angsuran_ke"] == 2

    # Cek kas masuk tercatat otomatis
    cur = db_conn.cursor()
    cur.execute("SELECT masuk FROM kas_transaksi WHERE sumber = 'angsuran';")
    assert cur.fetchone()[0] == 1030000


def test_bayar_sebagian(db_conn):
    id_ang = tambah_anggota(db_conn, "A-0001", "Siti", None, None, None, None, "2026-11-01")
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_ang, 1, plafon=2000000, tenor=2,
        jasa_persen_per_bulan=1.0, biaya_admin=0, tanggal_cair="2026-11-01"
    )
    c1 = ambil_angsuran_berikutnya_yang_harus_dibayar(db_conn, pinj_id)

    # Bayar baru 400.000 pokok dan 20.000 jasa (tagihan pokok 1.000.000)
    bayar_angsuran(
        db_conn, pinjaman_id=pinj_id, angsuran_id=c1["id"],
        tanggal="2026-11-05", bayar_pokok=400000, bayar_jasa=20000
    )

    daftar = ambil_daftar_angsuran_dengan_status(db_conn, pinj_id)
    assert daftar[0]["status"] == "sebagian"
    assert daftar[0]["sisa_pokok"] == 600000


def test_pelunasan_dipercepat_dan_status_lunas(db_conn):
    id_ang = tambah_anggota(db_conn, "A-0001", "Joko", None, None, None, None, "2026-11-01")
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_ang, 1, plafon=5000000, tenor=5,
        jasa_persen_per_bulan=1.0, biaya_admin=0, tanggal_cair="2026-11-01"
    )

    # Bayar lunas seluruh sisa pokok 5jt sekaligus (angsuran_id=None)
    bayar_angsuran(
        db_conn, pinjaman_id=pinj_id, angsuran_id=None,
        tanggal="2026-11-10", bayar_pokok=5000000, bayar_jasa=50000
    )

    assert hitung_sisa_pokok_pinjaman(db_conn, pinj_id) == 0

    pinj = ambil_pinjaman_by_id(db_conn, pinj_id)
    assert pinj["status"] == "lunas"
    assert pinj["tanggal_lunas"] == "2026-11-10"


def test_tolak_bayar_melebihi_sisa_pokok(db_conn):
    id_ang = tambah_anggota(db_conn, "A-0001", "Eko", None, None, None, None, "2026-11-01")
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_ang, 1, plafon=1000000, tenor=1,
        jasa_persen_per_bulan=1.0, biaya_admin=0, tanggal_cair="2026-11-01"
    )

    with pytest.raises(ValueError, match="melebihi sisa pokok"):
        bayar_angsuran(
            db_conn, pinjaman_id=pinj_id, angsuran_id=None,
            tanggal="2026-11-05", bayar_pokok=2000000, bayar_jasa=10000
        )


def test_transaksi_pembalik_pembayaran_angsuran(db_conn):
    id_ang = tambah_anggota(db_conn, "A-0001", "Dewi", None, None, None, None, "2026-11-01")
    pinj_id = buat_pinjaman_baru(
        db_conn, "P-0001", id_ang, 1, plafon=1000000, tenor=1,
        jasa_persen_per_bulan=1.0, biaya_admin=0, tanggal_cair="2026-11-01"
    )

    # Pelunasan
    b_id = bayar_angsuran(
        db_conn, pinjaman_id=pinj_id, angsuran_id=None,
        tanggal="2026-11-05", bayar_pokok=1000000, bayar_jasa=10000
    )
    assert ambil_pinjaman_by_id(db_conn, pinj_id)["status"] == "lunas"

    # Koreksi pembalik pembayaran
    balik_pembayaran_angsuran(
        db_conn, pembayaran_id=b_id, alasan="Salah transfer anggota", tanggal_balik="2026-11-06"
    )

    # Pinjaman harus kembali berstatus 'aktif' dan sisa pokok kembali 1.000.000
    pinj = ambil_pinjaman_by_id(db_conn, pinj_id)
    assert pinj["status"] == "aktif"
    assert hitung_sisa_pokok_pinjaman(db_conn, pinj_id) == 1000000

