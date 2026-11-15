"""
tests/test_impor.py — Unit test untuk modul Impor Excel (Modul 10).
"""
import pytest
from app.db.koneksi import buka_koneksi
from app.db.skema import inisialisasi_skema
from app.db.repo_anggota import ambil_anggota_by_id
from app.db.repo_simpanan import hitung_saldo_simpanan_anggota
from app.db.repo_angsuran import hitung_sisa_pokok_pinjaman
from app.layanan.impor_excel import (
    buat_template_impor_excel, validasi_file_impor, eksekusi_impor_data
)


@pytest.fixture
def db_conn(tmp_path):
    db_file = tmp_path / "test_impor.db"
    conn = buka_koneksi(db_file)
    inisialisasi_skema(conn)
    yield conn
    conn.close()


def test_buat_template_dan_validasi_file(tmp_path, db_conn):
    template_file = tmp_path / "template_koperasi.xlsx"
    path_hasil = buat_template_impor_excel(template_file)
    assert path_hasil.exists()

    # Validasi file template (yang berisi baris contoh standar)
    hasil_val = validasi_file_impor(db_conn, template_file)
    assert len(hasil_val["daftar_error"]) == 0
    assert len(hasil_val["anggota"]) == 2
    assert len(hasil_val["simpanan"]) == 2
    assert len(hasil_val["pinjaman"]) == 1
    assert hasil_val["siap_impor"] is True


def test_eksekusi_impor_ke_database(tmp_path, db_conn):
    template_file = tmp_path / "impor_uji.xlsx"
    buat_template_impor_excel(template_file)

    val = validasi_file_impor(db_conn, template_file)
    ringkasan = eksekusi_impor_data(db_conn, val, backup_dulu=False)

    assert ringkasan["anggota"] == 2
    assert ringkasan["simpanan"] == 2
    assert ringkasan["pinjaman"] == 1

    # Verifikasi data anggota tersimpan
    cur = db_conn.cursor()
    cur.execute("SELECT id, no_anggota, nama FROM anggota WHERE no_anggota = 'A-0001';")
    ang1 = cur.fetchone()
    assert ang1 is not None
    assert ang1["nama"] == "Budi Santoso"

    # Verifikasi saldo simpanan awal Budi: Pokok 100rb, Wajib 500rb, Sukarela 250rb
    saldo1 = hitung_saldo_simpanan_anggota(db_conn, ang1["id"])
    assert saldo1["pokok"] == 100000
    assert saldo1["wajib"] == 500000
    assert saldo1["sukarela"] == 250000
    assert saldo1["total"] == 850000

    # Verifikasi pinjaman berjalan Budi (Plafon 10jt, sisa pokok 7jt)
    cur.execute("SELECT id, plafon FROM pinjaman WHERE no_pinjaman = 'P-0001';")
    pinj1 = cur.fetchone()
    assert pinj1 is not None
    assert pinj1["plafon"] == 10000000
    assert hitung_sisa_pokok_pinjaman(db_conn, pinj1["id"]) == 7000000


def test_validasi_deteksi_error_baris(tmp_path, db_conn):
    import openpyxl
    file_rusak = tmp_path / "data_error.xlsx"
    wb = openpyxl.Workbook()
    
    # Sheet Anggota tanpa nama
    ws = wb.active
    ws.title = "Anggota"
    ws.append(["No Anggota", "Nama Lengkap"])
    ws.append(["A-0999", ""])  # Nama kosong

    wb.save(str(file_rusak))

    val = validasi_file_impor(db_conn, file_rusak)
    assert len(val["daftar_error"]) >= 1
    assert "Nama Anggota kosong" in val["daftar_error"][0]
    assert val["siap_impor"] is False

