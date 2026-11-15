"""
tests/test_pinjaman.py — Unit test untuk modul Pinjaman dan Jadwal Angsuran Flat.
Memenuhi ketentuan RULES.md Bab 8:
- Uji jadwal angsuran flat (termasuk pembulatan & tenor 1)
- Uji contoh minimum: plafon 10.000.000, tenor 10, jasa 1% -> pokok 1jt/bln, jasa 100rb/bln, sum(pokok) == plafon
- Uji pembulatan: plafon 1.000.000, tenor 3 -> pokok 333.333, 333.333, 333.334
- Uji tanggal jatuh tempo akhir bulan (misal 31 Januari -> 28 Februari)
- Uji atomik pembuatan pinjaman + insert tabel angsuran + kas transaksi pencairan & admin
"""
import pytest
from datetime import date
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import tambah_anggota
from app.logika.angsuran_flat import hitung_jadwal_angsuran_flat, tambah_bulan
from app.db.repo_pinjaman import (
    buat_nomor_pinjaman_berikutnya, buat_pinjaman_baru,
    ambil_pinjaman_by_id, ambil_jadwal_angsuran_pinjaman
)


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_pinjaman.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_jadwal_flat_standar_10jt_tenor_10():
    """RULES.md: plafon 10.000.000, tenor 10, jasa 1% -> pokok 1.000.000, jasa 100.000, sum == plafon"""
    jadwal = hitung_jadwal_angsuran_flat(
        plafon=10000000,
        tenor=10,
        jasa_persen_per_bulan=1.0,
        tanggal_cair_iso="2026-11-14"
    )

    assert len(jadwal) == 10
    for i, cicilan in enumerate(jadwal, start=1):
        assert cicilan["angsuran_ke"] == i
        assert cicilan["pokok"] == 1000000
        assert cicilan["jasa"] == 100000
        assert cicilan["total_angsuran"] == 1100000

    assert sum(c["pokok"] for c in jadwal) == 10000000


def test_jadwal_flat_pembulatan_1jt_tenor_3():
    """RULES.md: plafon 1.000.000 tenor 3 -> pokok 333.333, 333.333, 333.334"""
    jadwal = hitung_jadwal_angsuran_flat(
        plafon=1000000,
        tenor=3,
        jasa_persen_per_bulan=1.5,
        tanggal_cair_iso="2026-11-14"
    )

    assert len(jadwal) == 3
    assert jadwal[0]["pokok"] == 333333
    assert jadwal[1]["pokok"] == 333333
    assert jadwal[2]["pokok"] == 333334
    assert sum(c["pokok"] for c in jadwal) == 1000000


def test_jadwal_flat_tenor_1():
    """Uji tenor 1 bulan."""
    jadwal = hitung_jadwal_angsuran_flat(
        plafon=5000000,
        tenor=1,
        jasa_persen_per_bulan=2.0,
        tanggal_cair_iso="2026-11-14"
    )
    assert len(jadwal) == 1
    assert jadwal[0]["pokok"] == 5000000
    assert jadwal[0]["jasa"] == 100000
    assert jadwal[0]["total_angsuran"] == 5100000


def test_jatuh_tempo_akhir_bulan():
    """RULES.md: Tanggal jatuh tempo akhir bulan (31 Jan -> 28 Feb non-kabisat)"""
    tgl_cair = date(2027, 1, 31)
    # Tambah 1 bulan ke 31 Jan 2027 -> 28 Feb 2027
    tgl_tempo_feb = tambah_bulan(tgl_cair, 1)
    assert tgl_tempo_feb == date(2027, 2, 28)

    # Tambah 3 bulan ke 31 Jan 2027 -> 30 Apr 2027
    tgl_tempo_apr = tambah_bulan(tgl_cair, 3)
    assert tgl_tempo_apr == date(2027, 4, 30)


def test_buat_pinjaman_atomik_db(db_conn):
    id_ang = tambah_anggota(
        db_conn, "A-0001", "Pak Joko", None, None, None, None, "2026-11-01"
    )
    no_pinj = buat_nomor_pinjaman_berikutnya(db_conn)
    assert no_pinj == "P-0001"

    pinj_id = buat_pinjaman_baru(
        db_conn,
        no_pinjaman=no_pinj,
        anggota_id=id_ang,
        produk_id=1,
        plafon=10000000,
        tenor=10,
        jasa_persen_per_bulan=1.5,
        biaya_admin=50000,
        tanggal_cair="2026-11-14",
        keperluan="Modal usaha"
    )

    pinj = ambil_pinjaman_by_id(db_conn, pinj_id)
    assert pinj is not None
    assert pinj["plafon"] == 10000000
    assert pinj["status"] == "aktif"
    assert pinj["nama_anggota"] == "Pak Joko"

    # Verifikasi tabel angsuran terisi 10 baris
    angsuran = ambil_jadwal_angsuran_pinjaman(db_conn, pinj_id)
    assert len(angsuran) == 10
    assert sum(a["pokok"] for a in angsuran) == 10000000

    # Verifikasi kas_transaksi: pencairan (keluar 10jt) & admin (masuk 50rb)
    cur = db_conn.cursor()
    cur.execute("SELECT keluar FROM kas_transaksi WHERE ref_id = ? AND sumber = 'pencairan';", (pinj_id,))
    assert cur.fetchone()[0] == 10000000

    cur.execute("SELECT masuk FROM kas_transaksi WHERE ref_id = ? AND sumber = 'biaya_admin';", (pinj_id,))
    assert cur.fetchone()[0] == 50000


def test_tolak_pinjaman_anggota_nonaktif(db_conn):
    id_ang = tambah_anggota(
        db_conn, "A-0002", "Anggota Keluar", None, None, None, None, "2026-11-01"
    )
    with db_conn:
        db_conn.execute("UPDATE anggota SET status = 'keluar' WHERE id = ?;", (id_ang,))

    with pytest.raises(ValueError, match="tidak dapat meminjam"):
        buat_pinjaman_baru(
            db_conn,
            no_pinjaman="P-0002",
            anggota_id=id_ang,
            produk_id=1,
            plafon=2000000,
            tenor=6,
            jasa_persen_per_bulan=1.5,
            biaya_admin=0,
            tanggal_cair="2026-11-14"
        )

