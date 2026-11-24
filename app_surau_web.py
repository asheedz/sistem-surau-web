import streamlit as st
import sqlite3
from datetime import datetime, timezone, timedelta
import pandas as pd
import hashlib
import os
import shutil
import base64
import streamlit.components.v1 as components

try:
    from zoneinfo import ZoneInfo
    ZONA_MASA_MY = ZoneInfo("Asia/Kuala_Lumpur")
except Exception:
    ZONA_MASA_MY = timezone(timedelta(hours=8))

# Coding Versi 1.0
# tarikh 23/11/2026

# =========================================================================
# KONFIGURASI LAMAN (PAGE CONFIG)
# =========================================================================
st.set_page_config(
    page_title="Sistem Kewangan Surau",
    page_icon="🕌",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Pastikan folder lampiran resit wujud
UPLOAD_DIR_TUNTUTAN = "lampiran_tuntutan"
os.makedirs(UPLOAD_DIR_TUNTUTAN, exist_ok=True)

# =========================================================================
# FUNGSI MASA TEMPATAN (MALAYSIA UTC+8), CRYPTOGRAPHY & DATABASE
# =========================================================================
def masa_sekarang():
    """Mengembalikan tarikh dan masa semasa mengikut waktu tempatan Malaysia (Asia/Kuala Lumpur utc+8)."""
    return datetime.now(ZONA_MASA_MY)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def get_db_connection():
    # return sqlite3.connect('sistem_surau.db', check_same_thread=False) <-- ni coding asal
    
    def get_db_connection():
        conn = sqlite3.connect('sistem_surau.db', timeout=30.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn
    
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Users Table with status
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nama_penuh TEXT NOT NULL,
        no_telefon TEXT,
        peranan TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Aktif'
    )""")
    
    c.execute("PRAGMA table_info(users)")
    cols = [col[1] for col in c.fetchall()]
    if 'no_telefon' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN no_telefon TEXT")
    if 'status' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'Aktif'")
        c.execute("UPDATE users SET status = 'Aktif' WHERE status IS NULL")
    
    # 2. Jawatan Table
    c.execute("""CREATE TABLE IF NOT EXISTS jawatan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama_jawatan TEXT UNIQUE NOT NULL,
        boleh_ubah_data INTEGER NOT NULL DEFAULT 0,
        keterangan TEXT
    )""")
    
    default_roles = [
        ('Admin', 1, 'Akses Penuh Sistem, Pengurusan Pengguna, Jawatan & Database'),
        ('Bendahari', 1, 'Perekodan Urusniaga Kewangan, Semakan Dana Tuntutan & Baucar Bayaran'),
        ('Pengerusi', 0, 'Pengesahan Baucar & Tuntutan, Kebenaran Pindaan & Semakan Penyata'),
        ('Timbalan Pengerusi', 0, 'Pengesahan Baucar & Tuntutan, Kebenaran Pindaan & Semakan Penyata'),
        ('AJK', 0, 'Paparan Sahaja & Permohonan Tuntutan Perbelanjaan')
    ]
    for r_name, r_mod, r_desc in default_roles:
        c.execute("SELECT id FROM jawatan WHERE nama_jawatan = ?", (r_name,))
        if not c.fetchone():
            c.execute("INSERT INTO jawatan (nama_jawatan, boleh_ubah_data, keterangan) VALUES (?, ?, ?)",
                      (r_name, r_mod, r_desc))

    # Seed default users
    default_users = [
        ('admin', 'admin123', 'Pentadbir Sistem Utama', '012-3456789', 'Admin', 'Aktif'),
        ('bendahari', 'benda123', 'Hj. Ismail (Bendahari)', '013-1122334', 'Bendahari', 'Aktif'),
        ('pengerusi', 'pengerusi123', 'Dato Hj. Azman (Pengerusi)', '019-8877665', 'Pengerusi', 'Aktif'),
        ('timbalan', 'timbalan123', 'Hj. Razak (Timbalan Pengerusi)', '016-5544332', 'Timbalan Pengerusi', 'Aktif'),
        ('ajk1', 'ajk123', 'Ustaz Hamdan (AJK)', '017-9988776', 'AJK', 'Aktif')
    ]
    for u_name, u_pass, u_full, u_tel, u_role, u_stat in default_users:
        c.execute("SELECT id FROM users WHERE username = ?", (u_name,))
        if not c.fetchone():
            c.execute("INSERT INTO users (username, password_hash, nama_penuh, no_telefon, peranan, status) VALUES (?, ?, ?, ?, ?, ?)",
                      (u_name, hash_password(u_pass), u_full, u_tel, u_role, u_stat))
            
    # 3. Settings Table
    c.execute("""CREATE TABLE IF NOT EXISTS tetapan (
        id INTEGER PRIMARY KEY,
        nama_surau TEXT NOT NULL,
        alamat_surau TEXT,
        bg_image_path TEXT
    )""")
    c.execute("PRAGMA table_info(tetapan)")
    t_cols = [col[1] for col in c.fetchall()]
    if 'bg_image_path' not in t_cols:
        c.execute("ALTER TABLE tetapan ADD COLUMN bg_image_path TEXT")

    c.execute("SELECT * FROM tetapan WHERE id = 1")
    if not c.fetchone():
        c.execute("INSERT INTO tetapan (id, nama_surau, alamat_surau) VALUES (1, 'Surau An Najdah', 'Komuniti Perumahan')")
    
    # 4. Financial Years Table
    c.execute("""CREATE TABLE IF NOT EXISTS tahun_kewangan (
        tahun TEXT PRIMARY KEY,
        status TEXT NOT NULL DEFAULT 'Buka',
        ditutup_oleh TEXT,
        ditutup_pada TEXT
    )""")
    
    # 5. Categories Table
    c.execute("""CREATE TABLE IF NOT EXISTS kategori (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        jenis TEXT NOT NULL,
        nama TEXT NOT NULL UNIQUE
    )""")
    c.execute("SELECT COUNT(*) FROM kategori")
    if c.fetchone()[0] == 0:
        default_incomes = [
            "Kutipan Solat Jumaat", "Tabung Harian / Sedekah", "Sumbangan Khas Penduduk", 
            "Sumbangan Syarikat / Korporat", "Tajaan Majlis & Jamuan", "Sewa Fasiliti Surau", "Lain-lain Penerimaan"
        ]
        default_expenses = [
            "Bil Elektrik & Air", "Bil Internet / Telekomunikasi", "Saguhati Imam / Bilal / Siak", 
            "Saguhati Penceramah (Kuliah)", "Penyelenggaraan & Pembaikan", "Program / Jamuan / Aktiviti", 
            "Pembelian Barang Keperluan", "Kebersihan & Pelupusan Sampah", "Lain-lain Perbelanjaan"
        ]
        for inc in default_incomes:
            c.execute("INSERT INTO kategori (jenis, nama) VALUES ('Penerimaan (Masuk)', ?)", (inc,))
        for exp in default_expenses:
            c.execute("INSERT INTO kategori (jenis, nama) VALUES ('Perbelanjaan (Keluar)', ?)", (exp,))

    # 6. Transactions Table
    c.execute("""CREATE TABLE IF NOT EXISTS urusniaga (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarikh TEXT NOT NULL,
        bulan_tahun TEXT NOT NULL,
        jenis TEXT NOT NULL,
        kategori TEXT NOT NULL,
        butiran TEXT NOT NULL,
        amaun REAL NOT NULL,
        no_baucar TEXT,
        dicipta_oleh TEXT NOT NULL,
        dicipta_pada TEXT NOT NULL,
        dikemaskini_oleh TEXT,
        dikemaskini_pada TEXT,
        nota_kemaskini_admin TEXT
    )""")
    
    c.execute("PRAGMA table_info(urusniaga)")
    u_cols = [col[1] for col in c.fetchall()]
    if 'no_baucar' not in u_cols:
        c.execute("ALTER TABLE urusniaga ADD COLUMN no_baucar TEXT")
    if 'dikemaskini_oleh' not in u_cols:
        c.execute("ALTER TABLE urusniaga ADD COLUMN dikemaskini_oleh TEXT")
    if 'dikemaskini_pada' not in u_cols:
        c.execute("ALTER TABLE urusniaga ADD COLUMN dikemaskini_pada TEXT")
    if 'nota_kemaskini_admin' not in u_cols:
        c.execute("ALTER TABLE urusniaga ADD COLUMN nota_kemaskini_admin TEXT")

    # 7. Payment Vouchers Table (Baucar Bayaran Pra-Transaksi)
    c.execute("""CREATE TABLE IF NOT EXISTS payment_vouchers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        no_baucar TEXT UNIQUE NOT NULL,
        tarikh_baucar TEXT NOT NULL,
        nama_penerima TEXT NOT NULL,
        no_rujukan TEXT,
        kategori TEXT NOT NULL,
        butiran TEXT NOT NULL,
        amaun REAL NOT NULL,
        kaedah_bayaran TEXT NOT NULL DEFAULT 'Tunai',
        status TEXT NOT NULL DEFAULT 'Menunggu Kelulusan',
        dicipta_oleh TEXT NOT NULL,
        dicipta_pada TEXT NOT NULL,
        disahkan_oleh TEXT,
        jawatan_pengesah TEXT,
        disahkan_pada TEXT,
        catatan_pengesah TEXT,
        sebab_mohon_edit TEXT,
        dimohon_edit_oleh TEXT,
        dimohon_edit_pada TEXT,
        kebenaran_edit_oleh TEXT,
        kebenaran_edit_pada TEXT,
        dikemaskini_oleh TEXT,
        dikemaskini_pada TEXT,
        urusniaga_id INTEGER
    )""")

    # 8. Tuntutan Perbelanjaan Table (Reimbursement)
    c.execute("""CREATE TABLE IF NOT EXISTS tuntutan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        no_tuntutan TEXT UNIQUE NOT NULL,
        tarikh_tuntutan TEXT NOT NULL,
        tarikh_resit TEXT NOT NULL,
        nama_penuntut TEXT NOT NULL,
        username_penuntut TEXT NOT NULL,
        no_resit_kedai TEXT,
        kategori TEXT NOT NULL,
        butiran TEXT NOT NULL,
        amaun REAL NOT NULL,
        kaedah_bayaran_balik TEXT NOT NULL DEFAULT 'Tunai',
        maklumat_akaun_bank TEXT,
        lampiran_path TEXT,
        status TEXT NOT NULL DEFAULT 'Menunggu Semakan Bendahari',
        dicipta_oleh TEXT NOT NULL,
        dicipta_pada TEXT NOT NULL,
        disemak_oleh TEXT,
        disemak_pada TEXT,
        status_dana TEXT,
        catatan_bendahari TEXT,
        disahkan_oleh TEXT,
        jawatan_pengesah TEXT,
        disahkan_pada TEXT,
        catatan_pengesah TEXT,
        sebab_mohon_edit TEXT,
        dimohon_edit_oleh TEXT,
        dimohon_edit_pada TEXT,
        kebenaran_edit_oleh TEXT,
        kebenaran_edit_pada TEXT,
        dikemaskini_oleh TEXT,
        dikemaskini_pada TEXT,
        no_baucar_pv TEXT,
        urusniaga_id INTEGER
    )""")

    # 9. Audit Log Table
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarikh_masa TEXT NOT NULL,
        pengguna TEXT NOT NULL,
        tindakan TEXT NOT NULL,
        butiran TEXT NOT NULL
    )""")

    conn.commit()
    conn.close()

# diubah pada 23/11/2026 utk betulkan current time
def log_audit(pengguna, tindakan, butiran):
    conn = get_db_connection()
    c = conn.cursor()
    kini = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO audit_log (tarikh_masa, pengguna, tindakan, butiran) VALUES (?, ?, ?, ?)",
              (kini, pengguna, tindakan, butiran))
    conn.commit()
    conn.close()

def check_boleh_ubah_data(peranan):
    if peranan == 'Admin':
        return True
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT boleh_ubah_data FROM jawatan WHERE nama_jawatan = ?", (peranan,))
    row = c.fetchone()
    conn.close()
    if row is not None:
        return bool(row[0] == 1)
    return peranan in ['Admin', 'Bendahari']

def check_boleh_semak_tuntutan(peranan):
    """Bendahari (atau Admin) menyemak resit dan mengesahkan kecukupan dana sebelum kelulusan Pengerusi/Timbalan."""
    return peranan in ['Bendahari', 'Admin']

def check_boleh_sahkan_baucar(peranan):
    """Hanya Pengerusi atau Timbalan Pengerusi berkuasa mengesahkan baucar/tuntutan dan memberi kebenaran edit selepas kelulusan."""
    return peranan in ['Pengerusi', 'Timbalan Pengerusi']

def get_senarai_jawatan():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nama_jawatan FROM jawatan ORDER BY id ASC")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows if rows else ["Admin", "Bendahari", "Pengerusi", "Timbalan Pengerusi", "AJK"]

def get_tahun_status(tahun):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT status FROM tahun_kewangan WHERE tahun = ?", (str(tahun),))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 'Buka'

def get_nama_surau():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nama_surau FROM tetapan WHERE id = 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else "Surau An Najdah"

def get_maklumat_surau():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nama_surau, alamat_surau FROM tetapan WHERE id = 1")
    row = c.fetchone()
    conn.close()
    if row:
        return row[0], (row[1] or "")
    return "Surau An Najdah", ""

def get_baki_dana_semasa():
    """Mengira baki keseluruhan dana tabung surau semasa berdasarkan lejar urusniaga."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT SUM(amaun) FROM urusniaga WHERE jenis LIKE '%Masuk%'")
    tot_in = c.fetchone()[0] or 0.0
    c.execute("SELECT SUM(amaun) FROM urusniaga WHERE jenis LIKE '%Keluar%'")
    tot_out = c.fetchone()[0] or 0.0
    conn.close()
    return tot_in, tot_out, (tot_in - tot_out)

# diubah 23/11/2026
def jana_no_baucar_seterusnya(tahun_str=None):
    """Menjana nombor siri kawalan automatik (Auto Running Serial Number) format PV-YYYY-0001."""
    if not tahun_str:
        tahun_str = masa_sekarang().strftime("%Y")
    conn = get_db_connection()
    c = conn.cursor()
    prefix = f"PV-{tahun_str}-"
    c.execute("SELECT no_baucar FROM payment_vouchers WHERE no_baucar LIKE ?", (f"{prefix}%",))
    rows = c.fetchall()
    conn.close()
    max_seq = 0
    for (nb,) in rows:
        try:
            seq = int(nb.replace(prefix, ""))
            if seq > max_seq:
                max_seq = seq
        except ValueError:
            pass
    return f"{prefix}{max_seq + 1:04d}"
# diubah 23/11/2026
def jana_no_tuntutan_seterusnya(tahun_str=None):
    """Menjana nombor siri kawalan automatik (Auto Running Serial Number) format TNT-YYYY-0001."""
    if not tahun_str:
        tahun_str = masa_sekarang().strftime("%Y")
    conn = get_db_connection()
    c = conn.cursor()
    prefix = f"TNT-{tahun_str}-"
    c.execute("SELECT no_tuntutan FROM tuntutan WHERE no_tuntutan LIKE ?", (f"{prefix}%",))
    rows = c.fetchall()
    conn.close()
    max_seq = 0
    for (nt,) in rows:
        try:
            seq = int(nt.replace(prefix, ""))
            if seq > max_seq:
                max_seq = seq
        except ValueError:
            pass
    return f"{prefix}{max_seq + 1:04d}"

init_db()

# =========================================================================
# PENGURUSAN SESI (SESSION STATE)
# =========================================================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_info' not in st.session_state:
    st.session_state['user_info'] = None
if 'edit_trx_id' not in st.session_state:
    st.session_state['edit_trx_id'] = None
if 'delete_trx_id' not in st.session_state:
    st.session_state['delete_trx_id'] = None
if 'view_voucher_id' not in st.session_state:
    st.session_state['view_voucher_id'] = None
if 'selected_pv_id' not in st.session_state:
    st.session_state['selected_pv_id'] = None
if 'pv_form_nonce' not in st.session_state:
    st.session_state['pv_form_nonce'] = 0
if 'tnt_form_nonce' not in st.session_state:
    st.session_state['tnt_form_nonce'] = 0
if 'trx_form_nonce' not in st.session_state:
    st.session_state['trx_form_nonce'] = 0
if 'kat_edit_nonce' not in st.session_state:
    st.session_state['kat_edit_nonce'] = 0
if 'pv_success_msg' not in st.session_state:
    st.session_state['pv_success_msg'] = None
if 'tnt_success_msg' not in st.session_state:
    st.session_state['tnt_success_msg'] = None
if 'trx_success_msg' not in st.session_state:
    st.session_state['trx_success_msg'] = None

# =========================================================================
# FUNGSI BANTUAN PAPARAN CETAKAN & PENJANA PDF TULEN
# =========================================================================
def _pdf_escape(text):
    if text is None:
        text = "-"
    s = str(text)
    s = s.encode('latin-1', 'replace').decode('latin-1')
    s = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return s

def _wrap_text(text, max_chars=65):
    words = str(text or "-").split()
    lines = []
    curr = ""
    for w in words:
        if len(curr) + len(w) + 1 <= max_chars:
            curr = (curr + " " + w).strip()
        else:
            if curr:
                lines.append(curr)
            curr = w
    if curr:
        lines.append(curr)
    return lines if lines else ["-"]

def _build_single_page_pdf(ops):
    stream_str = "\n".join(ops)
    stream_bytes = stream_str.encode('latin-1')

    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>\nendobj\n")
    objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n")
    objects.append(f"6 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode('latin-1') + stream_bytes + b"\nendstream\nendobj\n")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_pos = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode('latin-1'))
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode('latin-1'))

    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF"
    pdf.extend(trailer.encode('latin-1'))
    return bytes(pdf)

def generate_pv_pdf_bytes(pv_data, nama_surau, alamat_surau=""):
    ops = []
    ops.append("1.5 w")
    ops.append("0.12 0.30 0.17 RG")
    ops.append("36 36 523 770 re S")
    ops.append("0.12 0.30 0.17 rg")
    ops.append("36 735 523 71 re f")
    ops.append("1 1 1 rg")
    ops.append("BT /F2 16 Tf 50 778 Td (" + _pdf_escape(nama_surau.upper()) + ") Tj ET")
    if alamat_surau:
        ops.append("BT /F1 9 Tf 50 762 Td (" + _pdf_escape(alamat_surau[:85]) + ") Tj ET")
    ops.append("BT /F2 12 Tf 50 744 Td (BAUCAR BAYARAN / PAYMENT VOUCHER) Tj ET")
    
    ops.append("0 0 0 rg")
    ops.append("0.95 0.97 0.95 rg")
    ops.append("50 675 495 48 re f")
    ops.append("0.75 0.82 0.77 RG 0.8 w")
    ops.append("50 675 495 48 re S")
    
    ops.append("0.12 0.30 0.17 rg")
    ops.append("BT /F2 11 Tf 60 704 Td (NO. SIRI BAUCAR: " + _pdf_escape(pv_data['no_baucar']) + ") Tj ET")
    ops.append("0 0 0 rg")
    ops.append("BT /F1 10 Tf 350 704 Td (Tarikh Baucar: " + _pdf_escape(pv_data['tarikh_baucar']) + ") Tj ET")
    ops.append("BT /F2 10 Tf 60 686 Td (Status Kelulusan: " + _pdf_escape(pv_data['status'].upper()) + ") Tj ET")
    ops.append("BT /F1 10 Tf 350 686 Td (Kaedah Bayaran: " + _pdf_escape(pv_data['kaedah_bayaran']) + ") Tj ET")
    
    y = 645
    fields = [
        ("Dibayar Kepada (Penerima):", pv_data['nama_penerima']),
        ("No. Rujukan / Invois / Bil:", pv_data['no_rujukan'] if pv_data['no_rujukan'] else "-"),
        ("Kategori Perbelanjaan:", pv_data['kategori']),
    ]
    for lbl, val in fields:
        ops.append("0.25 0.25 0.25 rg")
        ops.append(f"BT /F2 10 Tf 50 {y} Td ({_pdf_escape(lbl)}) Tj ET")
        ops.append("0 0 0 rg")
        ops.append(f"BT /F1 10 Tf 215 {y} Td ({_pdf_escape(val[:65])}) Tj ET")
        ops.append("0.85 0.85 0.85 RG 0.5 w")
        ops.append(f"215 {y - 4} m 545 {y - 4} l S")
        y -= 28

    ops.append("0.25 0.25 0.25 rg")
    ops.append(f"BT /F2 10 Tf 50 {y} Td ({_pdf_escape('Maksud / Butiran Bayaran:')}) Tj ET")
    butiran_lines = _wrap_text(pv_data['butiran'], max_chars=58)
    for line in butiran_lines[:4]:
        ops.append("0 0 0 rg")
        ops.append(f"BT /F1 10 Tf 215 {y} Td ({_pdf_escape(line)}) Tj ET")
        ops.append("0.85 0.85 0.85 RG 0.5 w")
        ops.append(f"215 {y - 4} m 545 {y - 4} l S")
        y -= 22

    y -= 18
    ops.append("0.94 0.97 0.95 rg")
    ops.append(f"50 {y - 34} 495 46 re f")
    ops.append("0.12 0.30 0.17 RG 1.2 w")
    ops.append(f"50 {y - 34} 495 46 re S")
    ops.append("0.12 0.30 0.17 rg")
    ops.append(f"BT /F2 10 Tf 62 {y - 5} Td (JUMLAH BAYARAN YANG DILULUSKAN / DIPOHON:) Tj ET")
    ops.append(f"BT /F2 16 Tf 62 {y - 25} Td (RM {pv_data['amaun']:,.2f}) Tj ET")

    y -= 65
    ops.append("0.98 0.98 0.96 rg")
    ops.append(f"50 {y - 68} 495 78 re f")
    ops.append("0.7 0.7 0.7 RG 0.6 w")
    ops.append(f"50 {y - 68} 495 78 re S")
    ops.append("0.12 0.30 0.17 rg")
    ops.append(f"BT /F2 10 Tf 60 {y - 5} Td (REKOD KAWALAN & PENGESAHAN DIGITAL) Tj ET")
    ops.append("0 0 0 rg")
    ops.append(f"BT /F1 9 Tf 60 {y - 22} Td ({_pdf_escape('Disediakan Oleh: ' + pv_data['dicipta_oleh'] + ' (' + pv_data['dicipta_pada'] + ')')}) Tj ET")
    
    if pv_data.get('disahkan_oleh'):
        pengesah_txt = f"Disahkan / Diluluskan Oleh: {pv_data['disahkan_oleh']} [{pv_data.get('jawatan_pengesah', '')}] pada {pv_data.get('disahkan_pada', '')}"
        ops.append("0.05 0.38 0.12 rg")
        ops.append(f"BT /F2 9 Tf 60 {y - 38} Td ({_pdf_escape(pengesah_txt[:88])}) Tj ET")
    else:
        ops.append("0.75 0.15 0.10 rg")
        ops.append(f"BT /F2 9 Tf 60 {y - 38} Td (Status Pengesahan: BELUM DISAHKAN OLEH PENGERUSI / TIMBALAN PENGERUSI) Tj ET")

    if pv_data.get('kebenaran_edit_oleh'):
        edit_txt = f"Kebenaran Edit Diluluskan Oleh: {pv_data['kebenaran_edit_oleh']} ({pv_data.get('kebenaran_edit_pada', '')})"
        ops.append("0.2 0.2 0.2 rg")
        ops.append(f"BT /F1 8.5 Tf 60 {y - 54} Td ({_pdf_escape(edit_txt[:90])}) Tj ET")

    sig_y = 115
    ops.append("0 0 0 RG 0.8 w")
    ops.append(f"55 {sig_y} m 195 {sig_y} l S")
    ops.append("0 0 0 rg")
    ops.append(f"BT /F2 9 Tf 75 {sig_y - 14} Td (Disediakan Oleh) Tj ET")
    ops.append(f"BT /F1 8.5 Tf 82 {sig_y - 26} Td ((Bendahari)) Tj ET")
    
    ops.append(f"220 {sig_y} m 375 {sig_y} l S")
    ops.append(f"BT /F2 9 Tf 245 {sig_y - 14} Td (Disahkan & Diluluskan) Tj ET")
    ops.append(f"BT /F1 8 Tf 222 {sig_y - 26} Td ((Pengerusi / Timbalan Pengerusi)) Tj ET")

    ops.append(f"400 {sig_y} m 540 {sig_y} l S")
    ops.append(f"BT /F2 9 Tf 430 {sig_y - 14} Td (Diterima Oleh) Tj ET")
    ops.append(f"BT /F1 8.5 Tf 425 {sig_y - 26} Td ((Penerima Bayaran)) Tj ET")

    ops.append("0.45 0.45 0.45 rg")
    ops.append(f"BT /F1 8 Tf 50 50 Td ({_pdf_escape('Dokumen janaan sistem kewangan rasmi. Dicetak pada: ' + datetime.now().strftime('%d/%m/%Y %H:%M'))}) Tj ET")

    return _build_single_page_pdf(ops)

def generate_tuntutan_pdf_bytes(tnt_data, nama_surau, alamat_surau=""):
    """Menjana fail PDF tulen bagi Borang Tuntutan Perbelanjaan (Reimbursement Form)."""
    ops = []
    ops.append("1.5 w")
    ops.append("0.12 0.30 0.17 RG")
    ops.append("36 36 523 770 re S")
    ops.append("0.12 0.30 0.17 rg")
    ops.append("36 735 523 71 re f")
    ops.append("1 1 1 rg")
    ops.append("BT /F2 16 Tf 50 778 Td (" + _pdf_escape(nama_surau.upper()) + ") Tj ET")
    if alamat_surau:
        ops.append("BT /F1 9 Tf 50 762 Td (" + _pdf_escape(alamat_surau[:85]) + ") Tj ET")
    ops.append("BT /F2 12 Tf 50 744 Td (BORANG TUNTUTAN PERBELANJAAN / REIMBURSEMENT CLAIM) Tj ET")

    ops.append("0 0 0 rg")
    ops.append("0.95 0.97 0.95 rg")
    ops.append("50 675 495 48 re f")
    ops.append("0.75 0.82 0.77 RG 0.8 w")
    ops.append("50 675 495 48 re S")

    ops.append("0.12 0.30 0.17 rg")
    ops.append("BT /F2 11 Tf 60 704 Td (NO. SIRI TUNTUTAN: " + _pdf_escape(tnt_data['no_tuntutan']) + ") Tj ET")
    ops.append("0 0 0 rg")
    ops.append("BT /F1 10 Tf 350 704 Td (Tarikh Tuntutan: " + _pdf_escape(tnt_data['tarikh_tuntutan']) + ") Tj ET")
    ops.append("BT /F2 9.5 Tf 60 686 Td (Status: " + _pdf_escape(tnt_data['status'].upper()) + ") Tj ET")
    ops.append("BT /F1 10 Tf 350 686 Td (Tarikh Resit: " + _pdf_escape(tnt_data['tarikh_resit']) + ") Tj ET")

    y = 645
    fields = [
        ("Nama Penuntut (Ahli / AJK):", tnt_data['nama_penuntut']),
        ("No. Resit / Bil Pembelian:", tnt_data['no_resit_kedai'] if tnt_data['no_resit_kedai'] else "-"),
        ("Kategori Perbelanjaan:", tnt_data['kategori']),
        ("Kaedah Bayaran Balik:", f"{tnt_data['kaedah_bayaran_balik']} {('(' + tnt_data['maklumat_akaun_bank'] + ')') if tnt_data.get('maklumat_akaun_bank') else ''}".strip()),
    ]
    for lbl, val in fields:
        ops.append("0.25 0.25 0.25 rg")
        ops.append(f"BT /F2 10 Tf 50 {y} Td ({_pdf_escape(lbl)}) Tj ET")
        ops.append("0 0 0 rg")
        ops.append(f"BT /F1 10 Tf 215 {y} Td ({_pdf_escape(val[:65])}) Tj ET")
        ops.append("0.85 0.85 0.85 RG 0.5 w")
        ops.append(f"215 {y - 4} m 545 {y - 4} l S")
        y -= 26

    ops.append("0.25 0.25 0.25 rg")
    ops.append(f"BT /F2 10 Tf 50 {y} Td ({_pdf_escape('Butiran / Maksud Perbelanjaan:')}) Tj ET")
    butiran_lines = _wrap_text(tnt_data['butiran'], max_chars=58)
    for line in butiran_lines[:3]:
        ops.append("0 0 0 rg")
        ops.append(f"BT /F1 10 Tf 215 {y} Td ({_pdf_escape(line)}) Tj ET")
        ops.append("0.85 0.85 0.85 RG 0.5 w")
        ops.append(f"215 {y - 4} m 545 {y - 4} l S")
        y -= 21

    y -= 14
    ops.append("0.94 0.97 0.95 rg")
    ops.append(f"50 {y - 34} 495 46 re f")
    ops.append("0.12 0.30 0.17 RG 1.2 w")
    ops.append(f"50 {y - 34} 495 46 re S")
    ops.append("0.12 0.30 0.17 rg")
    ops.append(f"BT /F2 10 Tf 62 {y - 5} Td (JUMLAH TUNTUTAN BAYARAN BALIK (RM):) Tj ET")
    ops.append(f"BT /F2 16 Tf 62 {y - 25} Td (RM {tnt_data['amaun']:,.2f}) Tj ET")
    if tnt_data.get('no_baucar_pv'):
        ops.append(f"BT /F2 9.5 Tf 350 {y - 22} Td (Rujukan Baucar: {_pdf_escape(tnt_data['no_baucar_pv'])}) Tj ET")

    # Rekod Semakan Dana Bendahari & Pengesahan Pengerusi
    y -= 62
    ops.append("0.98 0.98 0.96 rg")
    ops.append(f"50 {y - 82} 495 92 re f")
    ops.append("0.7 0.7 0.7 RG 0.6 w")
    ops.append(f"50 {y - 82} 495 92 re S")
    ops.append("0.12 0.30 0.17 rg")
    ops.append(f"BT /F2 10 Tf 60 {y - 5} Td (REKOD SEMAKAN DANA BENDAHARI & PENGESAHAN KELULUSAN) Tj ET")
    ops.append("0 0 0 rg")
    ops.append(f"BT /F1 9 Tf 60 {y - 21} Td ({_pdf_escape('1. Permohonan Oleh: ' + tnt_data['dicipta_oleh'] + ' (' + tnt_data['dicipta_pada'] + ')')}) Tj ET")

    if tnt_data.get('disemak_oleh'):
        semak_txt = f"2. Semakan Bendahari: {tnt_data['disemak_oleh']} [{tnt_data.get('status_dana', '')}] pada {tnt_data.get('disemak_pada', '')}"
        ops.append("0.05 0.35 0.55 rg")
        ops.append(f"BT /F2 9 Tf 60 {y - 37} Td ({_pdf_escape(semak_txt[:90])}) Tj ET")
    else:
        ops.append("0.75 0.15 0.10 rg")
        ops.append(f"BT /F2 9 Tf 60 {y - 37} Td (2. Semakan Bendahari: BELUM DISEMAK KECUKUPAN DANA) Tj ET")

    if tnt_data.get('disahkan_oleh'):
        pengesah_txt = f"3. Kelulusan Akhir: {tnt_data['disahkan_oleh']} [{tnt_data.get('jawatan_pengesah', '')}] pada {tnt_data.get('disahkan_pada', '')}"
        ops.append("0.05 0.38 0.12 rg")
        ops.append(f"BT /F2 9 Tf 60 {y - 53} Td ({_pdf_escape(pengesah_txt[:90])}) Tj ET")
    else:
        ops.append("0.75 0.15 0.10 rg")
        ops.append(f"BT /F2 9 Tf 60 {y - 53} Td (3. Kelulusan Akhir: BELUM DISAHKAN OLEH PENGERUSI / TIMBALAN PENGERUSI) Tj ET")

    if tnt_data.get('kebenaran_edit_oleh'):
        edit_txt = f"Kebenaran Edit Diluluskan Oleh: {tnt_data['kebenaran_edit_oleh']} ({tnt_data.get('kebenaran_edit_pada', '')})"
        ops.append("0.2 0.2 0.2 rg")
        ops.append(f"BT /F1 8.5 Tf 60 {y - 69} Td ({_pdf_escape(edit_txt[:90])}) Tj ET")

    # Ruang Tandatangan 3 Pihak
    sig_y = 115
    ops.append("0 0 0 RG 0.8 w")
    ops.append(f"55 {sig_y} m 195 {sig_y} l S")
    ops.append("0 0 0 rg")
    ops.append(f"BT /F2 9 Tf 80 {sig_y - 14} Td (Dituntut Oleh) Tj ET")
    ops.append(f"BT /F1 8.5 Tf 82 {sig_y - 26} Td ((Penuntut)) Tj ET")

    ops.append(f"220 {sig_y} m 375 {sig_y} l S")
    ops.append(f"BT /F2 9 Tf 242 {sig_y - 14} Td (Disemak Dana Oleh) Tj ET")
    ops.append(f"BT /F1 8.5 Tf 262 {sig_y - 26} Td ((Bendahari)) Tj ET")

    ops.append(f"400 {sig_y} m 540 {sig_y} l S")
    ops.append(f"BT /F2 9 Tf 418 {sig_y - 14} Td (Disahkan & Diluluskan) Tj ET")
    ops.append(f"BT /F1 8 Tf 402 {sig_y - 26} Td ((Pengerusi / Timbalan Pengerusi)) Tj ET")

    ops.append("0.45 0.45 0.45 rg")
    ops.append(f"BT /F1 8 Tf 50 50 Td ({_pdf_escape('Dokumen janaan sistem kewangan rasmi. Dicetak pada: ' + datetime.now().strftime('%d/%m/%Y %H:%M'))}) Tj ET")

    return _build_single_page_pdf(ops)

def show_printable_html(html_content, file_name="dokumen.html", button_label="🖨️ Cetak / Muat Turun Penyata"):
    b64 = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
    href = f'''<a href="data:text/html;base64,{b64}" target="_blank" download="{file_name}" style="text-decoration: none;">
        <button style="background-color: #1E4C2B; color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px; cursor: pointer; margin-bottom: 15px;">
            {button_label}
        </button>
    </a>'''
    st.markdown(href, unsafe_allow_html=True)
    with st.expander("👁️ Pratonton Dokumen (Skrin)", expanded=True):
        components.html(html_content, height=680, scrolling=True)

def build_pv_html(pv_data, nama_surau, alamat_surau=""):
    is_approved = pv_data['status'] in ['Diluluskan', 'Direkod ke Lejar']
    status_badge_color = "#1E4C2B" if is_approved else ("#990000" if pv_data['status'] == 'Ditolak' else "#B45309")
    watermark_html = ""
    if not is_approved:
        watermark_html = f"""
        <div style="text-align:center; background:#FFFBEB; border:1px dashed #B45309; color:#B45309; padding:8px; font-weight:bold; margin-bottom:15px; font-size:13px;">
            ⚠️ STATUS BAUCAR: {pv_data['status'].upper()} (BELUM DISAHKAN UNTUK PEMBAYARAN RASMI)
        </div>
        """
    pengesahan_info = ""
    if pv_data.get('disahkan_oleh'):
        pengesahan_info = f"""
        <div style="background:#EAF5EA; border:1px solid #274E13; padding:10px 14px; margin-top:15px; font-size:13px; color:#1E4C2B;">
            <strong>✅ PENGESAHAN DIGITAL:</strong> Telah disahkan dan diluluskan oleh <strong>{pv_data['disahkan_oleh']}</strong>
            ({pv_data.get('jawatan_pengesah', '')}) pada <strong>{pv_data.get('disahkan_pada', '')}</strong>.
            {f"<br><em>Catatan Pengesah: {pv_data['catatan_pengesah']}</em>" if pv_data.get('catatan_pengesah') else ""}
        </div>
        """
    kebenaran_edit_info = ""
    if pv_data.get('kebenaran_edit_oleh'):
        kebenaran_edit_info = f"""
        <div style="background:#F4F6F9; border:1px solid #99A3AD; padding:8px 14px; margin-top:8px; font-size:12px; color:#333;">
            <strong>🔓 REKOD KEBENARAN PINDAAN:</strong> Kebenaran edit diluluskan oleh <strong>{pv_data['kebenaran_edit_oleh']}</strong>
            pada {pv_data.get('kebenaran_edit_pada', '')}. (Alasan: {pv_data.get('sebab_mohon_edit', '-')})
        </div>
        """
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Baucar Bayaran {pv_data['no_baucar']}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; background: #fafafa; color: #222; }}
        .box {{ max-width: 820px; margin: 0 auto; background: #fff; border: 2px solid #1E4C2B; padding: 30px; }}
        .header {{ text-align: center; border-bottom: 3px double #1E4C2B; padding-bottom: 14px; margin-bottom: 18px; }}
        .header h1 {{ margin: 0; font-size: 23px; color: #1E4C2B; text-transform: uppercase; }}
        .header p {{ margin: 3px 0; font-size: 13px; color: #555; }}
        .header h2 {{ margin: 8px 0 0 0; font-size: 16px; color: #111; letter-spacing: 0.5px; }}
        .meta-bar {{ display: flex; justify-content: space-between; background: #f4f8f5; border: 1px solid #c8d8cc; padding: 10px 15px; margin-bottom: 18px; font-size: 14px; }}
        .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; }}
        .info-table td {{ padding: 9px 6px; font-size: 14px; vertical-align: top; }}
        .label {{ font-weight: bold; width: 195px; color: #333; }}
        .val {{ border-bottom: 1px dotted #777; color: #111; }}
        .amount-panel {{ background: #f0f7f2; border: 1.5px solid #1E4C2B; padding: 14px 18px; margin: 20px 0; }}
        .amount-val {{ font-size: 24px; font-weight: bold; color: #1E4C2B; margin-top: 3px; }}
        .signatures {{ display: flex; justify-content: space-between; margin-top: 50px; }}
        .sign-box {{ width: 31%; text-align: center; }}
        .sign-line {{ border-top: 1px solid #222; margin-top: 55px; padding-top: 6px; font-weight: bold; font-size: 13px; }}
        .sign-sub {{ font-size: 11px; color: #555; font-weight: normal; margin-top: 2px; }}
        @media print {{ .btn {{ display: none; }} body {{ padding: 0; background: #fff; }} .box {{ border: 2px solid #000; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:10px 18px;border:none;cursor:pointer;border-radius:5px;margin-bottom:15px;font-weight:bold;font-size:14px;">
        🖨️ Cetak Baucar / Simpan sebagai PDF
    </button>
    <div class="box">
        <div class="header">
            <h1>{nama_surau}</h1>
            {f"<p>{alamat_surau}</p>" if alamat_surau else ""}
            <h2>BAUCAR BAYARAN / PAYMENT VOUCHER</h2>
        </div>
        {watermark_html}
        <div class="meta-bar">
            <div><strong>No. Siri Baucar:</strong> <span style="font-size:16px; color:#1E4C2B; font-weight:800;">{pv_data['no_baucar']}</span></div>
            <div><strong>Tarikh Baucar:</strong> {pv_data['tarikh_baucar']}</div>
            <div><strong>Status:</strong> <span style="color:{status_badge_color}; font-weight:bold;">{pv_data['status'].upper()}</span></div>
        </div>
        <table class="info-table">
            <tr><td class="label">Dibayar Kepada (Penerima):</td><td class="val"><strong>{pv_data['nama_penerima']}</strong></td></tr>
            <tr><td class="label">No. Rujukan / Invois / Bil:</td><td class="val">{pv_data['no_rujukan'] if pv_data['no_rujukan'] else '-'}</td></tr>
            <tr><td class="label">Kategori Perbelanjaan:</td><td class="val">{pv_data['kategori']}</td></tr>
            <tr><td class="label">Kaedah Pembayaran:</td><td class="val">{pv_data['kaedah_bayaran']}</td></tr>
            <tr><td class="label">Maksud / Butiran Bayaran:</td><td class="val">{pv_data['butiran']}</td></tr>
        </table>
        <div class="amount-panel">
            <div style="font-size: 12px; font-weight: bold; color: #1E4C2B; letter-spacing: 0.5px;">JUMLAH BAYARAN:</div>
            <div class="amount-val">RM {pv_data['amaun']:,.2f}</div>
        </div>
        {pengesahan_info}
        {kebenaran_edit_info}
        <div class="signatures">
            <div class="sign-box"><div class="sign-line">Disediakan Oleh<br>(Bendahari)<div class="sign-sub">{pv_data['dicipta_oleh']}</div></div></div>
            <div class="sign-box"><div class="sign-line">Disahkan & Diluluskan Oleh<br>(Pengerusi / Timbalan Pengerusi)<div class="sign-sub">{pv_data['disahkan_oleh'] if pv_data.get('disahkan_oleh') else 'Menunggu Pengesahan'}</div></div></div>
            <div class="sign-box"><div class="sign-line">Diterima Oleh<br>(Penerima Bayaran)<div class="sign-sub">Nama & No. K/P: ........................</div></div></div>
        </div>
        <div style="margin-top:25px; font-size:11px; color:#666; border-top:1px solid #eee; padding-top:8px; display:flex; justify-content:space-between;">
            <span>No. Kawalan Siri: {pv_data['no_baucar']}</span>
            <span>Tarikh Cetakan: {masa_sekarang().strftime("%d/%m/%Y %H:%M")}</span>
        </div>
    </div>
</body>
</html>"""

def build_tuntutan_html(tnt_data, nama_surau, alamat_surau=""):
    is_approved = tnt_data['status'] in ['Diluluskan', 'Dibayar & Direkod']
    status_badge_color = "#1E4C2B" if is_approved else ("#990000" if tnt_data['status'] == 'Ditolak' else "#B45309")
    watermark_html = ""
    if not is_approved:
        watermark_html = f"""
        <div style="text-align:center; background:#FFFBEB; border:1px dashed #B45309; color:#B45309; padding:8px; font-weight:bold; margin-bottom:15px; font-size:13px;">
            ⚠️ STATUS TUNTUTAN: {tnt_data['status'].upper()}
        </div>
        """

    semakan_info = ""
    if tnt_data.get('disemak_oleh'):
        semakan_info = f"""
        <div style="background:#EFF6FF; border:1px solid #1D4ED8; padding:10px 14px; margin-top:12px; font-size:13px; color:#1E3A8A;">
            <strong>🔍 SEMAKAN DANA BENDAHARI:</strong> Disemak oleh <strong>{tnt_data['disemak_oleh']}</strong>
            pada <strong>{tnt_data.get('disemak_pada', '')}</strong> — Status Dana: <strong>{tnt_data.get('status_dana', '')}</strong>.
            {f"<br><em>Catatan Bendahari: {tnt_data['catatan_bendahari']}</em>" if tnt_data.get('catatan_bendahari') else ""}
        </div>
        """

    pengesahan_info = ""
    if tnt_data.get('disahkan_oleh'):
        pengesahan_info = f"""
        <div style="background:#EAF5EA; border:1px solid #274E13; padding:10px 14px; margin-top:8px; font-size:13px; color:#1E4C2B;">
            <strong>✅ PENGESAHAN KELULUSAN AKHIR:</strong> Telah disahkan dan diluluskan oleh <strong>{tnt_data['disahkan_oleh']}</strong>
            ({tnt_data.get('jawatan_pengesah', '')}) pada <strong>{tnt_data.get('disahkan_pada', '')}</strong>.
            {f"<br><em>Catatan Pengesah: {tnt_data['catatan_pengesah']}</em>" if tnt_data.get('catatan_pengesah') else ""}
        </div>
        """

    kebenaran_edit_info = ""
    if tnt_data.get('kebenaran_edit_oleh'):
        kebenaran_edit_info = f"""
        <div style="background:#F4F6F9; border:1px solid #99A3AD; padding:8px 14px; margin-top:8px; font-size:12px; color:#333;">
            <strong>🔓 REKOD KEBENARAN PINDAAN:</strong> Kebenaran edit diluluskan oleh <strong>{tnt_data['kebenaran_edit_oleh']}</strong>
            pada {tnt_data.get('kebenaran_edit_pada', '')}. (Alasan: {tnt_data.get('sebab_mohon_edit', '-')})
        </div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Borang Tuntutan {tnt_data['no_tuntutan']}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; background: #fafafa; color: #222; }}
        .box {{ max-width: 820px; margin: 0 auto; background: #fff; border: 2px solid #1E4C2B; padding: 30px; }}
        .header {{ text-align: center; border-bottom: 3px double #1E4C2B; padding-bottom: 14px; margin-bottom: 18px; }}
        .header h1 {{ margin: 0; font-size: 23px; color: #1E4C2B; text-transform: uppercase; }}
        .header p {{ margin: 3px 0; font-size: 13px; color: #555; }}
        .header h2 {{ margin: 8px 0 0 0; font-size: 16px; color: #111; letter-spacing: 0.5px; }}
        .meta-bar {{ display: flex; justify-content: space-between; background: #f4f8f5; border: 1px solid #c8d8cc; padding: 10px 15px; margin-bottom: 18px; font-size: 14px; }}
        .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; }}
        .info-table td {{ padding: 9px 6px; font-size: 14px; vertical-align: top; }}
        .label {{ font-weight: bold; width: 215px; color: #333; }}
        .val {{ border-bottom: 1px dotted #777; color: #111; }}
        .amount-panel {{ background: #f0f7f2; border: 1.5px solid #1E4C2B; padding: 14px 18px; margin: 20px 0; display: flex; justify-content: space-between; align-items: center; }}
        .amount-val {{ font-size: 24px; font-weight: bold; color: #1E4C2B; margin-top: 3px; }}
        .signatures {{ display: flex; justify-content: space-between; margin-top: 50px; }}
        .sign-box {{ width: 31%; text-align: center; }}
        .sign-line {{ border-top: 1px solid #222; margin-top: 55px; padding-top: 6px; font-weight: bold; font-size: 13px; }}
        .sign-sub {{ font-size: 11px; color: #555; font-weight: normal; margin-top: 2px; }}
        @media print {{ .btn {{ display: none; }} body {{ padding: 0; background: #fff; }} .box {{ border: 2px solid #000; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:10px 18px;border:none;cursor:pointer;border-radius:5px;margin-bottom:15px;font-weight:bold;font-size:14px;">
        🖨️ Cetak Borang Tuntutan / Simpan sebagai PDF
    </button>
    <div class="box">
        <div class="header">
            <h1>{nama_surau}</h1>
            {f"<p>{alamat_surau}</p>" if alamat_surau else ""}
            <h2>BORANG TUNTUTAN PERBELANJAAN / REIMBURSEMENT CLAIM</h2>
        </div>
        {watermark_html}
        <div class="meta-bar">
            <div><strong>No. Tuntutan:</strong> <span style="font-size:16px; color:#1E4C2B; font-weight:800;">{tnt_data['no_tuntutan']}</span></div>
            <div><strong>Tarikh Tuntutan:</strong> {tnt_data['tarikh_tuntutan']}</div>
            <div><strong>Status:</strong> <span style="color:{status_badge_color}; font-weight:bold;">{tnt_data['status'].upper()}</span></div>
        </div>
        <table class="info-table">
            <tr><td class="label">Nama Penuntut (Ahli / AJK):</td><td class="val"><strong>{tnt_data['nama_penuntut']}</strong></td></tr>
            <tr><td class="label">Tarikh Resit & No. Resit Kedai:</td><td class="val">{tnt_data['tarikh_resit']} &nbsp;|&nbsp; Rujukan Resit: <strong>{tnt_data['no_resit_kedai'] or '-'}</strong></td></tr>
            <tr><td class="label">Kategori Perbelanjaan:</td><td class="val">{tnt_data['kategori']}</td></tr>
            <tr><td class="label">Kaedah Bayaran Balik:</td><td class="val">{tnt_data['kaedah_bayaran_balik']} {f"({tnt_data['maklumat_akaun_bank']})" if tnt_data.get('maklumat_akaun_bank') else ''}</td></tr>
            <tr><td class="label">Maksud / Butiran Perbelanjaan:</td><td class="val">{tnt_data['butiran']}</td></tr>
        </table>
        <div class="amount-panel">
            <div>
                <div style="font-size: 12px; font-weight: bold; color: #1E4C2B; letter-spacing: 0.5px;">JUMLAH TUNTUTAN BAYARAN BALIK:</div>
                <div class="amount-val">RM {tnt_data['amaun']:,.2f}</div>
            </div>
            {f"<div style='text-align:right; font-size:13px;'><strong>No. Baucar Bayaran (PV):</strong><br><span style='color:#1E4C2B; font-weight:bold; font-size:15px;'>{tnt_data['no_baucar_pv']}</span></div>" if tnt_data.get('no_baucar_pv') else ""}
        </div>
        {semakan_info}
        {pengesahan_info}
        {kebenaran_edit_info}
        <div class="signatures">
            <div class="sign-box"><div class="sign-line">Dituntut Oleh<br>(Penuntut)<div class="sign-sub">{tnt_data['nama_penuntut']}</div></div></div>
            <div class="sign-box"><div class="sign-line">Disemak Kecukupan Dana<br>(Bendahari)<div class="sign-sub">{tnt_data['disemak_oleh'] if tnt_data.get('disemak_oleh') else 'Menunggu Semakan'}</div></div></div>
            <div class="sign-box"><div class="sign-line">Disahkan & Diluluskan<br>(Pengerusi / Timbalan Pengerusi)<div class="sign-sub">{tnt_data['disahkan_oleh'] if tnt_data.get('disahkan_oleh') else 'Menunggu Pengesahan'}</div></div></div>
        </div>
        <div style="margin-top:25px; font-size:11px; color:#666; border-top:1px solid #eee; padding-top:8px; display:flex; justify-content:space-between;">
            <span>No. Kawalan Siri: {tnt_data['no_tuntutan']}</span>
            <span>Tarikh Cetakan: {masa_sekarang().strftime("%d/%m/%Y %H:%M")}</span>
        </div>
    </div>
</body>
</html>"""

# =========================================================================
# HALAMAN LOG MASUK
# =========================================================================
def login_page():
    WARNA_BG_LUAR = "linear-gradient(135deg, #0e2716 0%, #1E4C2B 50%, #14341E 100%)"
    WARNA_KAD_FORM = "#ffffff"
    WARNA_TEKS_LABEL = "#1E4C2B"
    WARNA_INPUT_BG = "#f4f6f4"
    WARNA_INPUT_TEKS = "#000000"
    WARNA_BORDER_INPUT = "#c2d1c5"
    
    st.markdown(f"""
        <style>
        .stApp {{ background: {WARNA_BG_LUAR} !important; }}
        div[data-testid="stForm"] {{
            background-color: {WARNA_KAD_FORM} !important;
            padding: 35px 30px !important;
            border-radius: 15px !important;
            box-shadow: 0px 10px 30px rgba(0, 0, 0, 0.45) !important;
            margin-top: 25px !important;
            border: none !important;
        }}
        div[data-testid="stTextInput"] label, div[data-testid="stTextInput"] label p {{
            color: {WARNA_TEKS_LABEL} !important; font-size: 14px !important; font-weight: 700 !important;
        }}
        div[data-testid="stTextInput"] input {{
            color: {WARNA_INPUT_TEKS} !important; background-color: {WARNA_INPUT_BG} !important;
            border: 1.5px solid {WARNA_BORDER_INPUT} !important; border-radius: 8px !important; font-size: 14px !important;
        }}
        div[data-testid="stTextInput"] input:focus {{
            border-color: #1E4C2B !important; box-shadow: 0 0 8px rgba(30, 76, 43, 0.3) !important;
        }}
        div[data-testid="stFormSubmitButton"] button {{
            background-color: #1E4C2B !important; color: #ffffff !important; border-radius: 8px !important;
            font-weight: bold !important; border: none !important; padding: 0.55rem 1rem !important;
        }}
        div[data-testid="stFormSubmitButton"] button:hover {{ background-color: #14341E !important; }}
        </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.25, 1])
    with col2:
        with st.form("login_form", clear_on_submit=False):
            st.markdown("<h1 style='text-align: center; color: #D4AF37; margin-bottom: 0;'>🕌</h1>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='text-align: center; color: #1E4C2B; margin-top: 5px; font-weight: 800;'>{get_nama_surau().upper()}</h3>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #555555; font-size: 13px; margin-bottom: 18px;'>Sistem Pengurusan Kewangan Surau</p>", unsafe_allow_html=True)
            st.markdown("<hr style='border: 0; border-top: 1px solid #e0e0e0; margin-bottom: 18px;'>", unsafe_allow_html=True)
            
            username = st.text_input("Nama Pengguna (Username)", placeholder="Masukkan username...")
            password = st.text_input("Kata Laluan (Password)", type="password", placeholder="Masukkan kata laluan & tekan ENTER...")
            
            st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("🔓 LOG MASUK SEKARANG", use_container_width=True, type="primary")
            
            if submitted:
                if username and password:
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("SELECT id, username, password_hash, nama_penuh, no_telefon, peranan, status FROM users WHERE username = ?", (username.strip(),))
                    row = c.fetchone()
                    conn.close()
                    
                    if row and row[2] == hash_password(password):
                        u_status = row[6] if len(row) > 6 and row[6] else "Aktif"
                        if u_status == "Tidak Aktif":
                            st.error("⛔ Akses Ditolak: Akaun anda berstatus 'Tidak Aktif'. Sila hubungi Pentadbir Sistem.")
                        else:
                            st.session_state['logged_in'] = True
                            st.session_state['user_info'] = {
                                "id": row[0],
                                "username": row[1],
                                "nama_penuh": row[3],
                                "no_telefon": row[4] or "Tiada No. Tel",
                                "peranan": row[5],
                                "status": u_status,
                                "can_modify": check_boleh_ubah_data(row[5]),
                                "can_review_tnt": check_boleh_semak_tuntutan(row[5]),
                                "can_approve_pv": check_boleh_sahkan_baucar(row[5]),
                                "is_admin": (row[5] == 'Admin')
                            }
                            log_audit(row[3], "LOG MASUK", f"Pengguna '{username}' ({row[5]} - {u_status}) log masuk via Web.")
                            st.rerun()
                    else:
                        st.error("Nama pengguna atau kata laluan tidak sah!")
                else:
                    st.warning("Sila masukkan username dan kata laluan.")
                    
            st.markdown(
                "<br><p style='font-size: 11px; color: #666666; text-align: center;'>"
                "Akaun hanya boleh dicapai oleh: <b>admin</b> | <b>bendahari</b> <br>"
                "<b>pengerusi</b> | <b>timbalan</b> | <b>Auditor</b>"
                "<br> Sistem Pengurusan Kewangan Musolla oleh ACID 2026 © </br>"
                "</p>",
                unsafe_allow_html=True
            )

# =========================================================================
# HALAMAN UTAMA (MAIN APP)
# =========================================================================
def main_app():
    user = st.session_state['user_info']
    nama_surau, alamat_surau = get_maklumat_surau()
    user['can_approve_pv'] = check_boleh_sahkan_baucar(user['peranan'])
    user['can_review_tnt'] = check_boleh_semak_tuntutan(user['peranan'])
    
    st.sidebar.markdown(f"## 🕌 {nama_surau}")
    st.sidebar.info(f"👤 **{user['nama_penuh']}**\n\n🎭 **Jawatan:** {user['peranan']}\n\n🟢 **Status:** {user['status']}\n\n📞 **Tel:** {user['no_telefon']}")
    
    menu = [
        "📊 Papan Pemuka & Carta",
        "🧾 Baucar Bayaran (PV)",
        "💸 Tuntutan Perbelanjaan",
        "📝 Rekod & Lejar Urusniaga",
        "🖨️ Cetak Penyata Mesyuarat",
        "⚙️ Pengurusan Kategori",
        "🔒 Log Audit & Integriti"
    ]
    if user['is_admin']:
        menu.append("🛡️ Pentadbiran Sistem")
        
    pilihan = st.sidebar.radio("Navigasi Menu", menu)
    st.sidebar.divider()
    
    with st.sidebar.expander("🔑 Tukar Kata Laluan"):
        pwd_baru = st.text_input("Kata Laluan Baharu", type="password", key="sidebar_pwd")
        if st.button("Kemaskini Kata Laluan", use_container_width=True):
            if pwd_baru and len(pwd_baru.strip()) >= 4:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(pwd_baru.strip()), user["id"]))
                conn.commit()
                conn.close()
                log_audit(user["nama_penuh"], "KESELAMATAN", "Kata laluan peribadi dikemaskini via Web.")
                st.success("Kata laluan berjaya ditukar!")
            else:
                st.warning("Kata laluan mestilah sekurang-kurangnya 4 aksara.")
                
    if st.sidebar.button("🚪 Log Keluar", use_container_width=True, type="secondary"):
        log_audit(user["nama_penuh"], "LOG KELUAR", f"Pengguna log keluar.")
        st.session_state['logged_in'] = False
        st.session_state['user_info'] = None
        st.rerun()

    if user['is_admin']:
        with st.sidebar.expander("🕌 Ubah Nama Surau"):
            nama_semasa = get_nama_surau()
            nama_baru = st.text_input("Nama Rasmi Surau:", value=nama_semasa, key="sb_nama_surau_input")
            if st.button("💾 Simpan Nama Surau", use_container_width=True, key="btn_simpan_nama_surau"):
                if nama_baru.strip():
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE tetapan SET nama_surau = ? WHERE id = 1", (nama_baru.strip(),))
                    conn.commit()
                    conn.close()
                    log_audit(user["nama_penuh"], "KEMASKINI TETAPAN", f"Nama surau ditukar kepada '{nama_baru.strip()}'")
                    st.success("Nama surau berjaya dikemaskini!")
                    st.rerun()
                else:
                    st.warning("Nama surau tidak boleh dibiarkan kosong.")

    # ---------------------------------------------------------------------
    # 1. PAPAN PEMUKA & CARTA
    # ---------------------------------------------------------------------
    if pilihan == "📊 Papan Pemuka & Carta":
        st.subheader("📊 Papan Pemuka & Ringkasan Aliran Tunai")
        conn = get_db_connection()
        
        df_months = pd.read_sql_query("SELECT DISTINCT bulan_tahun FROM urusniaga ORDER BY bulan_tahun DESC", conn)
        months_list = df_months['bulan_tahun'].tolist() if not df_months.empty else [datetime.now().strftime("%Y-%m")]
        
        df_years = pd.read_sql_query("SELECT DISTINCT SUBSTR(tarikh, 1, 4) as thn FROM urusniaga ORDER BY thn DESC", conn)
        years_list = df_years['thn'].tolist() if not df_years.empty else [datetime.now().strftime("%Y")]
        
        c1, c2, c3 = st.columns([1, 1, 2])
        mod = c1.selectbox("Mod Paparan", ["Bulanan", "Tahunan"])
        
        if mod == "Bulanan":
            period = c2.selectbox("Pilih Bulan", months_list)
            query_in = "SELECT SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Masuk%'"
            query_out = "SELECT SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Keluar%'"
            query_cat = "SELECT kategori, SUM(amaun) as jumlah FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Keluar%' GROUP BY kategori ORDER BY jumlah DESC"
            val = (period,)
            tahun_semak = period[:4]
        else:
            period = c2.selectbox("Pilih Tahun", years_list)
            query_in = "SELECT SUM(amaun) FROM urusniaga WHERE SUBSTR(tarikh, 1, 4) = ? AND jenis LIKE '%Masuk%'"
            query_out = "SELECT SUM(amaun) FROM urusniaga WHERE SUBSTR(tarikh, 1, 4) = ? AND jenis LIKE '%Keluar%'"
            query_cat = "SELECT kategori, SUM(amaun) as jumlah FROM urusniaga WHERE SUBSTR(tarikh, 1, 4) = ? AND jenis LIKE '%Keluar%' GROUP BY kategori ORDER BY jumlah DESC"
            val = (period,)
            tahun_semak = period
            
        c = conn.cursor()
        c.execute(query_in, val)
        tot_in = c.fetchone()[0] or 0.0
        c.execute(query_out, val)
        tot_out = c.fetchone()[0] or 0.0
        baki = tot_in - tot_out
        
        df_cat = pd.read_sql_query(query_cat, conn, params=val)
        
        c.execute("SELECT COUNT(*) FROM payment_vouchers WHERE status = 'Menunggu Kelulusan'")
        cnt_pv_pending = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM payment_vouchers WHERE status = 'Diluluskan' AND urusniaga_id IS NULL")
        cnt_pv_ready_lejar = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM payment_vouchers WHERE status = 'Menunggu Kebenaran Edit'")
        cnt_pv_edit_req = c.fetchone()[0] or 0

        c.execute("SELECT COUNT(*) FROM tuntutan WHERE status = 'Menunggu Semakan Bendahari'")
        cnt_tnt_semak = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM tuntutan WHERE status = 'Ditangguhkan (Dana Tidak Cukup)'")
        cnt_tnt_hold = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM tuntutan WHERE status = 'Menunggu Kelulusan Pengerusi'")
        cnt_tnt_lulus = c.fetchone()[0] or 0
        conn.close()
        
        status_thn = get_tahun_status(tahun_semak)
        if status_thn == 'Tutup':
            c3.error(f"🔒 Tahun Kewangan {tahun_semak} telah DITUTUP")
        else:
            c3.success(f"🔓 Tahun Kewangan {tahun_semak} adalah AKTIF (Buka)")

        if cnt_pv_pending > 0 or cnt_pv_ready_lejar > 0 or cnt_pv_edit_req > 0:
            st.warning(
                f"🧾 **Perhatian Baucar Bayaran:** **{cnt_pv_pending}** baucar menunggu kelulusan, "
                f"**{cnt_pv_ready_lejar}** baucar diluluskan sedia direkod ke Lejar Urusniaga, "
                f"dan **{cnt_pv_edit_req}** permohonan kebenaran edit."
            )

        if cnt_tnt_semak > 0 or cnt_tnt_hold > 0 or cnt_tnt_lulus > 0:
            st.info(
                f"💸 **Perhatian Tuntutan Perbelanjaan:** **{cnt_tnt_semak}** tuntutan menunggu semakan dana Bendahari, "
                f"**{cnt_tnt_hold}** ditangguhkan (Hold dana tidak cukup), dan **{cnt_tnt_lulus}** menunggu kelulusan Pengerusi / Timbalan Pengerusi."
            )
            
        km1, km2, km3 = st.columns(3)
        km1.metric("JUMLAH PENERIMAAN (MASUK)", f"RM {tot_in:,.2f}")
        km2.metric("JUMLAH PERBELANJAAN (KELUAR)", f"RM {tot_out:,.2f}")
        km3.metric("LEBIHAN / (KURANGAN)", f"RM {baki:,.2f}")
        
        st.divider()
        st.markdown(f"#### 📈 Graf Pecahan Perbelanjaan bagi Tempoh {period}")
        if not df_cat.empty:
            st.bar_chart(df_cat.set_index('kategori'))
        else:
            st.info("Tiada perbelanjaan direkodkan dalam tempoh ini.")
            
        st.divider()
        if st.button("🖨️ Jana & Cetak Papan Pemuka (PDF / HTML)"):
            cat_rows = df_cat.values.tolist()
            max_cat = max([r[1] for r in cat_rows], default=1.0)
            cat_bars_html = ""
            for cat, amt in cat_rows:
                pct = (amt / tot_out * 100) if tot_out > 0 else 0
                bar_w = (amt / max_cat * 100)
                cat_bars_html += f"""
                <div style="margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: bold;">
                        <span>{cat}</span>
                        <span>RM {amt:,.2f} ({pct:.1f}%)</span>
                    </div>
                    <div style="background: #e0e0e0; height: 14px; border-radius: 7px; overflow: hidden; margin-top: 3px;">
                        <div style="background: #274E13; height: 100%; width: {bar_w:.1f}%;"></div>
                    </div>
                </div>"""

            html_dash = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Penyata Papan Pemuka - {period}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; background: #fff; color: #222; }}
        .header {{ text-align: center; border-bottom: 3px double #1E4C2B; padding-bottom: 12px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 22px; color: #1E4C2B; text-transform: uppercase; }}
        .cards {{ display: flex; justify-content: space-between; margin-bottom: 25px; }}
        .card {{ width: 31%; padding: 12px; border-radius: 6px; box-sizing: border-box; text-align: center; }}
        .sign {{ display: flex; justify-content: space-between; margin-top: 60px; }}
        .sign-box {{ width: 28%; text-align: center; border-top: 1px solid #000; padding-top: 5px; font-weight: bold; font-size: 13px; }}
        @media print {{ .btn {{ display: none; }} body {{ padding: 0; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:8px 16px;border:none;cursor:pointer;border-radius:4px;margin-bottom:15px;font-weight:bold;">🖨️ Cetak / Simpan PDF</button>
    <div class="header">
        <h1>{nama_surau}</h1>
        <h3 style="margin:4px 0;">RINGKASAN PAPAN PEMUKA & STATUS KEDUDUKAN KEWANGAN</h3>
        <div>Mod: {mod} | Tempoh: {period} | Tarikh Cetakan: {masa_sekarang().strftime("%d/%m/%Y %H:%M")}</div>
    </div>
    <div class="cards">
        <div class="card" style="background:#eaf5ea; border:1px solid #274E13;">
            <div style="font-size:12px;font-weight:bold;color:#274E13;">JUMLAH PENERIMAAN (MASUK)</div>
            <div style="font-size:18px;font-weight:bold;color:#274E13;margin-top:5px;">RM {tot_in:,.2f}</div>
        </div>
        <div class="card" style="background:#fdeeee; border:1px solid #990000;">
            <div style="font-size:12px;font-weight:bold;color:#990000;">JUMLAH PERBELANJAAN (KELUAR)</div>
            <div style="font-size:18px;font-weight:bold;color:#990000;margin-top:5px;">RM {tot_out:,.2f}</div>
        </div>
        <div class="card" style="background:#eef4fd; border:1px solid #1155CC;">
            <div style="font-size:12px;font-weight:bold;color:#1155CC;">LEBIHAN / (KURANGAN) BERSIH</div>
            <div style="font-size:18px;font-weight:bold;color:#1155CC;margin-top:5px;">RM {baki:,.2f}</div>
        </div>
    </div>
    <h3 style="color:#1E4C2B;border-bottom:1px solid #ddd;padding-bottom:5px;">Pecahan Perbelanjaan Mengikut Kategori</h3>
    {cat_bars_html if cat_rows else "<p>Tiada perbelanjaan direkodkan dalam tempoh ini.</p>"}
    <div class="sign">
        <div class="sign-box">Disediakan Oleh<br>(Bendahari)</div>
        <div class="sign-box">Disemak Oleh<br>(Pemeriksa Kira-Kira)</div>
        <div class="sign-box">Disahkan Oleh<br>(Pengerusi Surau)</div>
    </div>
    <script>window.print();</script>
</body>
</html>"""
            show_printable_html(html_dash, f"Penyata_Papan_Pemuka_{period}.html")

    # ---------------------------------------------------------------------
    # 2. BAUCAR BAYARAN (PAYMENT VOUCHER - PRA-TRANSAKSI & KAWALAN)
    # ---------------------------------------------------------------------
    elif pilihan == "🧾 Baucar Bayaran (PV)":
        st.subheader("🧾 Pengurusan Baucar Bayaran (Payment Voucher)")
        st.caption(
            "Aliran Kerja: (1) Bendahari jana baucar bayaran di sini -> (2) Pengerusi / Timbalan Pengerusi mengesahkan baucar -> "
            "(3) Bendahari merujuk No. Baucar di modul **📝 Rekod & Lejar Urusniaga** untuk merekod transaksi tanpa perlu key in semula."
        )
        conn = get_db_connection()

        pv_tab1, pv_tab2 = st.tabs([
            "📋 Senarai, Pengesahan & Kawalan Baucar",
            "➕ Keluarkan Baucar Baharu (Pra-Transaksi)"
        ])

        with pv_tab2:
            if not user['can_modify']:
                st.warning("Peranan anda adalah 'Paparan Sahaja'. Hanya Bendahari atau pegawai dengan kuasa ubah data boleh mengeluarkan baucar bayaran baharu.")
            else:
                if st.session_state.get('pv_success_msg'):
                    st.success(st.session_state['pv_success_msg'])
                    st.session_state['pv_success_msg'] = None

                nonce = st.session_state['pv_form_nonce']
                st.markdown("##### Borang Pengeluaran Baucar Bayaran Baharu")
                col_pv1, col_pv2, col_pv3 = st.columns(3)
                pv_tarikh = col_pv1.date_input("Tarikh Baucar", masa_sekarang(), key=f"pv_new_tarikh_{nonce}")
                next_serial = jana_no_baucar_seterusnya(pv_tarikh.strftime("%Y"))
                col_pv2.text_input("No. Siri Baucar (Auto Running Serial)", value=next_serial, disabled=True, key=f"pv_new_serial_{nonce}", help="Dijana secara automatik oleh sistem.")
                
                df_kat_keluar = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis LIKE '%Keluar%' ORDER BY nama ASC", conn)
                kat_keluar_opts = df_kat_keluar['nama'].tolist() if not df_kat_keluar.empty else ["Lain-lain Perbelanjaan"]
                pv_kategori = col_pv3.selectbox("Kategori Perbelanjaan", kat_keluar_opts, key=f"pv_new_kat_{nonce}")

                col_pv4, col_pv5, col_pv6 = st.columns([2, 1.2, 1.2])
                pv_penerima = col_pv4.text_input("Dibayar Kepada (Nama Penerima / Syarikat) *", placeholder="cth: Tenaga Nasional Berhad / Ustaz Ahmad", key=f"pv_new_penerima_{nonce}")
                pv_rujukan = col_pv5.text_input("No. Rujukan / Bil / Invois", placeholder="cth: INV-2026-089", key=f"pv_new_rujukan_{nonce}")
                pv_kaedah = col_pv6.selectbox("Kaedah Bayaran", ["Tunai", "Pindahan Bank (Online)", "Cek"], key=f"pv_new_kaedah_{nonce}")

                pv_butiran = st.text_area("Maksud / Butiran Pembayaran *", placeholder="Nyatakan tujuan pembayaran secara terperinci...", height=80, key=f"pv_new_butiran_{nonce}")
                pv_amaun = st.number_input("Jumlah Bayaran Dipohon (RM) *", min_value=0.0, step=10.0, format="%.2f", key=f"pv_new_amaun_{nonce}")

                btn_c1, btn_c2 = st.columns([1, 1])
                if btn_c1.button("🧾 Jana & Hantar Baucar untuk Pengesahan", type="primary", key=f"btn_create_pv_{nonce}", use_container_width=True):
                    if not pv_penerima.strip():
                        st.error("Sila masukkan nama penerima bayaran!")
                    elif not pv_butiran.strip():
                        st.error("Sila masukkan maksud / butiran pembayaran!")
                    elif pv_amaun <= 0:
                        st.error("Jumlah bayaran mestilah lebih besar daripada RM 0.00!")
                    else:
                        thn_pv = pv_tarikh.strftime("%Y")
                        if get_tahun_status(thn_pv) == 'Tutup' and not user['is_admin']:
                            st.error(f"Tahun kewangan {thn_pv} telah DITUTUP. Baucar baharu tidak boleh dikeluarkan.")
                        else:
                            c = conn.cursor()
                            kini_str = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                            serial_final = jana_no_baucar_seterusnya(thn_pv)
                            inserted = False
                            for _ in range(5):
                                try:
                                    c.execute("""INSERT INTO payment_vouchers 
                                        (no_baucar, tarikh_baucar, nama_penerima, no_rujukan, kategori, butiran, amaun, kaedah_bayaran, status, dicipta_oleh, dicipta_pada)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Menunggu Kelulusan', ?, ?)""",
                                        (serial_final, pv_tarikh.strftime("%Y-%m-%d"), pv_penerima.strip(), pv_rujukan.strip(),
                                         pv_kategori, pv_butiran.strip(), pv_amaun, pv_kaedah, user['nama_penuh'], kini_str))
                                    conn.commit()
                                    inserted = True
                                    break
                                except sqlite3.IntegrityError:
                                    prefix = f"PV-{thn_pv}-"
                                    seq_num = int(serial_final.replace(prefix, "")) + 1
                                    serial_final = f"{prefix}{seq_num:04d}"

                            if inserted:
                                log_audit(user['nama_penuh'], "KELUAR BAUCAR BAYARAN", f"{serial_final} | Penerima: {pv_penerima.strip()} | RM{pv_amaun:,.2f} (Menunggu Kelulusan)")
                                st.session_state['pv_success_msg'] = f"✅ Baucar Bayaran **{serial_final}** berjaya dikeluarkan dan dihantar untuk pengesahan!"
                                st.session_state['pv_form_nonce'] += 1
                                st.rerun()

                if btn_c2.button("❌ Batal / Kosongkan Borang", key=f"btn_batal_pv_new_{nonce}", use_container_width=True):
                    st.session_state['pv_form_nonce'] += 1
                    st.rerun()

        with pv_tab1:
            f_col1, f_col2 = st.columns([1.3, 2])
            status_opts = [
                "Semua Status", "Menunggu Kelulusan", "Diluluskan", 
                "Menunggu Kebenaran Edit", "Dibenarkan Edit", "Direkod ke Lejar", "Ditolak"
            ]
            pilih_status_pv = f_col1.selectbox("Tapis Mengikut Status Baucar", status_opts, key="flt_pv_status")
            cari_pv = f_col2.text_input("Cari No. Baucar / Penerima / Butiran", placeholder="Taip PV-2026 atau nama penerima...", key="flt_pv_search")

            q_pv = """SELECT id, no_baucar, tarikh_baucar, nama_penerima, kategori, butiran, amaun, kaedah_bayaran, status, dicipta_oleh, disahkan_oleh
                      FROM payment_vouchers WHERE 1=1"""
            p_pv = []
            if pilih_status_pv != "Semua Status":
                q_pv += " AND status = ?"
                p_pv.append(pilih_status_pv)
            if cari_pv.strip():
                q_pv += " AND (LOWER(no_baucar) LIKE ? OR LOWER(nama_penerima) LIKE ? OR LOWER(butiran) LIKE ?)"
                kw = f"%{cari_pv.strip().lower()}%"
                p_pv.extend([kw, kw, kw])
            q_pv += " ORDER BY id DESC"

            df_pv = pd.read_sql_query(q_pv, conn, params=p_pv)

            if df_pv.empty:
                st.info("Tiada rekod baucar bayaran dijumpai. Gunakan tab '➕ Keluarkan Baucar Baharu'.")
            else:
                def format_status_badge(st_val):
                    mapping = {
                        "Menunggu Kelulusan": "⏳ Menunggu Kelulusan",
                        "Diluluskan": "✅ Diluluskan (Sedia ke Lejar)",
                        "Menunggu Kebenaran Edit": "🔐 Menunggu Kebenaran Edit",
                        "Dibenarkan Edit": "🔓 Dibenarkan Edit",
                        "Direkod ke Lejar": "💸 Direkod ke Lejar",
                        "Ditolak": "❌ Ditolak"
                    }
                    return mapping.get(st_val, st_val)

                df_pv_display = df_pv.copy()
                df_pv_display['Status Kawalan'] = df_pv_display['status'].apply(format_status_badge)
                df_pv_display['disahkan_oleh'] = df_pv_display['disahkan_oleh'].fillna("-")

                st.dataframe(
                    df_pv_display[['no_baucar', 'tarikh_baucar', 'nama_penerima', 'kategori', 'butiran', 'amaun', 'Status Kawalan', 'dicipta_oleh', 'disahkan_oleh']].rename(columns={
                        'no_baucar': 'No. Baucar (Serial)', 'tarikh_baucar': 'Tarikh', 'nama_penerima': 'Penerima Bayaran',
                        'kategori': 'Kategori', 'butiran': 'Butiran', 'amaun': 'Amaun (RM)',
                        'dicipta_oleh': 'Disediakan Oleh', 'disahkan_oleh': 'Disahkan Oleh'
                    }).style.format({"Amaun (RM)": "RM {:,.2f}"}),
                    use_container_width=True, hide_index=True
                )

                st.divider()
                st.markdown("#### 🛠️ Tindakan, Pengesahan & Cetakan Baucar")

                pv_select_map = {
                    f"{r['no_baucar']} | {r['nama_penerima']} | RM {r['amaun']:,.2f} [{r['status']}]": int(r['id'])
                    for _, r in df_pv.iterrows()
                }
                chosen_pv_label = st.selectbox("Pilih Baucar Bayaran untuk Tindakan / Cetakan:", list(pv_select_map.keys()), key="sel_pv_action")
                chosen_pv_id = pv_select_map[chosen_pv_label]

                c = conn.cursor()
                c.execute("""SELECT id, no_baucar, tarikh_baucar, nama_penerima, no_rujukan, kategori, butiran, amaun,
                                    kaedah_bayaran, status, dicipta_oleh, dicipta_pada, disahkan_oleh, jawatan_pengesah,
                                    disahkan_pada, catatan_pengesah, sebab_mohon_edit, dimohon_edit_oleh, dimohon_edit_pada,
                                    kebenaran_edit_oleh, kebenaran_edit_pada, urusniaga_id
                             FROM payment_vouchers WHERE id = ?""", (chosen_pv_id,))
                pv_rec = c.fetchone()

                if pv_rec:
                    pv_dict = {
                        "id": pv_rec[0], "no_baucar": pv_rec[1], "tarikh_baucar": pv_rec[2],
                        "nama_penerima": pv_rec[3], "no_rujukan": pv_rec[4], "kategori": pv_rec[5],
                        "butiran": pv_rec[6], "amaun": float(pv_rec[7]), "kaedah_bayaran": pv_rec[8],
                        "status": pv_rec[9], "dicipta_oleh": pv_rec[10], "dicipta_pada": pv_rec[11],
                        "disahkan_oleh": pv_rec[12], "jawatan_pengesah": pv_rec[13], "disahkan_pada": pv_rec[14],
                        "catatan_pengesah": pv_rec[15], "sebab_mohon_edit": pv_rec[16], "dimohon_edit_oleh": pv_rec[17],
                        "dimohon_edit_pada": pv_rec[18], "kebenaran_edit_oleh": pv_rec[19], "kebenaran_edit_pada": pv_rec[20],
                        "urusniaga_id": pv_rec[21]
                    }

                    with st.container(border=True):
                        ic1, ic2, ic3 = st.columns(3)
                        ic1.markdown(f"**No. Baucar:** `{pv_dict['no_baucar']}`\n\n**Tarikh:** {pv_dict['tarikh_baucar']}")
                        ic2.markdown(f"**Penerima:** {pv_dict['nama_penerima']}\n\n**Kategori:** {pv_dict['kategori']}")
                        ic3.markdown(f"**Amaun:** **RM {pv_dict['amaun']:,.2f}**\n\n**Status:** **{format_status_badge(pv_dict['status'])}**")
                        st.markdown(f"**Butiran Bayaran:** {pv_dict['butiran']} *(Kaedah: {pv_dict['kaedah_bayaran']} | Rujukan: {pv_dict['no_rujukan'] or '-'})*")

                        if pv_dict['disahkan_oleh']:
                            st.success(f"✅ Disahkan oleh **{pv_dict['disahkan_oleh']}** ({pv_dict['jawatan_pengesah']}) pada {pv_dict['disahkan_pada']}" + (f" — Catatan: *{pv_dict['catatan_pengesah']}*" if pv_dict['catatan_pengesah'] else ""))
                        if pv_dict['kebenaran_edit_oleh']:
                            st.info(f"🔓 Kebenaran Edit diluluskan oleh **{pv_dict['kebenaran_edit_oleh']}** pada {pv_dict['kebenaran_edit_pada']} (Alasan: *{pv_dict['sebab_mohon_edit']}*)")
                        if pv_dict['urusniaga_id']:
                            st.info(f"📘 **Pautan Lejar Urusniaga:** Telah direkodkan di Lejar Urusniaga dengan **ID Transaksi #{pv_dict['urusniaga_id']}**.")

                    st.markdown("##### 🖨️ Cetakan & Muat Turun PDF Baucar")
                    pdf_bytes = generate_pv_pdf_bytes(pv_dict, nama_surau, alamat_surau)
                    dl_col1, dl_col2 = st.columns([1.2, 2])
                    dl_col1.download_button(
                        label=f"📥 Muat Turun PDF ({pv_dict['no_baucar']}.pdf)",
                        data=pdf_bytes, file_name=f"{pv_dict['no_baucar']}.pdf", mime="application/pdf", type="primary", use_container_width=True
                    )
                    if dl_col2.checkbox("👁️ Buka Pratonton & Cetak Terus (HTML Print)", key=f"chk_print_pv_{chosen_pv_id}"):
                        pv_html_doc = build_pv_html(pv_dict, nama_surau, alamat_surau)
                        show_printable_html(pv_html_doc, f"{pv_dict['no_baucar']}.html", f"🖨️ Cetak {pv_dict['no_baucar']}")

                    st.markdown("---")

                    if pv_dict['status'] == 'Menunggu Kelulusan':
                        st.markdown("##### ✍️ Pengesahan Baucar Bayaran (Pengerusi / Timbalan Pengerusi)")
                        if user['can_approve_pv']:
                            catatan_lulus = st.text_input("Catatan Pengesahan / Kelulusan (Pilihan):", key=f"cat_app_{chosen_pv_id}")
                            ab1, ab2 = st.columns(2)
                            if ab1.button("✅ Sahkan & Luluskan Baucar Ini", type="primary", use_container_width=True, key=f"btn_app_pv_{chosen_pv_id}"):
                                kini_app = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                c.execute("""UPDATE payment_vouchers SET status = 'Diluluskan', disahkan_oleh = ?, jawatan_pengesah = ?,
                                             disahkan_pada = ?, catatan_pengesah = ? WHERE id = ?""",
                                          (user['nama_penuh'], user['peranan'], kini_app, catatan_lulus.strip(), chosen_pv_id))
                                conn.commit()
                                log_audit(user['nama_penuh'], "LULUS BAUCAR BAYARAN", f"{pv_dict['no_baucar']} (RM{pv_dict['amaun']:,.2f}) disahkan oleh {user['peranan']}.")
                                st.success(f"Baucar **{pv_dict['no_baucar']}** telah disahkan dan diluluskan! Bendahari kini boleh memilih No. Baucar ini di menu **📝 Rekod & Lejar Urusniaga**.")
                                st.rerun()

                            if ab2.button("❌ Tolak Baucar Ini", type="secondary", use_container_width=True, key=f"btn_rej_pv_{chosen_pv_id}"):
                                if not catatan_lulus.strip():
                                    st.error("Sila masukkan sebab penolakan pada ruangan catatan di atas.")
                                else:
                                    kini_rej = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                    c.execute("""UPDATE payment_vouchers SET status = 'Ditolak', disahkan_oleh = ?, jawatan_pengesah = ?,
                                                 disahkan_pada = ?, catatan_pengesah = ? WHERE id = ?""",
                                              (user['nama_penuh'], user['peranan'], kini_rej, catatan_lulus.strip(), chosen_pv_id))
                                    conn.commit()
                                    log_audit(user['nama_penuh'], "TOLAK BAUCAR BAYARAN", f"{pv_dict['no_baucar']} ditolak oleh {user['peranan']}. Sebab: {catatan_lulus.strip()}")
                                    st.warning(f"Baucar **{pv_dict['no_baucar']}** telah ditolak.")
                                    st.rerun()
                        else:
                            st.info("⏳ Baucar ini sedang menunggu pengesahan daripada **Pengerusi** atau **Timbalan Pengerusi** sebelum boleh direkodkan ke dalam lejar.")

                    if pv_dict['status'] == 'Diluluskan':
                        st.success(
                            f"✅ Baucar **{pv_dict['no_baucar']}** telah diluluskan. Sila ke menu **📝 Rekod & Lejar Urusniaga** "
                            f"dan pilih No. Baucar **`{pv_dict['no_baucar']}`** untuk merekodkan transaksi keluar ke dalam lejar secara automatik."
                        )

                    if pv_dict['status'] == 'Menunggu Kelulusan' and user['can_modify']:
                        edit_draft_key = f"edit_draft_{chosen_pv_id}"
                        if edit_draft_key not in st.session_state:
                            st.session_state[edit_draft_key] = False
                            
                        if not st.session_state[edit_draft_key]:
                            if st.button("✏️ Kemaskini Draf Baucar (Sebelum Kelulusan)", key=f"btn_open_edit_draft_{chosen_pv_id}"):
                                st.session_state[edit_draft_key] = True
                                st.rerun()
                        else:
                            st.markdown("##### ✏️ Kemaskini Draf Baucar (Sebelum Kelulusan)")
                            with st.container(border=True):
                                df_k_edit = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis LIKE '%Keluar%' ORDER BY nama ASC", conn)
                                k_edit_opts = df_k_edit['nama'].tolist() if not df_k_edit.empty else [pv_dict['kategori']]
                                idx_k = k_edit_opts.index(pv_dict['kategori']) if pv_dict['kategori'] in k_edit_opts else 0

                                ed1, ed2 = st.columns(2)
                                ed_tarikh = ed1.date_input("Tarikh Baucar", datetime.strptime(pv_dict['tarikh_baucar'], "%Y-%m-%d"), key=f"ed_pv_dt_{chosen_pv_id}")
                                ed_kat = ed2.selectbox("Kategori", k_edit_opts, index=idx_k, key=f"ed_pv_kat_{chosen_pv_id}")
                                ed_penerima = ed1.text_input("Dibayar Kepada", value=pv_dict['nama_penerima'], key=f"ed_pv_pen_{chosen_pv_id}")
                                ed_rujukan = ed2.text_input("No. Rujukan / Invois", value=pv_dict['no_rujukan'] or "", key=f"ed_pv_ruj_{chosen_pv_id}")
                                kaedah_list = ["Tunai", "Pindahan Bank (Online)", "Cek"]
                                idx_kd = kaedah_list.index(pv_dict['kaedah_bayaran']) if pv_dict['kaedah_bayaran'] in kaedah_list else 0
                                ed_kaedah = ed1.selectbox("Kaedah Bayaran", kaedah_list, index=idx_kd, key=f"ed_pv_kd_{chosen_pv_id}")
                                ed_amaun = ed2.number_input("Amaun (RM)", min_value=0.01, value=pv_dict['amaun'], step=10.0, format="%.2f", key=f"ed_pv_amt_{chosen_pv_id}")
                                ed_butiran = st.text_area("Maksud / Butiran", value=pv_dict['butiran'], key=f"ed_pv_but_{chosen_pv_id}")

                                c_btn1, c_btn2 = st.columns(2)
                                if c_btn1.button("💾 Simpan Kemaskini Draf Baucar", type="primary", key=f"btn_save_draft_pv_{chosen_pv_id}", use_container_width=True):
                                    kini_ed = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                    c.execute("""UPDATE payment_vouchers SET tarikh_baucar=?, nama_penerima=?, no_rujukan=?, kategori=?,
                                                 butiran=?, amaun=?, kaedah_bayaran=?, dikemaskini_oleh=?, dikemaskini_pada=? WHERE id=?""",
                                              (ed_tarikh.strftime("%Y-%m-%d"), ed_penerima.strip(), ed_rujukan.strip(), ed_kat,
                                               ed_butiran.strip(), ed_amaun, ed_kaedah, user['nama_penuh'], kini_ed, chosen_pv_id))
                                    conn.commit()
                                    log_audit(user['nama_penuh'], "KEMASKINI DRAF BAUCAR", f"{pv_dict['no_baucar']} dikemaskini sebelum kelulusan.")
                                    st.success("Draf baucar berjaya dikemaskini!")
                                    st.session_state[edit_draft_key] = False
                                    st.rerun()

                                if c_btn2.button("❌ Batal / Cancel", key=f"btn_cancel_draft_pv_{chosen_pv_id}", use_container_width=True):
                                    st.session_state[edit_draft_key] = False
                                    st.rerun()

                    elif pv_dict['status'] in ['Diluluskan', 'Direkod ke Lejar']:
                        st.markdown("##### 🔒 Kawalan Pindaan Baucar Selepas Kelulusan")
                        st.warning(
                            f"Baucar **{pv_dict['no_baucar']}** telah disahkan oleh **{pv_dict['disahkan_oleh']}**. "
                            "Sebarang pengubahsuaian dikunci dan memerlukan kebenaran **Pengerusi** atau **Timbalan Pengerusi**."
                        )
                        if user['can_modify'] or user['can_approve_pv']:
                            req_edit_key = f"req_edit_{chosen_pv_id}"
                            if req_edit_key not in st.session_state:
                                st.session_state[req_edit_key] = False
                                
                            if not st.session_state[req_edit_key]:
                                if st.button("🔓 Mohon Kebenaran Edit daripada Pengerusi", key=f"btn_open_req_{chosen_pv_id}"):
                                    st.session_state[req_edit_key] = True
                                    st.rerun()
                            else:
                                with st.container(border=True):
                                    sebab_edit = st.text_area("Nyatakan Sebab / Justifikasi Pindaan (Wajib) *:", placeholder="cth: Jumlah sebenar pada resit pembekal ialah RM 245.00 berbanding anggaran RM 250.00", key=f"req_edit_reason_{chosen_pv_id}")
                                    r_b1, r_b2 = st.columns(2)
                                    if r_b1.button("📨 Hantar Permohonan Kebenaran Edit", type="primary", key=f"btn_req_edit_{chosen_pv_id}", use_container_width=True):
                                        if not sebab_edit.strip():
                                            st.error("Sila nyatakan sebab pindaan dengan jelas!")
                                        else:
                                            kini_req = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                            c.execute("""UPDATE payment_vouchers SET status = 'Menunggu Kebenaran Edit',
                                                         sebab_mohon_edit = ?, dimohon_edit_oleh = ?, dimohon_edit_pada = ? WHERE id = ?""",
                                                      (sebab_edit.strip(), user['nama_penuh'], kini_req, chosen_pv_id))
                                            conn.commit()
                                            log_audit(user['nama_penuh'], "MOHON KEBENARAN EDIT BAUCAR", f"{pv_dict['no_baucar']} | Sebab: {sebab_edit.strip()}")
                                            st.success("Permohonan kebenaran edit telah dihantar kepada Pengerusi / Timbalan Pengerusi!")
                                            st.session_state[req_edit_key] = False
                                            st.rerun()
                                    if r_b2.button("❌ Batal / Cancel", key=f"btn_cancel_req_edit_{chosen_pv_id}", use_container_width=True):
                                        st.session_state[req_edit_key] = False
                                        st.rerun()

                    elif pv_dict['status'] == 'Menunggu Kebenaran Edit':
                        st.markdown("##### 🔐 Permohonan Kebenaran Edit Baucar Diluluskan")
                        st.info(
                            f"**Dimohon Oleh:** {pv_dict['dimohon_edit_oleh']} pada {pv_dict['dimohon_edit_pada']}\n\n"
                            f"**Alasan Pindaan:** {pv_dict['sebab_mohon_edit']}"
                        )
                        if user['can_approve_pv']:
                            ke1, ke2 = st.columns(2)
                            if ke1.button("✅ Beri Kebenaran Edit Baucar", type="primary", use_container_width=True, key=f"btn_grant_edit_{chosen_pv_id}"):
                                kini_grant = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                c.execute("""UPDATE payment_vouchers SET status = 'Dibenarkan Edit',
                                             kebenaran_edit_oleh = ?, kebenaran_edit_pada = ? WHERE id = ?""",
                                          (f"{user['nama_penuh']} ({user['peranan']})", kini_grant, chosen_pv_id))
                                conn.commit()
                                log_audit(user['nama_penuh'], "BENARKAN EDIT BAUCAR", f"Kebenaran edit diberikan bagi {pv_dict['no_baucar']} oleh {user['peranan']}.")
                                st.success(f"Kebenaran edit telah diberikan bagi baucar **{pv_dict['no_baucar']}**!")
                                st.rerun()

                            if ke2.button("❌ Tolak Permohonan Edit", type="secondary", use_container_width=True, key=f"btn_deny_edit_{chosen_pv_id}"):
                                restore_st = 'Direkod ke Lejar' if pv_dict['urusniaga_id'] else 'Diluluskan'
                                c.execute("UPDATE payment_vouchers SET status = ? WHERE id = ?", (restore_st, chosen_pv_id))
                                conn.commit()
                                log_audit(user['nama_penuh'], "TOLAK KEBENARAN EDIT BAUCAR", f"Permohonan edit bagi {pv_dict['no_baucar']} ditolak oleh {user['peranan']}.")
                                st.warning("Permohonan kebenaran edit ditolak. Status asal baucar dikekalkan.")
                                st.rerun()
                        else:
                            st.warning("⏳ Menunggu kebenaran daripada **Pengerusi** atau **Timbalan Pengerusi** untuk membuka kunci pindaan baucar ini.")

                    elif pv_dict['status'] == 'Dibenarkan Edit':
                        edit_app_key = f"edit_app_{chosen_pv_id}"
                        if edit_app_key not in st.session_state:
                            st.session_state[edit_app_key] = False
                            
                        if not st.session_state[edit_app_key]:
                            st.success(f"🔓 Kebenaran edit telah diberikan oleh **{pv_dict['kebenaran_edit_oleh']}**.")
                            if st.button("✏️ Buka Borang Kemaskini Baucar", key=f"btn_open_edit_app_{chosen_pv_id}"):
                                st.session_state[edit_app_key] = True
                                st.rerun()
                        else:
                            st.markdown("##### ✏️ Kemaskini Baucar (Kebenaran Edit Telah Diluluskan)")
                            if user['can_modify'] or user['can_approve_pv']:
                                with st.container(border=True):
                                    df_k_ed2 = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis LIKE '%Keluar%' ORDER BY nama ASC", conn)
                                    k_ed2_opts = df_k_ed2['nama'].tolist() if not df_k_ed2.empty else [pv_dict['kategori']]
                                    idx_k2 = k_ed2_opts.index(pv_dict['kategori']) if pv_dict['kategori'] in k_ed2_opts else 0

                                    ep1, ep2 = st.columns(2)
                                    ep_tarikh = ep1.date_input("Tarikh Baucar", datetime.strptime(pv_dict['tarikh_baucar'], "%Y-%m-%d"), key=f"ep_pv_dt_{chosen_pv_id}")
                                    ep_kat = ep2.selectbox("Kategori", k_ed2_opts, index=idx_k2, key=f"ep_pv_kat_{chosen_pv_id}")
                                    ep_penerima = ep1.text_input("Dibayar Kepada", value=pv_dict['nama_penerima'], key=f"ep_pv_pen_{chosen_pv_id}")
                                    ep_rujukan = ep2.text_input("No. Rujukan / Invois", value=pv_dict['no_rujukan'] or "", key=f"ep_pv_ruj_{chosen_pv_id}")
                                    kaedah_list2 = ["Tunai", "Pindahan Bank (Online)", "Cek"]
                                    idx_kd2 = kaedah_list2.index(pv_dict['kaedah_bayaran']) if pv_dict['kaedah_bayaran'] in kaedah_list2 else 0
                                    ep_kaedah = ep1.selectbox("Kaedah Bayaran", kaedah_list2, index=idx_kd2, key=f"ep_pv_kd_{chosen_pv_id}")
                                    ep_amaun = ep2.number_input("Amaun Baharu (RM)", min_value=0.01, value=pv_dict['amaun'], step=10.0, format="%.2f", key=f"ep_pv_amt_{chosen_pv_id}")
                                    ep_butiran = st.text_area("Maksud / Butiran", value=pv_dict['butiran'], key=f"ep_pv_but_{chosen_pv_id}")

                                    e_btn1, e_btn2 = st.columns(2)
                                    if e_btn1.button("💾 Simpan Pindaan & Hantar Semula untuk Pengesahan", type="primary", key=f"btn_save_approved_edit_{chosen_pv_id}", use_container_width=True):
                                        kini_ep = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                        c.execute("""UPDATE payment_vouchers SET tarikh_baucar=?, nama_penerima=?, no_rujukan=?, kategori=?,
                                                     butiran=?, amaun=?, kaedah_bayaran=?, status='Menunggu Kelulusan',
                                                     disahkan_oleh=NULL, jawatan_pengesah=NULL, disahkan_pada=NULL,
                                                     dikemaskini_oleh=?, dikemaskini_pada=? WHERE id=?""",
                                                  (ep_tarikh.strftime("%Y-%m-%d"), ep_penerima.strip(), ep_rujukan.strip(), ep_kat,
                                                   ep_butiran.strip(), ep_amaun, ep_kaedah, user['nama_penuh'], kini_ep, chosen_pv_id))

                                        if pv_dict['urusniaga_id']:
                                            butiran_lejar_baru = f"{ep_penerima.strip()} - {ep_butiran.strip()}" + (f" (Ruj: {ep_rujukan.strip()})" if ep_rujukan.strip() else "")
                                            c.execute("""UPDATE urusniaga SET tarikh=?, bulan_tahun=?, kategori=?, butiran=?, amaun=?,
                                                         dikemaskini_oleh=?, dikemaskini_pada=? WHERE id=?""",
                                                      (ep_tarikh.strftime("%Y-%m-%d"), ep_tarikh.strftime("%Y-%m"), ep_kat,
                                                       butiran_lejar_baru, ep_amaun, user['nama_penuh'], kini_ep, pv_dict['urusniaga_id']))

                                        conn.commit()
                                        log_audit(
                                            user['nama_penuh'], "PINDA BAUCAR SELEPAS KELULUSAN",
                                            f"{pv_dict['no_baucar']} dipinda (Kebenaran: {pv_dict['kebenaran_edit_oleh']}). "
                                            f"Amaun asal: RM{pv_dict['amaun']:,.2f} -> RM{ep_amaun:,.2f}. Dihantar untuk pengesahan semula."
                                        )
                                        st.success(f"Pindaan bagi **{pv_dict['no_baucar']}** berjaya disimpan dan dihantar semula untuk pengesahan!")
                                        st.session_state[edit_app_key] = False
                                        st.rerun()

                                    if e_btn2.button("❌ Batal / Cancel", key=f"btn_cancel_approved_edit_{chosen_pv_id}", use_container_width=True):
                                        st.session_state[edit_app_key] = False
                                        st.rerun()

        conn.close()

    # ---------------------------------------------------------------------
    # 3. TUNTUTAN PERBELANJAAN (REIMBURSEMENT - SEMAKAN DANA & PENGESAHAN)
    # ---------------------------------------------------------------------
    elif pilihan == "💸 Tuntutan Perbelanjaan":
        st.subheader("💸 Pengurusan Tuntutan Perbelanjaan (Reimbursement)")
        st.caption(
            "Aliran Kawalan 2 Peringkat: (1) Ahli/AJK menghantar tuntutan berserta bukti resit -> "
            "(2) Bendahari menyemak resit & mengesahkan kecukupan dana (atau Hold jika dana tidak cukup) -> "
            "(3) Pengerusi / Timbalan Pengerusi mengesahkan kelulusan -> (4) Bayaran balik & rekod ke Lejar."
        )
        conn = get_db_connection()

        tnt_tab1, tnt_tab2 = st.tabs([
            "📋 Senarai, Semakan Dana & Pengesahan Tuntutan",
            "➕ Hantar Permohonan Tuntutan Baharu"
        ])

        with tnt_tab2:
            if st.session_state.get('tnt_success_msg'):
                st.success(st.session_state['tnt_success_msg'])
                st.session_state['tnt_success_msg'] = None

            t_nonce = st.session_state['tnt_form_nonce']
            st.markdown("##### Borang Permohonan Tuntutan Perbelanjaan (Dana Sendiri)")
            
            c_t1, c_t2, c_t3 = st.columns(3)
            tnt_tarikh = c_t1.date_input("Tarikh Permohonan Tuntutan", masa_sekarang(), key=f"tnt_new_tarikh_{t_nonce}")
            next_tnt_serial = jana_no_tuntutan_seterusnya(tnt_tarikh.strftime("%Y"))
            c_t2.text_input("No. Siri Tuntutan (Auto Serial)", value=next_tnt_serial, disabled=True, key=f"tnt_new_serial_{t_nonce}", help="Dijana automatik oleh sistem untuk kawalan audit.")
            tnt_tarikh_resit = c_t3.date_input("Tarikh Resit / Pembelian *", masa_sekarang(), key=f"tnt_new_dt_resit_{t_nonce}")

            c_t4, c_t5, c_t6 = st.columns([1.6, 1.2, 1.2])
            tnt_penuntut = c_t4.text_input("Nama Penuntut (Ahli / AJK) *", value=user['nama_penuh'], key=f"tnt_new_penuntut_{t_nonce}")
            tnt_no_resit = c_t5.text_input("No. Resit / Bil Kedai", placeholder="cth: RES-8821", key=f"tnt_new_no_resit_{t_nonce}")
            
            df_kat_tnt = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis LIKE '%Keluar%' ORDER BY nama ASC", conn)
            kat_tnt_opts = df_kat_tnt['nama'].tolist() if not df_kat_tnt.empty else ["Lain-lain Perbelanjaan"]
            tnt_kategori = c_t6.selectbox("Kategori Perbelanjaan", kat_tnt_opts, key=f"tnt_new_kat_{t_nonce}")

            c_t7, c_t8 = st.columns([1, 2])
            tnt_kaedah = c_t7.selectbox("Kaedah Bayaran Balik Dipohon", ["Tunai", "Pindahan Bank (Online)", "Cek"], key=f"tnt_new_kaedah_{t_nonce}")
            tnt_akaun_bank = c_t8.text_input("Nama Bank & No. Akaun (Jika Pindahan Bank)", placeholder="cth: Maybank - 162012345678", key=f"tnt_new_bank_{t_nonce}")

            tnt_butiran = st.text_area("Maksud / Butiran Perbelanjaan *", placeholder="Nyatakan barangan/perkhidmatan yang telah dibeli untuk kegunaan surau...", height=80, key=f"tnt_new_butiran_{t_nonce}")
            
            c_t9, c_t10 = st.columns([1, 1.5])
            tnt_amaun = c_t9.number_input("Jumlah Tuntutan (RM) *", min_value=0.0, step=10.0, format="%.2f", key=f"tnt_new_amaun_{t_nonce}")
            tnt_lampiran = c_t10.file_uploader("Muat Naik Bukti Resit (Gambar JPG/PNG atau PDF)", type=["jpg", "jpeg", "png", "pdf"], key=f"tnt_new_file_{t_nonce}")

            tb1, tb2 = st.columns(2)
            if tb1.button("📨 Hantar Tuntutan untuk Semakan Bendahari", type="primary", key=f"btn_submit_tnt_{t_nonce}", use_container_width=True):
                if not tnt_penuntut.strip():
                    st.error("Sila masukkan nama penuntut!")
                elif not tnt_butiran.strip():
                    st.error("Sila masukkan butiran perbelanjaan!")
                elif tnt_amaun <= 0:
                    st.error("Jumlah tuntutan mestilah lebih besar daripada RM 0.00!")
                else:
                    thn_tnt = tnt_tarikh.strftime("%Y")
                    if get_tahun_status(thn_tnt) == 'Tutup' and not user['is_admin']:
                        st.error(f"Tahun kewangan {thn_tnt} telah DITUTUP. Tuntutan baharu tidak boleh dihantar.")
                    else:
                        c = conn.cursor()
                        kini_tnt = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                        serial_tnt_final = jana_no_tuntutan_seterusnya(thn_tnt)

                        saved_file_path = None
                        if tnt_lampiran is not None:
                            safe_name = f"{serial_tnt_final}_{os.path.basename(tnt_lampiran.name)}"
                            saved_file_path = os.path.join(UPLOAD_DIR_TUNTUTAN, safe_name)
                            with open(saved_file_path, "wb") as f_out:
                                f_out.write(tnt_lampiran.getbuffer())

                        inserted_tnt = False
                        for _ in range(5):
                            try:
                                c.execute("""INSERT INTO tuntutan 
                                    (no_tuntutan, tarikh_tuntutan, tarikh_resit, nama_penuntut, username_penuntut, no_resit_kedai,
                                     kategori, butiran, amaun, kaedah_bayaran_balik, maklumat_akaun_bank, lampiran_path,
                                     status, dicipta_oleh, dicipta_pada)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Menunggu Semakan Bendahari', ?, ?)""",
                                    (serial_tnt_final, tnt_tarikh.strftime("%Y-%m-%d"), tnt_tarikh_resit.strftime("%Y-%m-%d"),
                                     tnt_penuntut.strip(), user['username'], tnt_no_resit.strip(),
                                     tnt_kategori, tnt_butiran.strip(), tnt_amaun, tnt_kaedah, tnt_akaun_bank.strip(),
                                     saved_file_path, user['nama_penuh'], kini_tnt))
                                conn.commit()
                                inserted_tnt = True
                                break
                            except sqlite3.IntegrityError:
                                prefix = f"TNT-{thn_tnt}-"
                                seq_num = int(serial_tnt_final.replace(prefix, "")) + 1
                                serial_tnt_final = f"{prefix}{seq_num:04d}"

                        if inserted_tnt:
                            log_audit(user['nama_penuh'], "MOHON TUNTUTAN", f"{serial_tnt_final} | Penuntut: {tnt_penuntut.strip()} | RM{tnt_amaun:,.2f} (Menunggu Semakan Bendahari)")
                            st.session_state['tnt_success_msg'] = f"✅ Permohonan Tuntutan **{serial_tnt_final}** berjaya dihantar untuk semakan kecukupan dana oleh Bendahari!"
                            st.session_state['tnt_form_nonce'] += 1
                            st.rerun()

            if tb2.button("❌ Batal / Kosongkan Borang", key=f"btn_batal_tnt_new_{t_nonce}", use_container_width=True):
                st.session_state['tnt_form_nonce'] += 1
                st.rerun()

        with tnt_tab1:
            _, _, baki_tabung_semasa = get_baki_dana_semasa()
            st.metric("💰 Baki Dana Tabung Surau Semasa (Berdasarkan Lejar)", f"RM {baki_tabung_semasa:,.2f}")

            tf_col1, tf_col2 = st.columns([1.4, 2])
            tnt_status_opts = [
                "Semua Status",
                "Menunggu Semakan Bendahari",
                "Ditangguhkan (Dana Tidak Cukup)",
                "Menunggu Kelulusan Pengerusi",
                "Diluluskan",
                "Dibayar & Direkod",
                "Menunggu Kebenaran Edit",
                "Dibenarkan Edit",
                "Ditolak"
            ]
            pilih_status_tnt = tf_col1.selectbox("Tapis Mengikut Status Tuntutan", tnt_status_opts, key="flt_tnt_status")
            cari_tnt = tf_col2.text_input("Cari No. Tuntutan / Nama Penuntut / Butiran", placeholder="Taip TNT-2026 atau nama penuntut...", key="flt_tnt_search")

            q_tnt = """SELECT id, no_tuntutan, tarikh_tuntutan, nama_penuntut, kategori, butiran, amaun, status, disemak_oleh, disahkan_oleh
                       FROM tuntutan WHERE 1=1"""
            p_tnt = []
            if pilih_status_tnt != "Semua Status":
                q_tnt += " AND status = ?"
                p_tnt.append(pilih_status_tnt)
            if cari_tnt.strip():
                q_tnt += " AND (LOWER(no_tuntutan) LIKE ? OR LOWER(nama_penuntut) LIKE ? OR LOWER(butiran) LIKE ?)"
                kw_t = f"%{cari_tnt.strip().lower()}%"
                p_tnt.extend([kw_t, kw_t, kw_t])
            q_tnt += " ORDER BY id DESC"

            df_tnt = pd.read_sql_query(q_tnt, conn, params=p_tnt)

            if df_tnt.empty:
                st.info("Tiada rekod tuntutan perbelanjaan dijumpai. Gunakan tab '➕ Hantar Permohonan Tuntutan Baharu'.")
            else:
                def format_tnt_badge(st_val):
                    mapping = {
                        "Menunggu Semakan Bendahari": "🔍 Menunggu Semakan Bendahari",
                        "Ditangguhkan (Dana Tidak Cukup)": "⏸️ Ditangguhkan (Hold - Dana Tidak Cukup)",
                        "Menunggu Kelulusan Pengerusi": "⏳ Menunggu Kelulusan Pengerusi",
                        "Diluluskan": "✅ Diluluskan",
                        "Dibayar & Direkod": "💸 Dibayar & Direkod",
                        "Menunggu Kebenaran Edit": "🔐 Menunggu Kebenaran Edit",
                        "Dibenarkan Edit": "🔓 Dibenarkan Edit",
                        "Ditolak": "❌ Ditolak"
                    }
                    return mapping.get(st_val, st_val)

                df_tnt_show = df_tnt.copy()
                df_tnt_show['Status Kawalan'] = df_tnt_show['status'].apply(format_tnt_badge)
                df_tnt_show['disemak_oleh'] = df_tnt_show['disemak_oleh'].fillna("-")
                df_tnt_show['disahkan_oleh'] = df_tnt_show['disahkan_oleh'].fillna("-")

                st.dataframe(
                    df_tnt_show[['no_tuntutan', 'tarikh_tuntutan', 'nama_penuntut', 'kategori', 'butiran', 'amaun', 'Status Kawalan', 'disemak_oleh', 'disahkan_oleh']].rename(columns={
                        'no_tuntutan': 'No. Tuntutan',
                        'tarikh_tuntutan': 'Tarikh',
                        'nama_penuntut': 'Nama Penuntut',
                        'kategori': 'Kategori',
                        'butiran': 'Butiran',
                        'amaun': 'Amaun (RM)',
                        'disemak_oleh': 'Semakan Bendahari',
                        'disahkan_oleh': 'Kelulusan Akhir'
                    }).style.format({"Amaun (RM)": "RM {:,.2f}"}),
                    use_container_width=True, hide_index=True
                )

                st.divider()
                st.markdown("#### 🛠️ Tindakan, Semakan Dana, Pengesahan & Cetakan Tuntutan")

                tnt_select_map = {
                    f"{r['no_tuntutan']} | {r['nama_penuntut']} | RM {r['amaun']:,.2f} [{r['status']}]": int(r['id'])
                    for _, r in df_tnt.iterrows()
                }
                chosen_tnt_label = st.selectbox("Pilih Tuntutan untuk Tindakan / Semakan / Cetakan:", list(tnt_select_map.keys()), key="sel_tnt_action")
                chosen_tnt_id = tnt_select_map[chosen_tnt_label]

                c = conn.cursor()
                c.execute("""SELECT id, no_tuntutan, tarikh_tuntutan, tarikh_resit, nama_penuntut, username_penuntut,
                                    no_resit_kedai, kategori, butiran, amaun, kaedah_bayaran_balik, maklumat_akaun_bank,
                                    lampiran_path, status, dicipta_oleh, dicipta_pada, disemak_oleh, disemak_pada,
                                    status_dana, catatan_bendahari, disahkan_oleh, jawatan_pengesah, disahkan_pada,
                                    catatan_pengesah, sebab_mohon_edit, dimohon_edit_oleh, dimohon_edit_pada,
                                    kebenaran_edit_oleh, kebenaran_edit_pada, no_baucar_pv, urusniaga_id
                             FROM tuntutan WHERE id = ?""", (chosen_tnt_id,))
                t_rec = c.fetchone()

                if t_rec:
                    tnt_dict = {
                        "id": t_rec[0], "no_tuntutan": t_rec[1], "tarikh_tuntutan": t_rec[2],
                        "tarikh_resit": t_rec[3], "nama_penuntut": t_rec[4], "username_penuntut": t_rec[5],
                        "no_resit_kedai": t_rec[6], "kategori": t_rec[7], "butiran": t_rec[8],
                        "amaun": float(t_rec[9]), "kaedah_bayaran_balik": t_rec[10], "maklumat_akaun_bank": t_rec[11],
                        "lampiran_path": t_rec[12], "status": t_rec[13], "dicipta_oleh": t_rec[14],
                        "dicipta_pada": t_rec[15], "disemak_oleh": t_rec[16], "disemak_pada": t_rec[17],
                        "status_dana": t_rec[18], "catatan_bendahari": t_rec[19], "disahkan_oleh": t_rec[20],
                        "jawatan_pengesah": t_rec[21], "disahkan_pada": t_rec[22], "catatan_pengesah": t_rec[23],
                        "sebab_mohon_edit": t_rec[24], "dimohon_edit_oleh": t_rec[25], "dimohon_edit_pada": t_rec[26],
                        "kebenaran_edit_oleh": t_rec[27], "kebenaran_edit_pada": t_rec[28], "no_baucar_pv": t_rec[29],
                        "urusniaga_id": t_rec[30]
                    }

                    with st.container(border=True):
                        tc1, tc2, tc3 = st.columns(3)
                        tc1.markdown(f"**No. Tuntutan:** `{tnt_dict['no_tuntutan']}`\n\n**Tarikh Mohon:** {tnt_dict['tarikh_tuntutan']}\n\n**Tarikh Resit:** {tnt_dict['tarikh_resit']}")
                        tc2.markdown(f"**Nama Penuntut:** {tnt_dict['nama_penuntut']}\n\n**Kategori:** {tnt_dict['kategori']}\n\n**No. Resit:** {tnt_dict['no_resit_kedai'] or '-'}")
                        tc3.markdown(f"**Amaun Tuntutan:** **RM {tnt_dict['amaun']:,.2f}**\n\n**Status:** **{format_tnt_badge(tnt_dict['status'])}**\n\n**Kaedah Bayaran:** {tnt_dict['kaedah_bayaran_balik']}")
                        
                        st.markdown(f"**Butiran Perbelanjaan:** {tnt_dict['butiran']}" + (f" *(Akaun Bank: {tnt_dict['maklumat_akaun_bank']})*" if tnt_dict['maklumat_akaun_bank'] else ""))

                        if tnt_dict['no_baucar_pv']:
                            st.info(f"🧾 **No. Rujukan Baucar Bayaran (PV) Dijana:** `{tnt_dict['no_baucar_pv']}` (ID Lejar: #{tnt_dict['urusniaga_id']})")

                        if tnt_dict['disemak_oleh']:
                            if tnt_dict['status'] == 'Ditangguhkan (Dana Tidak Cukup)':
                                st.warning(f"⏸️ **Ditangguhkan (Hold) oleh Bendahari ({tnt_dict['disemak_oleh']})** pada {tnt_dict['disemak_pada']} — Sebab: *{tnt_dict['catatan_bendahari'] or 'Dana semasa tidak mencukupi'}*")
                            else:
                                st.info(f"🔍 **Semakan Dana Bendahari:** Disemak oleh **{tnt_dict['disemak_oleh']}** pada {tnt_dict['disemak_pada']} ({tnt_dict['status_dana']})" + (f" — Catatan: *{tnt_dict['catatan_bendahari']}*" if tnt_dict['catatan_bendahari'] else ""))

                        if tnt_dict['disahkan_oleh']:
                            if tnt_dict['status'] == 'Ditolak':
                                st.error(f"❌ **Ditolak oleh {tnt_dict['disahkan_oleh']}** ({tnt_dict['jawatan_pengesah']}) pada {tnt_dict['disahkan_pada']} — Sebab: *{tnt_dict['catatan_pengesah']}*")
                            else:
                                st.success(f"✅ **Diluluskan oleh {tnt_dict['disahkan_oleh']}** ({tnt_dict['jawatan_pengesah']}) pada {tnt_dict['disahkan_pada']}" + (f" — Catatan: *{tnt_dict['catatan_pengesah']}*" if tnt_dict['catatan_pengesah'] else ""))

                        if tnt_dict['lampiran_path'] and os.path.exists(tnt_dict['lampiran_path']):
                            with st.expander("📎 Lihat / Muat Turun Bukti Resit Lampiran", expanded=False):
                                file_ext = os.path.splitext(tnt_dict['lampiran_path'])[1].lower()
                                with open(tnt_dict['lampiran_path'], "rb") as f_att:
                                    att_bytes = f_att.read()
                                st.download_button(
                                    label=f"⬇️ Muat Turun Fail Resit ({os.path.basename(tnt_dict['lampiran_path'])})",
                                    data=att_bytes,
                                    file_name=os.path.basename(tnt_dict['lampiran_path']),
                                    key=f"dl_att_tnt_{chosen_tnt_id}"
                                )
                                if file_ext in [".jpg", ".jpeg", ".png"]:
                                    st.image(att_bytes, caption=f"Bukti Resit - {tnt_dict['no_tuntutan']}", use_container_width=True)
                                elif file_ext == ".pdf":
                                    b64_pdf = base64.b64encode(att_bytes).decode('utf-8')
                                    st.markdown(f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="500" type="application/pdf"></iframe>', unsafe_allow_html=True)

                    st.markdown("##### 🖨️ Cetakan & Muat Turun PDF Borang Tuntutan")
                    tnt_pdf_bytes = generate_tuntutan_pdf_bytes(tnt_dict, nama_surau, alamat_surau)
                    tdl1, tdl2 = st.columns([1.2, 2])
                    tdl1.download_button(
                        label=f"📥 Muat Turun PDF ({tnt_dict['no_tuntutan']}.pdf)",
                        data=tnt_pdf_bytes, file_name=f"{tnt_dict['no_tuntutan']}.pdf", mime="application/pdf", type="primary", use_container_width=True
                    )
                    if tdl2.checkbox("👁️ Buka Pratonton & Cetak Terus (HTML Print)", key=f"chk_print_tnt_{chosen_tnt_id}"):
                        tnt_html_doc = build_tuntutan_html(tnt_dict, nama_surau, alamat_surau)
                        show_printable_html(tnt_html_doc, f"{tnt_dict['no_tuntutan']}.html", f"🖨️ Cetak {tnt_dict['no_tuntutan']}")

                    st.markdown("---")

                    if tnt_dict['status'] in ['Menunggu Semakan Bendahari', 'Ditangguhkan (Dana Tidak Cukup)']:
                        st.markdown("##### 🔍 Peringkat 1: Semakan Resit & Pengesahan Kecukupan Dana (Bendahari)")
                        
                        baki_selepas = baki_tabung_semasa - tnt_dict['amaun']
                        sc1, sc2, sc3 = st.columns(3)
                        sc1.metric("Baki Dana Tabung Semasa", f"RM {baki_tabung_semasa:,.2f}")
                        sc2.metric("Jumlah Tuntutan Ini", f"RM {tnt_dict['amaun']:,.2f}")
                        sc3.metric("Anggaran Baki Selepas Bayar", f"RM {baki_selepas:,.2f}", delta=f"{-tnt_dict['amaun']:,.2f}")

                        if baki_selepas < 0:
                            st.error("⚠️ **AMARAN KECUKUPAN DANA:** Baki dana semasa dalam lejar **TIDAK MENCUKUPI** untuk menampung tuntutan ini. Bendahari disarankan untuk **Hold (Tangguhkan)** tuntutan ini sehingga kutipan dana mencukupi.")
                        else:
                            st.success("✅ **STATUS DANA:** Baki dana semasa mencukupi untuk menampung bayaran balik tuntutan ini.")

                        if user['can_review_tnt']:
                            catatan_benda = st.text_input(
                                "Catatan Semakan Bendahari (Wajib diisi jika Hold / Tolak):",
                                placeholder="cth: Resit sah & dana mencukupi / Ditangguhkan sementara menunggu kutipan Jumaat",
                                key=f"cat_benda_tnt_{chosen_tnt_id}"
                            )
                            sb_col1, sb_col2, sb_col3 = st.columns(3)
                            
                            if sb_col1.button("✅ Sahkan Dana Mencukupi & Hantar ke Pengerusi", type="primary", use_container_width=True, key=f"btn_ok_dana_{chosen_tnt_id}"):
                                kini_semak = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                c.execute("""UPDATE tuntutan SET status = 'Menunggu Kelulusan Pengerusi',
                                             disemak_oleh = ?, disemak_pada = ?, status_dana = 'Dana Mencukupi',
                                             catatan_bendahari = ? WHERE id = ?""",
                                          (user['nama_penuh'], kini_semak, catatan_benda.strip(), chosen_tnt_id))
                                conn.commit()
                                log_audit(user['nama_penuh'], "SEMAK TUNTUTAN (DANA MENCUKUPI)", f"{tnt_dict['no_tuntutan']} (RM{tnt_dict['amaun']:,.2f}) disahkan dana mencukupi & dihantar ke Pengerusi/Timbalan.")
                                st.success(f"Semakan selesai! Tuntutan **{tnt_dict['no_tuntutan']}** telah dihantar kepada Pengerusi / Timbalan Pengerusi untuk kelulusan.")
                                st.rerun()

                            if sb_col2.button("⏸️ Hold / Tangguhkan (Dana Tak Cukup)", type="secondary", use_container_width=True, key=f"btn_hold_dana_{chosen_tnt_id}"):
                                if not catatan_benda.strip():
                                    st.error("Sila nyatakan sebab penangguhan (Hold) pada ruangan catatan di atas.")
                                else:
                                    kini_hold = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                    c.execute("""UPDATE tuntutan SET status = 'Ditangguhkan (Dana Tidak Cukup)',
                                                 disemak_oleh = ?, disemak_pada = ?, status_dana = 'Dana Tidak Cukup (Hold)',
                                                 catatan_bendahari = ? WHERE id = ?""",
                                              (user['nama_penuh'], kini_hold, catatan_benda.strip(), chosen_tnt_id))
                                    conn.commit()
                                    log_audit(user['nama_penuh'], "TANGGUH TUNTUTAN (HOLD DANA)", f"{tnt_dict['no_tuntutan']} ditangguhkan oleh Bendahari. Sebab: {catatan_benda.strip()}")
                                    st.warning(f"Tuntutan **{tnt_dict['no_tuntutan']}** telah ditangguhkan (Hold) sehingga dana mencukupi.")
                                    st.rerun()

                            if sb_col3.button("❌ Tolak Tuntutan", type="secondary", use_container_width=True, key=f"btn_rej_benda_{chosen_tnt_id}"):
                                if not catatan_benda.strip():
                                    st.error("Sila masukkan sebab penolakan pada ruangan catatan di atas.")
                                else:
                                    kini_rej_b = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                    c.execute("""UPDATE tuntutan SET status = 'Ditolak', disemak_oleh = ?, disemak_pada = ?,
                                                 status_dana = 'Ditolak Semasa Semakan', catatan_bendahari = ? WHERE id = ?""",
                                              (user['nama_penuh'], kini_rej_b, catatan_benda.strip(), chosen_tnt_id))
                                    conn.commit()
                                    log_audit(user['nama_penuh'], "TOLAK TUNTUTAN (BENDAHARI)", f"{tnt_dict['no_tuntutan']} ditolak oleh Bendahari. Sebab: {catatan_benda.strip()}")
                                    st.error(f"Tuntutan **{tnt_dict['no_tuntutan']}** telah ditolak.")
                                    st.rerun()
                        else:
                            if tnt_dict['status'] == 'Ditangguhkan (Dana Tidak Cukup)':
                                st.warning("⏸️ Tuntutan ini sedang **ditangguhkan (Hold)** oleh Bendahari kerana baki dana tabung semasa belum mencukupi.")
                            else:
                                st.info("🔍 Tuntutan ini sedang menunggu semakan resit dan pengesahan kecukupan dana daripada **Bendahari**.")

                    elif tnt_dict['status'] == 'Menunggu Kelulusan Pengerusi':
                        st.markdown("##### ✍️ Peringkat 2: Pengesahan & Kelulusan Akhir (Pengerusi / Timbalan Pengerusi)")
                        if user['can_approve_pv']:
                            if user['username'] == tnt_dict['username_penuntut']:
                                st.error(
                                    "⛔ **Kawalan Integriti:** Anda adalah penuntut bagi permohonan ini. "
                                    "Sila minta **Pengerusi** atau **Timbalan Pengerusi** yang lain untuk mengesahkan tuntutan ini."
                                )
                            else:
                                catatan_lulus_tnt = st.text_input("Catatan Kelulusan / Pengesahan (Pilihan):", key=f"cat_app_tnt_{chosen_tnt_id}")
                                ap_c1, ap_c2 = st.columns(2)
                                if ap_c1.button("✅ Sahkan & Luluskan Tuntutan Ini", type="primary", use_container_width=True, key=f"btn_app_tnt_{chosen_tnt_id}"):
                                    kini_lulus_tnt = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                    c.execute("""UPDATE tuntutan SET status = 'Diluluskan', disahkan_oleh = ?, jawatan_pengesah = ?,
                                                 disahkan_pada = ?, catatan_pengesah = ? WHERE id = ?""",
                                              (user['nama_penuh'], user['peranan'], kini_lulus_tnt, catatan_lulus_tnt.strip(), chosen_tnt_id))
                                    conn.commit()
                                    log_audit(user['nama_penuh'], "LULUS TUNTUTAN", f"{tnt_dict['no_tuntutan']} (RM{tnt_dict['amaun']:,.2f}) diluluskan oleh {user['peranan']}.")
                                    st.success(f"Tuntutan **{tnt_dict['no_tuntutan']}** telah disahkan dan diluluskan! Sedia untuk pembayaran balik oleh Bendahari.")
                                    st.rerun()

                                if ap_c2.button("❌ Tolak Tuntutan Ini", type="secondary", use_container_width=True, key=f"btn_rej_tnt_{chosen_tnt_id}"):
                                    if not catatan_lulus_tnt.strip():
                                        st.error("Sila nyatakan sebab penolakan pada ruangan catatan di atas.")
                                    else:
                                        kini_rej_tnt = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                        c.execute("""UPDATE tuntutan SET status = 'Ditolak', disahkan_oleh = ?, jawatan_pengesah = ?,
                                                     disahkan_pada = ?, catatan_pengesah = ? WHERE id = ?""",
                                                  (user['nama_penuh'], user['peranan'], kini_rej_tnt, catatan_lulus_tnt.strip(), chosen_tnt_id))
                                        conn.commit()
                                        log_audit(user['nama_penuh'], "TOLAK TUNTUTAN (PENGERUSI)", f"{tnt_dict['no_tuntutan']} ditolak oleh {user['peranan']}. Sebab: {catatan_lulus_tnt.strip()}")
                                        st.warning(f"Tuntutan **{tnt_dict['no_tuntutan']}** telah ditolak.")
                                        st.rerun()
                        else:
                            st.info("⏳ Dana telah disahkan mencukupi oleh Bendahari. Menunggu pengesahan kelulusan daripada **Pengerusi** atau **Timbalan Pengerusi**.")

                    if tnt_dict['status'] == 'Diluluskan' and user['can_review_tnt']:
                        st.markdown("##### 💸 Peringkat 3: Salurkan Bayaran Balik, Jana Baucar (PV) & Rekod ke Lejar")
                        st.caption("Tindakan ini akan menjana Baucar Bayaran (PV) rasmi dan merekodkan transaksi keluar ke dalam Lejar Urusniaga secara automatik.")
                        pay_c1, pay_c2 = st.columns([1.2, 2])
                        tarikh_bayar_tnt = pay_c1.date_input("Tarikh Bayaran Balik", masa_sekarang(), key=f"dt_pay_tnt_{chosen_tnt_id}")
                        if pay_c2.button("💸 Sahkan Bayaran Balik, Jana PV & Rekod ke Lejar", type="primary", key=f"btn_pay_tnt_{chosen_tnt_id}"):
                            thn_bayar = tarikh_bayar_tnt.strftime("%Y")
                            bln_bayar = tarikh_bayar_tnt.strftime("%Y-%m")
                            if get_tahun_status(thn_bayar) == 'Tutup' and not user['is_admin']:
                                st.error(f"Tahun kewangan {thn_bayar} telah DITUTUP.")
                            else:
                                kini_bayar = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                pv_auto_serial = jana_no_baucar_seterusnya(thn_bayar)
                                butiran_pv_tnt = f"Bayaran Balik Tuntutan [{tnt_dict['no_tuntutan']}]: {tnt_dict['butiran']}"
                                
                                c.execute("""INSERT INTO payment_vouchers 
                                    (no_baucar, tarikh_baucar, nama_penerima, no_rujukan, kategori, butiran, amaun, kaedah_bayaran,
                                     status, dicipta_oleh, dicipta_pada, disahkan_oleh, jawatan_pengesah, disahkan_pada, catatan_pengesah)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Direkod ke Lejar', ?, ?, ?, ?, ?, ?)""",
                                    (pv_auto_serial, tarikh_bayar_tnt.strftime("%Y-%m-%d"), tnt_dict['nama_penuntut'],
                                     tnt_dict['no_tuntutan'], tnt_dict['kategori'], butiran_pv_tnt, tnt_dict['amaun'],
                                     tnt_dict['kaedah_bayaran_balik'], user['nama_penuh'], kini_bayar,
                                     tnt_dict['disahkan_oleh'], tnt_dict['jawatan_pengesah'], tnt_dict['disahkan_pada'],
                                     f"Kelulusan Tuntutan {tnt_dict['no_tuntutan']}"))
                                new_pv_id = c.lastrowid

                                butiran_lejar_tnt = f"[{tnt_dict['no_tuntutan']}] {tnt_dict['nama_penuntut']} - {tnt_dict['butiran']}"
                                c.execute("INSERT OR IGNORE INTO tahun_kewangan (tahun, status) VALUES (?, 'Buka')", (thn_bayar,))
                                c.execute("""INSERT INTO urusniaga (tarikh, bulan_tahun, jenis, kategori, butiran, amaun, no_baucar, dicipta_oleh, dicipta_pada)
                                             VALUES (?, ?, 'Perbelanjaan (Keluar)', ?, ?, ?, ?, ?, ?)""",
                                          (tarikh_bayar_tnt.strftime("%Y-%m-%d"), bln_bayar, tnt_dict['kategori'], butiran_lejar_tnt,
                                           tnt_dict['amaun'], pv_auto_serial, user['nama_penuh'], kini_bayar))
                                new_trx_tnt_id = c.lastrowid

                                c.execute("UPDATE payment_vouchers SET urusniaga_id = ? WHERE id = ?", (new_trx_tnt_id, new_pv_id))
                                c.execute("""UPDATE tuntutan SET status = 'Dibayar & Direkod', no_baucar_pv = ?, urusniaga_id = ?
                                             WHERE id = ?""", (pv_auto_serial, new_trx_tnt_id, chosen_tnt_id))
                                conn.commit()

                                log_audit(
                                    user['nama_penuh'], "BAYAR & REKOD TUNTUTAN",
                                    f"{tnt_dict['no_tuntutan']} dibayar kepada {tnt_dict['nama_penuntut']} (RM{tnt_dict['amaun']:,.2f}). "
                                    f"Dijana PV: {pv_auto_serial} & Lejar ID #{new_trx_tnt_id}."
                                )
                                st.success(f"✅ Bayaran balik selesai! Baucar **{pv_auto_serial}** telah dijana dan transaksi direkodkan ke Lejar Urusniaga.")
                                st.rerun()

                    if tnt_dict['status'] in ['Menunggu Semakan Bendahari', 'Ditangguhkan (Dana Tidak Cukup)']:
                        if user['username'] == tnt_dict['username_penuntut'] or user['can_review_tnt']:
                            ed_tnt_key = f"edit_draft_tnt_{chosen_tnt_id}"
                            if ed_tnt_key not in st.session_state:
                                st.session_state[ed_tnt_key] = False

                            if not st.session_state[ed_tnt_key]:
                                if st.button("✏️ Kemaskini Draf Tuntutan (Sebelum Kelulusan)", key=f"btn_open_ed_tnt_{chosen_tnt_id}"):
                                    st.session_state[ed_tnt_key] = True
                                    st.rerun()
                            else:
                                st.markdown("##### ✏️ Kemaskini Draf Tuntutan")
                                with st.container(border=True):
                                    df_kt_ed = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis LIKE '%Keluar%' ORDER BY nama ASC", conn)
                                    kt_ed_opts = df_kt_ed['nama'].tolist() if not df_kt_ed.empty else [tnt_dict['kategori']]
                                    idx_kt = kt_ed_opts.index(tnt_dict['kategori']) if tnt_dict['kategori'] in kt_ed_opts else 0

                                    te1, te2 = st.columns(2)
                                    te_dt_resit = te1.date_input("Tarikh Resit", datetime.strptime(tnt_dict['tarikh_resit'], "%Y-%m-%d"), key=f"te_dt_resit_{chosen_tnt_id}")
                                    te_kat = te2.selectbox("Kategori", kt_ed_opts, index=idx_kt, key=f"te_kat_{chosen_tnt_id}")
                                    te_penuntut = te1.text_input("Nama Penuntut", value=tnt_dict['nama_penuntut'], key=f"te_pen_{chosen_tnt_id}")
                                    te_no_resit = te2.text_input("No. Resit Kedai", value=tnt_dict['no_resit_kedai'] or "", key=f"te_nres_{chosen_tnt_id}")
                                    kd_list_t = ["Tunai", "Pindahan Bank (Online)", "Cek"]
                                    idx_kdt = kd_list_t.index(tnt_dict['kaedah_bayaran_balik']) if tnt_dict['kaedah_bayaran_balik'] in kd_list_t else 0
                                    te_kaedah = te1.selectbox("Kaedah Bayaran Balik", kd_list_t, index=idx_kdt, key=f"te_kd_{chosen_tnt_id}")
                                    te_amaun = te2.number_input("Amaun Tuntutan (RM)", min_value=0.01, value=tnt_dict['amaun'], step=10.0, format="%.2f", key=f"te_amt_{chosen_tnt_id}")
                                    te_bank = st.text_input("Maklumat Akaun Bank", value=tnt_dict['maklumat_akaun_bank'] or "", key=f"te_bank_{chosen_tnt_id}")
                                    te_butiran = st.text_area("Maksud / Butiran", value=tnt_dict['butiran'], key=f"te_but_{chosen_tnt_id}")

                                    te_b1, te_b2 = st.columns(2)
                                    if te_b1.button("💾 Simpan Kemaskini Draf Tuntutan", type="primary", key=f"btn_save_ed_tnt_{chosen_tnt_id}", use_container_width=True):
                                        kini_te = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                        c.execute("""UPDATE tuntutan SET tarikh_resit=?, nama_penuntut=?, no_resit_kedai=?, kategori=?,
                                                     butiran=?, amaun=?, kaedah_bayaran_balik=?, maklumat_akaun_bank=?,
                                                     status='Menunggu Semakan Bendahari', dikemaskini_oleh=?, dikemaskini_pada=? WHERE id=?""",
                                                  (te_dt_resit.strftime("%Y-%m-%d"), te_penuntut.strip(), te_no_resit.strip(), te_kat,
                                                   te_butiran.strip(), te_amaun, te_kaedah, te_bank.strip(), user['nama_penuh'], kini_te, chosen_tnt_id))
                                        conn.commit()
                                        log_audit(user['nama_penuh'], "KEMASKINI DRAF TUNTUTAN", f"{tnt_dict['no_tuntutan']} dikemaskini sebelum kelulusan.")
                                        st.success("Draf tuntutan berjaya dikemaskini!")
                                        st.session_state[ed_tnt_key] = False
                                        st.rerun()

                                    if te_b2.button("❌ Batal / Cancel", key=f"btn_cancel_ed_tnt_{chosen_tnt_id}", use_container_width=True):
                                        st.session_state[ed_tnt_key] = False
                                        st.rerun()

                    elif tnt_dict['status'] in ['Menunggu Kelulusan Pengerusi', 'Diluluskan', 'Dibayar & Direkod']:
                        st.markdown("##### 🔒 Kawalan Pindaan Tuntutan Selepas Semakan / Kelulusan")
                        st.warning(
                            f"Tuntutan **{tnt_dict['no_tuntutan']}** telah melalui proses pengesahan. "
                            "Sebarang pindaan dikunci dan memerlukan kebenaran **Pengerusi** atau **Timbalan Pengerusi**."
                        )
                        if user['username'] == tnt_dict['username_penuntut'] or user['can_review_tnt'] or user['can_approve_pv']:
                            req_tnt_key = f"req_edit_tnt_{chosen_tnt_id}"
                            if req_tnt_key not in st.session_state:
                                st.session_state[req_tnt_key] = False

                            if not st.session_state[req_tnt_key]:
                                if st.button("🔓 Mohon Kebenaran Edit daripada Pengerusi / Timbalan", key=f"btn_open_req_tnt_{chosen_tnt_id}"):
                                    st.session_state[req_tnt_key] = True
                                    st.rerun()
                            else:
                                with st.container(border=True):
                                    sebab_tnt_edit = st.text_area("Nyatakan Sebab / Justifikasi Pindaan (Wajib) *:", placeholder="cth: Tersilap masukkan angka sen pada resit kedai", key=f"req_tnt_reason_{chosen_tnt_id}")
                                    rt_b1, rt_b2 = st.columns(2)
                                    if rt_b1.button("📨 Hantar Permohonan Kebenaran Edit", type="primary", key=f"btn_send_req_tnt_{chosen_tnt_id}", use_container_width=True):
                                        if not sebab_tnt_edit.strip():
                                            st.error("Sila nyatakan sebab pindaan dengan jelas!")
                                        else:
                                            kini_req_t = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                            c.execute("""UPDATE tuntutan SET status = 'Menunggu Kebenaran Edit',
                                                         sebab_mohon_edit = ?, dimohon_edit_oleh = ?, dimohon_edit_pada = ? WHERE id = ?""",
                                                      (sebab_tnt_edit.strip(), user['nama_penuh'], kini_req_t, chosen_tnt_id))
                                            conn.commit()
                                            log_audit(user['nama_penuh'], "MOHON KEBENARAN EDIT TUNTUTAN", f"{tnt_dict['no_tuntutan']} | Sebab: {sebab_tnt_edit.strip()}")
                                            st.success("Permohonan kebenaran edit telah dihantar kepada Pengerusi / Timbalan Pengerusi!")
                                            st.session_state[req_tnt_key] = False
                                            st.rerun()
                                    if rt_b2.button("❌ Batal / Cancel", key=f"btn_cancel_req_tnt_{chosen_tnt_id}", use_container_width=True):
                                        st.session_state[req_tnt_key] = False
                                        st.rerun()

                    elif tnt_dict['status'] == 'Menunggu Kebenaran Edit':
                        st.markdown("##### 🔐 Permohonan Kebenaran Edit Tuntutan")
                        st.info(
                            f"**Dimohon Oleh:** {tnt_dict['dimohon_edit_oleh']} pada {tnt_dict['dimohon_edit_pada']}\n\n"
                            f"**Alasan Pindaan:** {tnt_dict['sebab_mohon_edit']}"
                        )
                        if user['can_approve_pv']:
                            ket1, ket2 = st.columns(2)
                            if ket1.button("✅ Beri Kebenaran Edit Tuntutan", type="primary", use_container_width=True, key=f"btn_grant_tnt_{chosen_tnt_id}"):
                                kini_gt = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                c.execute("""UPDATE tuntutan SET status = 'Dibenarkan Edit',
                                             kebenaran_edit_oleh = ?, kebenaran_edit_pada = ? WHERE id = ?""",
                                          (f"{user['nama_penuh']} ({user['peranan']})", kini_gt, chosen_tnt_id))
                                conn.commit()
                                log_audit(user['nama_penuh'], "BENARKAN EDIT TUNTUTAN", f"Kebenaran edit diberikan bagi {tnt_dict['no_tuntutan']} oleh {user['peranan']}.")
                                st.success(f"Kebenaran edit telah diberikan bagi tuntutan **{tnt_dict['no_tuntutan']}**!")
                                st.rerun()

                            if ket2.button("❌ Tolak Permohonan Edit", type="secondary", use_container_width=True, key=f"btn_deny_tnt_{chosen_tnt_id}"):
                                restore_tnt = 'Dibayar & Direkod' if tnt_dict['urusniaga_id'] else ('Diluluskan' if tnt_dict['disahkan_oleh'] else 'Menunggu Kelulusan Pengerusi')
                                c.execute("UPDATE tuntutan SET status = ? WHERE id = ?", (restore_tnt, chosen_tnt_id))
                                conn.commit()
                                log_audit(user['nama_penuh'], "TOLAK KEBENARAN EDIT TUNTUTAN", f"Permohonan edit bagi {tnt_dict['no_tuntutan']} ditolak.")
                                st.warning("Permohonan edit ditolak. Status asal dikekalkan.")
                                st.rerun()
                        else:
                            st.warning("⏳ Menunggu kebenaran daripada **Pengerusi** atau **Timbalan Pengerusi** untuk membuka kunci pindaan tuntutan ini.")

                    elif tnt_dict['status'] == 'Dibenarkan Edit':
                        ed_app_tnt_key = f"ed_app_tnt_{chosen_tnt_id}"
                        if ed_app_tnt_key not in st.session_state:
                            st.session_state[ed_app_tnt_key] = False

                        if not st.session_state[ed_app_tnt_key]:
                            st.success(f"🔓 Kebenaran edit telah diberikan oleh **{tnt_dict['kebenaran_edit_oleh']}**.")
                            if st.button("✏️ Buka Borang Kemaskini Tuntutan", key=f"btn_open_app_ed_tnt_{chosen_tnt_id}"):
                                st.session_state[ed_app_tnt_key] = True
                                st.rerun()
                        else:
                            st.markdown("##### ✏️ Kemaskini Tuntutan (Kebenaran Edit Diluluskan)")
                            with st.container(border=True):
                                df_kt_ed2 = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis LIKE '%Keluar%' ORDER BY nama ASC", conn)
                                kt_ed2_opts = df_kt_ed2['nama'].tolist() if not df_kt_ed2.empty else [tnt_dict['kategori']]
                                idx_kt2 = kt_ed2_opts.index(tnt_dict['kategori']) if tnt_dict['kategori'] in kt_ed2_opts else 0

                                tep1, tep2 = st.columns(2)
                                tep_dt_resit = tep1.date_input("Tarikh Resit", datetime.strptime(tnt_dict['tarikh_resit'], "%Y-%m-%d"), key=f"tep_dt_resit_{chosen_tnt_id}")
                                tep_kat = tep2.selectbox("Kategori", kt_ed2_opts, index=idx_kt2, key=f"tep_kat_{chosen_tnt_id}")
                                tep_penuntut = tep1.text_input("Nama Penuntut", value=tnt_dict['nama_penuntut'], key=f"tep_pen_{chosen_tnt_id}")
                                tep_no_resit = tep2.text_input("No. Resit Kedai", value=tnt_dict['no_resit_kedai'] or "", key=f"tep_nres_{chosen_tnt_id}")
                                kd_list_t2 = ["Tunai", "Pindahan Bank (Online)", "Cek"]
                                idx_kdt2 = kd_list_t2.index(tnt_dict['kaedah_bayaran_balik']) if tnt_dict['kaedah_bayaran_balik'] in kd_list_t2 else 0
                                tep_kaedah = tep1.selectbox("Kaedah Bayaran Balik", kd_list_t2, index=idx_kdt2, key=f"tep_kd_{chosen_tnt_id}")
                                tep_amaun = tep2.number_input("Amaun Baharu (RM)", min_value=0.01, value=tnt_dict['amaun'], step=10.0, format="%.2f", key=f"tep_amt_{chosen_tnt_id}")
                                tep_bank = st.text_input("Maklumat Akaun Bank", value=tnt_dict['maklumat_akaun_bank'] or "", key=f"tep_bank_{chosen_tnt_id}")
                                tep_butiran = st.text_area("Maksud / Butiran", value=tnt_dict['butiran'], key=f"tep_but_{chosen_tnt_id}")

                                tep_b1, tep_b2 = st.columns(2)
                                if tep_b1.button("💾 Simpan Pindaan & Hantar Semula untuk Semakan", type="primary", key=f"btn_save_app_ed_tnt_{chosen_tnt_id}", use_container_width=True):
                                    kini_tep = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                    c.execute("""UPDATE tuntutan SET tarikh_resit=?, nama_penuntut=?, no_resit_kedai=?, kategori=?,
                                                 butiran=?, amaun=?, kaedah_bayaran_balik=?, maklumat_akaun_bank=?,
                                                 status='Menunggu Semakan Bendahari',
                                                 disemak_oleh=NULL, disemak_pada=NULL, status_dana=NULL,
                                                 disahkan_oleh=NULL, jawatan_pengesah=NULL, disahkan_pada=NULL,
                                                 dikemaskini_oleh=?, dikemaskini_pada=? WHERE id=?""",
                                              (tep_dt_resit.strftime("%Y-%m-%d"), tep_penuntut.strip(), tep_no_resit.strip(), tep_kat,
                                               tep_butiran.strip(), tep_amaun, tep_kaedah, tep_bank.strip(), user['nama_penuh'], kini_tep, chosen_tnt_id))

                                    if tnt_dict['urusniaga_id']:
                                        pv_ref = tnt_dict['no_baucar_pv'] or ""
                                        butiran_lejar_upd = f"[{tnt_dict['no_tuntutan']}] {tep_penuntut.strip()} - {tep_butiran.strip()}"
                                        c.execute("""UPDATE urusniaga SET kategori=?, butiran=?, amaun=?, dikemaskini_oleh=?, dikemaskini_pada=? WHERE id=?""",
                                                  (tep_kat, butiran_lejar_upd, tep_amaun, user['nama_penuh'], kini_tep, tnt_dict['urusniaga_id']))
                                        if pv_ref:
                                            c.execute("""UPDATE payment_vouchers SET nama_penerima=?, kategori=?, butiran=?, amaun=?, dikemaskini_oleh=?, dikemaskini_pada=? WHERE no_baucar=?""",
                                                      (tep_penuntut.strip(), tep_kat, f"Bayaran Balik Tuntutan [{tnt_dict['no_tuntutan']}]: {tep_butiran.strip()}",
                                                       tep_amaun, user['nama_penuh'], kini_tep, pv_ref))

                                    conn.commit()
                                    log_audit(
                                        user['nama_penuh'], "PINDA TUNTUTAN SELEPAS KELULUSAN",
                                        f"{tnt_dict['no_tuntutan']} dipinda (Kebenaran: {tnt_dict['kebenaran_edit_oleh']}). "
                                        f"Amaun asal: RM{tnt_dict['amaun']:,.2f} -> RM{tep_amaun:,.2f}. Dihantar semula untuk semakan Bendahari."
                                    )
                                    st.success(f"Pindaan bagi **{tnt_dict['no_tuntutan']}** berjaya disimpan dan dihantar semula untuk semakan Bendahari!")
                                    st.session_state[ed_app_tnt_key] = False
                                    st.rerun()

                                if tep_b2.button("❌ Batal / Cancel", key=f"btn_cancel_app_ed_tnt_{chosen_tnt_id}", use_container_width=True):
                                    st.session_state[ed_app_tnt_key] = False
                                    st.rerun()

        conn.close()

    # ---------------------------------------------------------------------
    # 4. REKOD & LEJAR URUSNIAGA (BERPAUT DENGAN NO. BAUCAR PV DILULUSKAN)
    # ---------------------------------------------------------------------
    elif pilihan == "📝 Rekod & Lejar Urusniaga":
        st.subheader("📝 Rekod & Lejar Urusniaga")
        conn = get_db_connection()
        
        with st.expander("➕ Daftar Urusniaga Baharu", expanded=user['can_modify']):
            if not user['can_modify']:
                st.warning("Peranan anda adalah 'Paparan Sahaja'. Hanya pegawai dengan kuasa ubah data dibenarkan menambah urusniaga.")
            else:
                if st.session_state.get('trx_success_msg'):
                    st.success(st.session_state['trx_success_msg'])
                    st.session_state['trx_success_msg'] = None

                t_nonce = st.session_state['trx_form_nonce']
                t_jenis = st.selectbox(
                    "Jenis Urusniaga",
                    ["Penerimaan (Masuk)", "Perbelanjaan (Keluar)"],
                    key=f"t_jenis_input_{t_nonce}"
                )

                # =========================================================
                # ALIRAN A: PENERIMAAN (MASUK) - REKOD TERUS
                # =========================================================
                if t_jenis == "Penerimaan (Masuk)":
                    c1, c2 = st.columns([1, 2])
                    t_tarikh = c1.date_input("Tarikh Urusniaga", masa_sekarang(), key=f"t_tarikh_in_{t_nonce}")
                    df_kat = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis = ? ORDER BY nama ASC", conn, params=(t_jenis,))
                    kategori_opts = df_kat['nama'].tolist() if not df_kat.empty else ["Lain-lain Penerimaan"]
                    t_kat = c2.selectbox("Kategori Penerimaan", kategori_opts, key=f"t_kat_in_{t_nonce}")
                    
                    t_butiran = st.text_input("Butiran / Keterangan Penerimaan *", placeholder="cth: Kutipan Solat Jumaat", key=f"t_butiran_in_{t_nonce}")
                    t_amaun = st.number_input("Amaun (RM) *", min_value=0.0, step=10.0, format="%.2f", key=f"t_amaun_in_{t_nonce}")
                    
                    bt_col1, bt_col2 = st.columns(2)
                    if bt_col1.button("➕ Simpan Rekod Penerimaan", type="primary", key=f"btn_simpan_trx_in_{t_nonce}", use_container_width=True):
                        if not t_butiran.strip():
                            st.error("Sila masukkan butiran urusniaga!")
                        elif t_amaun <= 0:
                            st.error("Amaun mestilah lebih besar daripada RM 0.00!")
                        else:
                            thn = t_tarikh.strftime("%Y")
                            bln_thn = t_tarikh.strftime("%Y-%m")
                            st_thn = get_tahun_status(thn)
                            
                            if st_thn == 'Tutup' and not user['is_admin']:
                                st.error(f"Tahun kewangan {thn} telah DITUTUP. Rekod baharu tidak boleh ditambah oleh Bendahari.")
                            else:
                                c = conn.cursor()
                                c.execute("INSERT OR IGNORE INTO tahun_kewangan (tahun, status) VALUES (?, 'Buka')", (thn,))
                                c.execute("""INSERT INTO urusniaga (tarikh, bulan_tahun, jenis, kategori, butiran, amaun, dicipta_oleh, dicipta_pada)
                                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                          (t_tarikh.strftime("%Y-%m-%d"), bln_thn, t_jenis, t_kat, t_butiran.strip(), t_amaun, user['nama_penuh'], masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")))
                                conn.commit()
                                log_audit(user["nama_penuh"], "TAMBAH TRANSAKSI", f"{t_jenis} | RM{t_amaun:,.2f} | {t_kat} | {t_butiran}")
                                st.session_state['trx_success_msg'] = "✅ Rekod Penerimaan (Masuk) berjaya disimpan ke dalam Lejar Urusniaga!"
                                st.session_state['trx_form_nonce'] += 1
                                st.rerun()

                    if bt_col2.button("❌ Batal / Kosongkan Borang", key=f"btn_batal_trx_in_{t_nonce}", use_container_width=True):
                        st.session_state['trx_form_nonce'] += 1
                        st.rerun()

                # =========================================================
                # ALIRAN B: PERBELANJAAN (KELUAR) - WAJIB RUJUK NO. BAUCAR (PV) DILULUSKAN
                # =========================================================
                else:
                    st.info(
                        "🔒 **Kawalan Perbelanjaan:** Bendahari hanya perlu memilih **No. Baucar Bayaran (PV)** yang telah "
                        "dijana di modul **🧾 Baucar Bayaran (PV)** dan diluluskan oleh Pengerusi / Timbalan Pengerusi. "
                        "Semua maklumat baucar akan diisi secara automatik."
                    )

                    df_pv_lulus = pd.read_sql_query(
                        """SELECT id, no_baucar, tarikh_baucar, nama_penerima, no_rujukan, kategori, butiran, amaun,
                                  kaedah_bayaran, disahkan_oleh, jawatan_pengesah, disahkan_pada
                           FROM payment_vouchers
                           WHERE status = 'Diluluskan' AND urusniaga_id IS NULL
                           ORDER BY id ASC""",
                        conn
                    )

                    if df_pv_lulus.empty:
                        st.warning(
                            "⚠️ **Tiada Baucar Bayaran (PV) Berstatus 'Diluluskan' Dijumpai.**\n\n"
                            "Sila jana baucar terlebih dahulu di modul **🧾 Baucar Bayaran (PV)** dan dapatkan kelulusan "
                            "**Pengerusi** atau **Timbalan Pengerusi** sebelum merekodkan perbelanjaan keluar."
                        )
                        st.button("➕ Simpan Rekod Perbelanjaan", disabled=True, key=f"btn_disabled_pv_{t_nonce}")
                    else:
                        pv_opts_map = {
                            f"{r['no_baucar']} | {r['nama_penerima']} | RM {float(r['amaun']):,.2f} ({r['kategori']})": r
                            for _, r in df_pv_lulus.iterrows()
                        }
                        sel_pv_lbl = st.selectbox(
                            "Pilih No. Baucar Bayaran (PV) yang Telah Diluluskan *",
                            list(pv_opts_map.keys()),
                            key=f"t_sel_pv_{t_nonce}"
                        )
                        pv_sel = pv_opts_map[sel_pv_lbl]
                        pv_sel_id = int(pv_sel['id'])

                        # Paparan Auto-Fill maklumat daripada Baucar Bayaran yang dipilih
                        c_pv1, c_pv2, c_pv3 = st.columns(3)
                        t_tarikh_pv = c_pv1.date_input(
                            "Tarikh Transaksi / Bayaran Sebenar *",
                            value=datetime.strptime(pv_sel['tarikh_baucar'], "%Y-%m-%d"),
                            key=f"t_tarikh_pv_{t_nonce}_{pv_sel_id}"
                        )
                        c_pv2.text_input(
                            "No. Baucar (PV)",
                            value=pv_sel['no_baucar'],
                            disabled=True,
                            key=f"t_nobaucar_disp_{t_nonce}_{pv_sel_id}"
                        )
                        c_pv3.text_input(
                            "Kategori Perbelanjaan",
                            value=pv_sel['kategori'],
                            disabled=True,
                            key=f"t_kat_pv_disp_{t_nonce}_{pv_sel_id}"
                        )

                        c_pv4, c_pv5 = st.columns([2, 1])
                        c_pv4.text_input(
                            "Dibayar Kepada (Penerima)",
                            value=pv_sel['nama_penerima'],
                            disabled=True,
                            key=f"t_pen_pv_disp_{t_nonce}_{pv_sel_id}"
                        )
                        c_pv5.text_input(
                            "Amaun Diluluskan (RM)",
                            value=f"RM {float(pv_sel['amaun']):,.2f}",
                            disabled=True,
                            key=f"t_amt_pv_disp_{t_nonce}_{pv_sel_id}"
                        )

                        butiran_auto = f"{pv_sel['nama_penerima']} - {pv_sel['butiran']}" + (
                            f" (Ruj: {pv_sel['no_rujukan']})" if pv_sel['no_rujukan'] else ""
                        )
                        st.text_input(
                            "Butiran Urusniaga (Diambil Automatik dari Baucar)",
                            value=butiran_auto,
                            disabled=True,
                            key=f"t_but_pv_disp_{t_nonce}_{pv_sel_id}"
                        )
                        st.caption(
                            f"✅ Baucar **{pv_sel['no_baucar']}** telah disahkan oleh **{pv_sel['disahkan_oleh']}** "
                            f"({pv_sel['jawatan_pengesah']}) pada {pv_sel['disahkan_pada']} | Kaedah Bayaran: {pv_sel['kaedah_bayaran']}"
                        )

                        bt_col1, bt_col2 = st.columns(2)
                        if bt_col1.button("➕ Simpan & Rekod Baucar ke Lejar", type="primary", key=f"btn_simpan_trx_pv_{t_nonce}_{pv_sel_id}", use_container_width=True):
                            thn = t_tarikh_pv.strftime("%Y")
                            bln_thn = t_tarikh_pv.strftime("%Y-%m")
                            st_thn = get_tahun_status(thn)

                            if st_thn == 'Tutup' and not user['is_admin']:
                                st.error(f"Tahun kewangan {thn} telah DITUTUP. Rekod baharu tidak boleh ditambah oleh Bendahari.")
                            else:
                                c = conn.cursor()
                                # Semak semula status baucar untuk elak rekod berganda
                                c.execute("SELECT status, urusniaga_id FROM payment_vouchers WHERE id = ?", (pv_sel_id,))
                                chk_pv = c.fetchone()
                                if not chk_pv or chk_pv[0] != 'Diluluskan' or chk_pv[1] is not None:
                                    st.error("Baucar ini telah direkodkan sebelum ini atau statusnya telah berubah. Sila muat semula.")
                                else:
                                    kini_str = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                                    amaun_pv = float(pv_sel['amaun'])
                                    c.execute("INSERT OR IGNORE INTO tahun_kewangan (tahun, status) VALUES (?, 'Buka')", (thn,))
                                    c.execute("""INSERT INTO urusniaga (tarikh, bulan_tahun, jenis, kategori, butiran, amaun, no_baucar, dicipta_oleh, dicipta_pada)
                                                 VALUES (?, ?, 'Perbelanjaan (Keluar)', ?, ?, ?, ?, ?, ?)""",
                                              (t_tarikh_pv.strftime("%Y-%m-%d"), bln_thn, pv_sel['kategori'], butiran_auto,
                                               amaun_pv, pv_sel['no_baucar'], user['nama_penuh'], kini_str))
                                    new_trx_id = c.lastrowid

                                    c.execute("UPDATE payment_vouchers SET status = 'Direkod ke Lejar', urusniaga_id = ? WHERE id = ?", (new_trx_id, pv_sel_id))
                                    conn.commit()
                                    log_audit(
                                        user["nama_penuh"],
                                        "REKOD TRANSAKSI DARI BAUCAR",
                                        f"Baucar {pv_sel['no_baucar']} direkodkan ke Lejar (ID #{new_trx_id}) | RM{amaun_pv:,.2f} | {pv_sel['kategori']}"
                                    )
                                    st.session_state['trx_success_msg'] = f"✅ Baucar **{pv_sel['no_baucar']}** (RM {amaun_pv:,.2f}) berjaya direkodkan ke dalam Lejar Urusniaga!"
                                    st.session_state['trx_form_nonce'] += 1
                                    st.rerun()

                        if bt_col2.button("❌ Batal / Set Semula", key=f"btn_batal_trx_pv_{t_nonce}_{pv_sel_id}", use_container_width=True):
                            st.session_state['trx_form_nonce'] += 1
                            st.rerun()

        # Modal Kemaskini Transaksi
        if st.session_state['edit_trx_id'] is not None:
            trx_id = st.session_state['edit_trx_id']
            c = conn.cursor()
            c.execute("SELECT tarikh, jenis, kategori, butiran, amaun, no_baucar FROM urusniaga WHERE id = ?", (trx_id,))
            e_row = c.fetchone()
            if e_row:
                e_no_baucar = e_row[5]
                st.warning(f"✏️ Mengemas kini Transaksi #{trx_id}" + (f" (Rujukan Baucar: {e_no_baucar})" if e_no_baucar else ""))
                with st.container(border=True):
                    if e_no_baucar:
                        st.info(
                            f"🔒 **Transaksi Berpaut Baucar (`{e_no_baucar}`):** Kategori dan Amaun dikunci mengikut baucar "
                            "yang diluluskan. Jika perlu meminda amaun atau butiran baucar, sila mohon kebenaran edit di modul **🧾 Baucar Bayaran (PV)**."
                        )
                        c_e1, c_e2, c_e3 = st.columns(3)
                        e_tarikh = c_e1.date_input("Tarikh Bayaran Sebenar", datetime.strptime(e_row[0], "%Y-%m-%d"), key=f"e_tarikh_{trx_id}")
                        c_e2.text_input("No. Baucar", value=e_no_baucar, disabled=True, key=f"e_nb_{trx_id}")
                        c_e3.text_input("Kategori", value=e_row[2], disabled=True, key=f"e_kat_lock_{trx_id}")
                        st.text_input("Butiran", value=e_row[3], disabled=True, key=f"e_but_lock_{trx_id}")
                        st.text_input("Amaun (RM)", value=f"RM {float(e_row[4]):,.2f}", disabled=True, key=f"e_amt_lock_{trx_id}")

                        ce_btn1, ce_btn2 = st.columns(2)
                        if ce_btn1.button("💾 Simpan Tarikh Baharu", type="primary", key=f"btn_save_edit_{trx_id}", use_container_width=True):
                            thn_e = e_tarikh.strftime("%Y")
                            bln_e = e_tarikh.strftime("%Y-%m")
                            if get_tahun_status(thn_e) == 'Tutup' and not user['is_admin']:
                                st.error(f"Tahun {thn_e} telah ditutup. Hanya Admin dibenarkan membuat pindaan.")
                            else:
                                c.execute("""UPDATE urusniaga SET tarikh=?, bulan_tahun=?, dikemaskini_oleh=?, dikemaskini_pada=? WHERE id = ?""",
                                          (e_tarikh.strftime("%Y-%m-%d"), bln_e, user['nama_penuh'], masa_sekarang().strftime("%Y-%m-%d %H:%M:%S"), trx_id))
                                conn.commit()
                                log_audit(user["nama_penuh"], "KEMASKINI TARIKH TRANSAKSI", f"ID #{trx_id} ({e_no_baucar}) tarikh dikemaskini kepada {e_tarikh.strftime('%Y-%m-%d')}")
                                st.session_state['edit_trx_id'] = None
                                st.success("Tarikh transaksi berjaya dikemaskini!")
                                st.rerun()
                        if ce_btn2.button("❌ Batal / Cancel", key=f"btn_cancel_edit_{trx_id}", use_container_width=True):
                            st.session_state['edit_trx_id'] = None
                            st.rerun()
                    else:
                        c_e1, c_e2, c_e3 = st.columns(3)
                        e_tarikh = c_e1.date_input("Tarikh", datetime.strptime(e_row[0], "%Y-%m-%d"), key=f"e_tarikh_{trx_id}")
                        e_jenis = c_e2.selectbox("Jenis", ["Penerimaan (Masuk)", "Perbelanjaan (Keluar)"], 
                                                 index=0 if "Masuk" in e_row[1] else 1, key=f"e_jenis_{trx_id}")
                        
                        df_e_kat = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis = ? ORDER BY nama ASC", conn, params=(e_jenis,))
                        e_kats = df_e_kat['nama'].tolist() if not df_e_kat.empty else [e_row[2]]
                        cat_idx = e_kats.index(e_row[2]) if e_row[2] in e_kats else 0
                        e_kat = c_e3.selectbox("Kategori", e_kats, index=cat_idx, key=f"e_kat_{trx_id}")
                        
                        e_butiran = st.text_input("Butiran", value=e_row[3], key=f"e_butiran_{trx_id}")
                        e_amaun = st.number_input("Amaun (RM)", min_value=0.01, value=float(e_row[4]), step=10.0, format="%.2f", key=f"e_amaun_{trx_id}")
                        
                        ce_btn1, ce_btn2 = st.columns(2)
                        if ce_btn1.button("💾 Simpan Perubahan", type="primary", key=f"btn_save_edit_{trx_id}", use_container_width=True):
                            thn_e = e_tarikh.strftime("%Y")
                            bln_e = e_tarikh.strftime("%Y-%m")
                            st_thn_e = get_tahun_status(thn_e)
                            
                            if st_thn_e == 'Tutup' and not user['is_admin']:
                                st.error(f"Tahun {thn_e} telah ditutup. Hanya Admin dibenarkan membuat pindaan.")
                            else:
                                c.execute("""UPDATE urusniaga SET tarikh=?, bulan_tahun=?, jenis=?, kategori=?, butiran=?, amaun=?,
                                             dikemaskini_oleh=?, dikemaskini_pada=? WHERE id = ?""",
                                          (e_tarikh.strftime("%Y-%m-%d"), bln_e, e_jenis, e_kat, e_butiran.strip(), e_amaun,
                                           user['nama_penuh'], masa_sekarang().strftime("%Y-%m-%d %H:%M:%S"), trx_id))
                                conn.commit()
                                log_audit(user["nama_penuh"], "KEMASKINI TRANSAKSI", f"ID #{trx_id} dikemaskini: RM{e_amaun:,.2f}")
                                st.session_state['edit_trx_id'] = None
                                st.success("Transaksi berjaya dikemaskini!")
                                st.rerun()
                        if ce_btn2.button("❌ Batal / Cancel", key=f"btn_cancel_edit_{trx_id}", use_container_width=True):
                            st.session_state['edit_trx_id'] = None
                            st.rerun()

        # Modal Pengesahan Pemadaman Transaksi
        if st.session_state['delete_trx_id'] is not None:
            del_id = st.session_state['delete_trx_id']
            c = conn.cursor()
            c.execute("SELECT tarikh, jenis, kategori, butiran, amaun, no_baucar FROM urusniaga WHERE id = ?", (del_id,))
            d_row = c.fetchone()
            if d_row:
                st.error(f"⚠️ PENGESAHAN PEMADAMAN: Transaksi #{del_id} | {d_row[0]} | {d_row[1]} | RM{d_row[4]:,.2f} ({d_row[3]})")
                if d_row[5]:
                    st.info(f"ℹ️ Nota: Rekod ini berpaut pada Baucar **{d_row[5]}**. Jika dipadam, status baucar akan dikembalikan kepada **'Diluluskan'**.")
                st.caption("Tindakan ini adalah KEKAL. Sila taip perkataan **PADAM** di bawah untuk mengesahkan pemadaman:")
                with st.container(border=True):
                    confirm_txt = st.text_input("Taip 'PADAM' untuk mengesahkan:", key="confirm_padam_box")
                    cd_b1, cd_b2 = st.columns(2)
                    if cd_b1.button("🗑️ Sahkan & Padam Rekod", type="primary", use_container_width=True):
                        if confirm_txt.strip().upper() == "PADAM":
                            thn_d = d_row[0][:4]
                            if get_tahun_status(thn_d) == 'Tutup' and not user['is_admin']:
                                st.error(f"Tahun {thn_d} telah ditutup. Tidak boleh dipadam.")
                            else:
                                c.execute("DELETE FROM urusniaga WHERE id = ?", (del_id,))
                                if d_row[5]:
                                    c.execute("UPDATE payment_vouchers SET status = 'Diluluskan', urusniaga_id = NULL WHERE no_baucar = ?", (d_row[5],))
                                conn.commit()
                                log_audit(user["nama_penuh"], "PADAM TRANSAKSI", f"ID #{del_id} dipadamkan: {d_row[3]} (RM{d_row[4]:,.2f})" + (f" | Baucar {d_row[5]} dikembalikan ke status Diluluskan" if d_row[5] else ""))
                                st.session_state['delete_trx_id'] = None
                                st.success(f"Rekod #{del_id} berjaya dipadam!")
                                st.rerun()
                        else:
                            st.error("Perkataan tidak sepadan! Pemadaman dibatalkan.")
                    if cd_b2.button("❌ Batal / Cancel", use_container_width=True):
                        st.session_state['delete_trx_id'] = None
                        st.rerun()

        # Paparan Baucar Daripada Lejar Urusniaga (Mengambil data sebenar dari jadual payment_vouchers)
        if st.session_state['view_voucher_id'] is not None:
            pv_id = st.session_state['view_voucher_id']
            c = conn.cursor()
            c.execute("SELECT id, tarikh, jenis, kategori, butiran, amaun, no_baucar, dicipta_oleh, dicipta_pada FROM urusniaga WHERE id = ?", (pv_id,))
            pv_row = c.fetchone()
            if pv_row:
                no_pv_papar = pv_row[6] if pv_row[6] else f"PV-TRX-{pv_id:04d}"
                pv_trx_dict = None
                if pv_row[6]:
                    c.execute("""SELECT no_baucar, tarikh_baucar, nama_penerima, no_rujukan, kategori, butiran, amaun,
                                        kaedah_bayaran, status, dicipta_oleh, dicipta_pada, disahkan_oleh, jawatan_pengesah,
                                        disahkan_pada, catatan_pengesah, sebab_mohon_edit, kebenaran_edit_oleh, kebenaran_edit_pada
                                 FROM payment_vouchers WHERE no_baucar = ?""", (pv_row[6],))
                    pv_real = c.fetchone()
                    if pv_real:
                        pv_trx_dict = {
                            "no_baucar": pv_real[0], "tarikh_baucar": pv_real[1], "nama_penerima": pv_real[2],
                            "no_rujukan": pv_real[3], "kategori": pv_real[4], "butiran": pv_real[5],
                            "amaun": float(pv_real[6]), "kaedah_bayaran": pv_real[7], "status": pv_real[8],
                            "dicipta_oleh": pv_real[9], "dicipta_pada": pv_real[10], "disahkan_oleh": pv_real[11],
                            "jawatan_pengesah": pv_real[12], "disahkan_pada": pv_real[13], "catatan_pengesah": pv_real[14],
                            "sebab_mohon_edit": pv_real[15], "kebenaran_edit_oleh": pv_real[16], "kebenaran_edit_pada": pv_real[17]
                        }

                if not pv_trx_dict:
                    pv_trx_dict = {
                        "no_baucar": no_pv_papar, "tarikh_baucar": pv_row[1], "nama_penerima": "Seperti dalam butiran",
                        "no_rujukan": "-", "kategori": pv_row[3], "butiran": pv_row[4], "amaun": float(pv_row[5]),
                        "kaedah_bayaran": "Tunai / Bank", "status": "Direkod ke Lejar", "dicipta_oleh": pv_row[7],
                        "dicipta_pada": pv_row[8], "disahkan_oleh": None, "jawatan_pengesah": "", "disahkan_pada": "",
                        "catatan_pengesah": "", "kebenaran_edit_oleh": None
                    }

                st.info(f"📄 Baucar Bayaran {pv_trx_dict['no_baucar']}")
                pdf_trx_bytes = generate_pv_pdf_bytes(pv_trx_dict, nama_surau, alamat_surau)
                st.download_button(
                    label=f"📥 Muat Turun PDF ({pv_trx_dict['no_baucar']}.pdf)", data=pdf_trx_bytes,
                    file_name=f"{pv_trx_dict['no_baucar']}.pdf", mime="application/pdf", type="primary"
                )
                html_pv = build_pv_html(pv_trx_dict, nama_surau, alamat_surau)
                show_printable_html(html_pv, f"Baucar_Bayaran_{pv_trx_dict['no_baucar']}.html", "🖨️ Buka & Cetak Baucar Bayaran")
                if st.button("❌ Tutup Paparan Baucar", type="secondary"):
                    st.session_state['view_voucher_id'] = None
                    st.rerun()

        st.markdown("---")
        flt1, flt2 = st.columns([1, 2])
        
        df_months_l = pd.read_sql_query("SELECT DISTINCT bulan_tahun FROM urusniaga ORDER BY bulan_tahun DESC", conn)
        opt_bln = ["Semua Bulan"] + df_months_l['bulan_tahun'].tolist() if not df_months_l.empty else ["Semua Bulan"]
        pilih_bln = flt1.selectbox("Tapis Mengikut Bulan", opt_bln)
        carian_txt = flt2.text_input("Cari Keterangan / Kategori / No. Baucar", placeholder="Taip kata kunci carian...")
        
        query_sql = "SELECT id, tarikh, bulan_tahun, no_baucar, jenis, kategori, butiran, amaun FROM urusniaga WHERE 1=1"
        q_params = []
        if pilih_bln != "Semua Bulan":
            query_sql += " AND bulan_tahun = ?"
            q_params.append(pilih_bln)
        if carian_txt.strip():
            query_sql += " AND (LOWER(butiran) LIKE ? OR LOWER(kategori) LIKE ? OR LOWER(COALESCE(no_baucar, '')) LIKE ?)"
            q_params.append(f"%{carian_txt.strip().lower()}%")
            q_params.append(f"%{carian_txt.strip().lower()}%")
            q_params.append(f"%{carian_txt.strip().lower()}%")
            
        query_sql += " ORDER BY tarikh DESC, id DESC"
        df_all = pd.read_sql_query(query_sql, conn, params=q_params)
        
        if not df_all.empty:
            df_all_show = df_all.copy()
            df_all_show['no_baucar'] = df_all_show['no_baucar'].fillna("-")
            st.dataframe(
                df_all_show.style.format({"amaun": "RM {:,.2f}"}),
                use_container_width=True, hide_index=True
            )
            
            st.markdown("##### 🛠️ Tindakan ke atas Rekod:")
            act_col1, act_col2, act_col3 = st.columns([1.5, 1, 1])
            selected_id = act_col1.selectbox("Pilih No. ID Transaksi:", df_all['id'].tolist(), key="sel_trx_id")
            
            sel_row = df_all[df_all['id'] == selected_id].iloc[0]
            is_keluar = "Keluar" in sel_row['jenis']
            
            if act_col2.button("📄 Papar & Cetak Baucar", disabled=not is_keluar, use_container_width=True):
                st.session_state['view_voucher_id'] = selected_id
                st.rerun()
                
            if user['can_modify']:
                b_edit, b_del = act_col3.columns(2)
                if b_edit.button("✏️ Edit", use_container_width=True):
                    st.session_state['edit_trx_id'] = selected_id
                    st.rerun()
                if b_del.button("🗑️ Padam", use_container_width=True):
                    st.session_state['delete_trx_id'] = selected_id
                    st.rerun()
                    
            csv_data = df_all.to_csv(index=False).encode('utf-8')
            st.download_button("📊 Muat Turun Data (CSV)", data=csv_data, file_name=f"Lejar_Surau_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv")
        else:
            st.info("Tiada rekod transaksi dijumpai mengikut kriteria tapisan.")
            
        conn.close()

    # ---------------------------------------------------------------------
    # 5. CETAK PENYATA MESYUARAT (BULANAN & TAHUNAN)
    # ---------------------------------------------------------------------
    elif pilihan == "🖨️ Cetak Penyata Mesyuarat":
        st.subheader("🖨️ Jana & Cetak Penyata Kewangan Rasmi")
        conn = get_db_connection()
        
        c_p1, c_p2 = st.columns(2)
        j_laporan = c_p1.selectbox("Pilih Jenis Penyata", ["Laporan Penyata Bulanan (Mesyuarat AJK)", "Laporan Penutupan Akaun Tahunan (AGM)"])
        
        if "Bulanan" in j_laporan:
            df_m = pd.read_sql_query("SELECT DISTINCT bulan_tahun FROM urusniaga ORDER BY bulan_tahun DESC", conn)
            opt_m = df_m['bulan_tahun'].tolist() if not df_m.empty else [datetime.now().strftime("%Y-%m")]
            sel_period = c_p2.selectbox("Pilih Bulan Laporan", opt_m)
            
            if st.button("🖨️ Jana Penyata Bulanan Rasmi", type="primary"):
                c = conn.cursor()
                c.execute("SELECT SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Masuk%'", (sel_period,))
                tot_in = c.fetchone()[0] or 0.0
                c.execute("SELECT SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Keluar%'", (sel_period,))
                tot_out = c.fetchone()[0] or 0.0
                baki = tot_in - tot_out
                
                c.execute("SELECT kategori, SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Keluar%' GROUP BY kategori ORDER BY 2 DESC", (sel_period,))
                cat_rows = c.fetchall()
                c.execute("SELECT tarikh, jenis, kategori, butiran, amaun, no_baucar FROM urusniaga WHERE bulan_tahun = ? ORDER BY tarikh ASC, id ASC", (sel_period,))
                trx_rows = c.fetchall()
                
                cat_html = "".join([f"<tr><td>{cat}</td><td style='text-align:right;'>RM {amt:,.2f}</td></tr>" for cat, amt in cat_rows])
                trx_items = []
                for r in trx_rows:
                    badge = "<span style='color:green;font-weight:bold;'>MASUK</span>" if "Masuk" in r[1] else "<span style='color:red;font-weight:bold;'>KELUAR</span>"
                    pv_col = r[5] if r[5] else "-"
                    trx_items.append(f"<tr><td>{r[0]}</td><td>{pv_col}</td><td>{badge}</td><td>{r[2]}</td><td>{r[3]}</td><td style='text-align:right;'>RM {r[4]:,.2f}</td></tr>")
                trx_html = "".join(trx_items)
                
                html_rep = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Laporan Kewangan Bulanan - {sel_period}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; background: #fff; color: #222; }}
        .header {{ text-align: center; border-bottom: 3px double #1E4C2B; padding-bottom: 12px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 24px; color: #1E4C2B; text-transform: uppercase; }}
        .summary-grid {{ display: flex; justify-content: space-between; margin-bottom: 25px; }}
        .card {{ width: 31%; border: 1px solid #ddd; padding: 12px; border-radius: 4px; box-sizing: border-box; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 13px; }}
        th, td {{ border: 1px solid #ccc; padding: 8px 10px; }}
        th {{ background-color: #1E4C2B; color: #fff; text-align: left; }}
        .sign-area {{ display: flex; justify-content: space-between; margin-top: 50px; page-break-inside: avoid; }}
        .sign-box {{ width: 28%; text-align: center; border-top: 1px solid #000; padding-top: 5px; font-weight: bold; font-size: 13px; }}
        @media print {{ .btn {{ display: none; }} body {{ padding: 0; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:8px 16px;border:none;cursor:pointer;border-radius:4px;margin-bottom:15px;font-weight:bold;">🖨️ Cetak / Simpan sebagai PDF</button>
    <div class="header">
        <h1>{nama_surau}</h1>
        <h2>PENYATA KEWANGAN BULANAN (MESYUARAT JAWATANKUASA)</h2>
        <div>Tempoh Bulan: {sel_period} | Tarikh Cetakan: {datetime.now().strftime("%d/%m/%Y")}</div>
    </div>
    <div class="summary-grid">
        <div class="card" style="background:#eaf5ea;border-color:#274E13;">
            <div style="font-size:12px;font-weight:bold;color:#274E13;">JUMLAH PENERIMAAN (MASUK)</div>
            <div style="font-size:18px;font-weight:bold;color:#274E13;margin-top:5px;">RM {tot_in:,.2f}</div>
        </div>
        <div class="card" style="background:#fdeeee;border-color:#990000;">
            <div style="font-size:12px;font-weight:bold;color:#990000;">JUMLAH PERBELANJAAN (KELUAR)</div>
            <div style="font-size:18px;font-weight:bold;color:#990000;margin-top:5px;">RM {tot_out:,.2f}</div>
        </div>
        <div class="card" style="background:#eef4fd;border-color:#1155CC;">
            <div style="font-size:12px;font-weight:bold;color:#1155CC;">LEBIHAN / (KURANGAN) BERSIH</div>
            <div style="font-size:18px;font-weight:bold;color:#1155CC;margin-top:5px;">RM {baki:,.2f}</div>
        </div>
    </div>
    <h3 style="color:#1E4C2B;">1. Pecahan Perbelanjaan Mengikut Kategori</h3>
    <table>
        <tr><th>Kategori Perbelanjaan</th><th style="width:180px;text-align:right;">Jumlah (RM)</th></tr>
        {cat_html if cat_rows else "<tr><td colspan='2'>Tiada perbelanjaan.</td></tr>"}
    </table>
    <h3 style="color:#1E4C2B;">2. Senarai Penuh Urusniaga & Transaksi</h3>
    <table>
        <tr><th>Tarikh</th><th>No. Baucar</th><th>Jenis</th><th>Kategori</th><th>Butiran</th><th style="text-align:right;">Amaun (RM)</th></tr>
        {trx_html if trx_rows else "<tr><td colspan='6'>Tiada transaksi.</td></tr>"}
    </table>
    <div class="sign-area">
        <div class="sign-box">Disediakan Oleh<br>(Bendahari)</div>
        <div class="sign-box">Disemak Oleh<br>(Pemeriksa Kira-Kira 1)</div>
        <div class="sign-box">Disahkan Oleh<br>(Pengerusi Surau)</div>
    </div>
    <script>window.print();</script>
</body>
</html>"""
                show_printable_html(html_rep, f"Penyata_Bulanan_{sel_period}.html")
        else:
            df_y = pd.read_sql_query("SELECT DISTINCT SUBSTR(tarikh, 1, 4) as thn FROM urusniaga ORDER BY thn DESC", conn)
            opt_y = df_y['thn'].tolist() if not df_y.empty else [datetime.now().strftime("%Y")]
            sel_year = c_p2.selectbox("Pilih Tahun Laporan (AGM)", opt_y)
            
            if st.button("🖨️ Jana Penyata Tahunan Rasmi (AGM)", type="primary"):
                c = conn.cursor()
                status_thn = get_tahun_status(sel_year)
                months_names = ["Januari", "Februari", "Mac", "April", "Mei", "Jun", "Julai", "Ogos", "September", "Oktober", "November", "Disember"]
                rows_html = ""
                grand_in, grand_out = 0.0, 0.0
                for m in range(1, 13):
                    m_str = f"{sel_year}-{m:02d}"
                    c.execute("SELECT SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Masuk%'", (m_str,))
                    mi = c.fetchone()[0] or 0.0
                    c.execute("SELECT SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Keluar%'", (m_str,))
                    mo = c.fetchone()[0] or 0.0
                    diff = mi - mo
                    grand_in += mi
                    grand_out += mo
                    diff_color = 'green' if diff >= 0 else 'red'
                    rows_html += f"<tr><td>{months_names[m-1]} ({m_str})</td><td style='text-align:right;'>RM {mi:,.2f}</td><td style='text-align:right;'>RM {mo:,.2f}</td><td style='text-align:right;font-weight:bold;color:{diff_color};'>RM {diff:,.2f}</td></tr>"

                grand_diff = grand_in - grand_out
                html_agm = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Penyata Kewangan Tahunan - {sel_year}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; background: #fff; color: #222; }}
        .header {{ text-align: center; border-bottom: 3px double #1E4C2B; padding-bottom: 12px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 24px; color: #1E4C2B; text-transform: uppercase; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 25px; font-size: 13px; }}
        th, td {{ border: 1px solid #ccc; padding: 9px 10px; }}
        th {{ background-color: #1E4C2B; color: #fff; text-align: left; }}
        .sign-area {{ display: flex; justify-content: space-between; margin-top: 60px; }}
        .sign-box {{ width: 28%; text-align: center; border-top: 1px solid #000; padding-top: 5px; font-weight: bold; font-size: 13px; }}
        @media print {{ .btn {{ display: none; }} body {{ padding: 0; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:8px 16px;border:none;cursor:pointer;border-radius:4px;margin-bottom:15px;font-weight:bold;">🖨️ Cetak / Simpan sebagai PDF</button>
    <div class="header">
        <h1>{nama_surau}</h1>
        <h2>PENYATA PENUTUPAN AKAUN TAHUNAN (MESYUARAT AGUNG TAHUNAN - AGM)</h2>
        <div>Tahun Kewangan: {sel_year} (Status: {status_thn.upper()}) | Tarikh Cetakan: {datetime.now().strftime("%d/%m/%Y")}</div>
    </div>
    <table>
        <tr><th>Bulan</th><th style="text-align:right;">Penerimaan (Masuk)</th><th style="text-align:right;">Perbelanjaan (Keluar)</th><th style="text-align:right;">Lebihan / (Kurangan)</th></tr>
        {rows_html}
        <tr style="background:#f4f6f9;font-weight:bold;font-size:14px;">
            <td>JUMLAH KESELURUHAN SETAHUN</td>
            <td style="text-align:right;color:#274E13;">RM {grand_in:,.2f}</td>
            <td style="text-align:right;color:#990000;">RM {grand_out:,.2f}</td>
            <td style="text-align:right;color:#1155CC;">RM {grand_diff:,.2f}</td>
        </tr>
    </table>
    <div class="sign-area">
        <div class="sign-box">Disediakan Oleh<br>(Bendahari)</div>
        <div class="sign-box">Disemak & Diaudit Oleh<br>(Juruaudit Dalaman)</div>
        <div class="sign-box">Disahkan Oleh<br>(Pengerusi Surau)</div>
    </div>
    <script>window.print();</script>
</body>
</html>"""
                show_printable_html(html_agm, f"Penyata_Tahunan_AGM_{sel_year}.html")
                
        conn.close()

    # ---------------------------------------------------------------------
    # 6. PENGURUSAN KATEGORI
    # ---------------------------------------------------------------------
    elif pilihan == "⚙️ Pengurusan Kategori":
        st.subheader("⚙️ Pengurusan Kategori Aliran Tunai")
        conn = get_db_connection()
        
        if user['can_modify']:
            with st.expander("➕ Tambah Kategori Baharu"):
                with st.form("form_tambah_kat", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    k_jenis = c1.selectbox("Jenis Aliran", ["Penerimaan (Masuk)", "Perbelanjaan (Keluar)"])
                    k_nama = c2.text_input("Nama Kategori Baharu")
                    
                    fc1, fc2 = st.columns(2)
                    btn_simpan_k = fc1.form_submit_button("💾 Simpan Kategori", type="primary", use_container_width=True)
                    btn_batal_k = fc2.form_submit_button("❌ Batal / Reset", use_container_width=True)
                    if btn_simpan_k:
                        if k_nama.strip():
                            try:
                                c = conn.cursor()
                                c.execute("INSERT INTO kategori (jenis, nama) VALUES (?, ?)", (k_jenis, k_nama.strip()))
                                conn.commit()
                                log_audit(user["nama_penuh"], "TAMBAH KATEGORI", f"{k_jenis} - {k_nama.strip()}")
                                st.success("Kategori berjaya ditambah!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Nama kategori ini sudah wujud!")
                        else:
                            st.warning("Sila masukkan nama kategori.")

            with st.expander("✏️ Kemaskini / Ubah Nama Kategori Sedia Ada"):
                df_kats_all = pd.read_sql_query("SELECT id, jenis, nama FROM kategori ORDER BY jenis DESC, nama ASC", conn)
                if not df_kats_all.empty:
                    k_nonce = st.session_state['kat_edit_nonce']
                    kat_options = {f"[{r['jenis']}] {r['nama']}": (r['id'], r['nama']) for _, r in df_kats_all.iterrows()}
                    pilih_kat_label = st.selectbox("Pilih Kategori untuk Diubah:", list(kat_options.keys()), key=f"sel_kat_edit_{k_nonce}")
                    
                    kat_id_edit, nama_kat_asal = kat_options[pilih_kat_label]
                    nama_kat_baru = st.text_input("Nama Baharu Kategori:", value=nama_kat_asal, key=f"edit_kat_input_{kat_id_edit}_{k_nonce}")
                    
                    st.caption("ℹ️ Nota: Menukar nama kategori akan mengemas kini semua transaksi lejar, baucar, dan tuntutan secara automatik demi integriti data.")
                    
                    b_c1, b_c2 = st.columns(2)
                    if b_c1.button("💾 Simpan Perubahan Nama Kategori", type="primary", use_container_width=True):
                        if nama_kat_baru.strip() and nama_kat_baru.strip() != nama_kat_asal:
                            try:
                                c = conn.cursor()
                                c.execute("UPDATE kategori SET nama = ? WHERE id = ?", (nama_kat_baru.strip(), kat_id_edit))
                                c.execute("UPDATE urusniaga SET kategori = ? WHERE kategori = ?", (nama_kat_baru.strip(), nama_kat_asal))
                                c.execute("UPDATE payment_vouchers SET kategori = ? WHERE kategori = ?", (nama_kat_baru.strip(), nama_kat_asal))
                                c.execute("UPDATE tuntutan SET kategori = ? WHERE kategori = ?", (nama_kat_baru.strip(), nama_kat_asal))
                                conn.commit()
                                log_audit(user["nama_penuh"], "KEMASKINI KATEGORI", f"Kategori '{nama_kat_asal}' ditukar ke '{nama_kat_baru.strip()}'")
                                st.success(f"Kategori '{nama_kat_asal}' berjaya ditukar kepada '{nama_kat_baru.strip()}'!")
                                st.session_state['kat_edit_nonce'] += 1
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Nama kategori tersebut telah digunakan!")
                        else:
                            st.warning("Sila masukkan nama baharu yang berbeza.")
                    if b_c2.button("❌ Batal / Cancel", key="btn_batal_kat", use_container_width=True):
                        st.session_state['kat_edit_nonce'] += 1
                        st.rerun()
                            
        st.markdown("#### Senarai Kategori Sedia Ada")
        df_kats = pd.read_sql_query("SELECT id, jenis, nama FROM kategori ORDER BY jenis DESC, nama ASC", conn)
        st.dataframe(df_kats, use_container_width=True, hide_index=True)
        
        col_k1, col_k2 = st.columns([1, 3])
        if col_k1.button("🖨️ Cetak Senarai Kategori"):
            c = conn.cursor()
            c.execute("SELECT id, nama FROM kategori WHERE jenis LIKE '%Masuk%' ORDER BY nama ASC")
            incomes = c.fetchall()
            c.execute("SELECT id, nama FROM kategori WHERE jenis LIKE '%Keluar%' ORDER BY nama ASC")
            expenses = c.fetchall()
            
            inc_html = "".join([f"<tr><td>{i+1}</td><td>{row[1]}</td></tr>" for i, row in enumerate(incomes)])
            exp_html = "".join([f"<tr><td>{i+1}</td><td>{row[1]}</td></tr>" for i, row in enumerate(expenses)])

            html_kats = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Senarai Kategori Kewangan</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th, td {{ border: 1px solid #333; padding: 7px 10px; }}
        th {{ background: #1E4C2B; color: white; }}
        @media print {{ .btn {{ display: none; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:8px 16px;border:none;cursor:pointer;border-radius:4px;margin-bottom:15px;font-weight:bold;">🖨️ Cetak / Simpan PDF</button>
    <h2 style="color:#1E4C2B;text-align:center;margin-bottom:3px;">{nama_surau}</h2>
    <h3 style="text-align:center;margin-top:0;">CARTA KATEGORI PENERIMAAN (MASUK) & PERBELANJAAN (KELUAR)</h3>
    <div style="font-size:12px;margin-bottom:10px;">Tarikh Cetakan: {masa_sekarang().strftime("%d/%m/%Y %H:%M")}</div>
    <div style="display:flex; justify-content:space-between; margin-top:20px;">
        <div style="width:48%;">
            <h4 style="color:#274E13;margin-bottom:5px;">1. Kategori Penerimaan (Duit Masuk)</h4>
            <table><tr><th style="width:40px;">Bil</th><th>Nama Kategori Masuk</th></tr>{inc_html}</table>
        </div>
        <div style="width:48%;">
            <h4 style="color:#990000;margin-bottom:5px;">2. Kategori Perbelanjaan (Duit Keluar)</h4>
            <table><tr><th style="width:40px;">Bil</th><th>Nama Kategori Keluar</th></tr>{exp_html}</table>
        </div>
    </div>
    <script>window.print();</script>
</body>
</html>"""
            show_printable_html(html_kats, "Senarai_Kategori_Surau.html")
            
        conn.close()

    # ---------------------------------------------------------------------
    # 7. LOG AUDIT & INTEGRITI DATA
    # ---------------------------------------------------------------------
    elif pilihan == "🔒 Log Audit & Integriti":
        st.subheader("🔒 Jejak Audit Keselamatan & Integriti (Audit Trail)")
        st.caption("Semua aktiviti log masuk, baucar bayaran, semakan & pengesahan tuntutan, dan urusniaga direkodkan secara kekal.")
        conn = get_db_connection()
        df_audit = pd.read_sql_query("SELECT id, tarikh_masa, pengguna, tindakan, butiran FROM audit_log ORDER BY id DESC LIMIT 500", conn)
        conn.close()
        st.dataframe(df_audit, use_container_width=True, hide_index=True)

    # ---------------------------------------------------------------------
    # 8. PENTADBIRAN SISTEM (ADMIN ONLY)
    # ---------------------------------------------------------------------
    elif pilihan == "🛡️ Pentadbiran Sistem" and user['is_admin']:
        st.subheader("🛡️ Panel Pentadbiran & Kawalan Keselamatan")
        conn = get_db_connection()
        
        adm_t1, adm_t_pwd, adm_t2, adm_t3, adm_t4, adm_t5, adm_t6 = st.tabs([
            "👥 Pengurusan Pengguna & Status",
            "🔑 Reset Kata Laluan",
            "👔 Jawatan & Hak Akses", 
            "📅 Tutup/Buka Tahun", 
            "💾 Sandaran & Pulih (Backup)", 
            "🗄️ Statistik Database",
            "🕌 Profil & Nama Surau"
        ])
        
        with adm_t1:
            st.markdown("##### Senarai Pengguna & Status Keahlian")
            df_u = pd.read_sql_query("SELECT id, username, nama_penuh, no_telefon, peranan, status FROM users ORDER BY id ASC", conn)
            df_u['Status Keahlian'] = df_u['status'].apply(lambda s: "🟢 Aktif" if s == "Aktif" else "🔴 Tidak Aktif")
            st.dataframe(df_u[['id', 'username', 'nama_penuh', 'no_telefon', 'peranan', 'Status Keahlian']], use_container_width=True, hide_index=True)
            
            col_pu1, col_pu2 = st.columns([1, 3])
            if col_pu1.button("🖨️ Cetak Senarai Pengguna"):
                c = conn.cursor()
                c.execute("SELECT u.id, u.username, u.nama_penuh, u.no_telefon, u.peranan, j.boleh_ubah_data, u.status FROM users u LEFT JOIN jawatan j ON u.peranan = j.nama_jawatan ORDER BY u.id ASC")
                u_rows = c.fetchall()
                tbl_rows = "".join([f"<tr><td>{i+1}</td><td>{r[1]}</td><td><strong>{r[2]}</strong></td><td>{r[3] or '-'}</td><td>{r[4]}</td><td>{'Boleh Ubah Data' if (r[4]=='Admin' or r[5]==1) else ('Pengesah Baucar & Tuntutan' if r[4] in ['Pengerusi', 'Timbalan Pengerusi'] else 'View Only')}</td><td>{r[6]}</td></tr>" for i, r in enumerate(u_rows)])
                
                html_users = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Senarai Pengguna & Pegawai</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 13px; }}
        th, td {{ border: 1px solid #333; padding: 8px 10px; }}
        th {{ background: #1E4C2B; color: white; }}
        @media print {{ .btn {{ display: none; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:8px 16px;border:none;cursor:pointer;border-radius:4px;margin-bottom:15px;font-weight:bold;">🖨️ Cetak / Simpan PDF</button>
    <h2 style="color:#1E4C2B;text-align:center;margin-bottom:3px;">{nama_surau}</h2>
    <h3 style="text-align:center;margin-top:0;">SENARAI PEGAWAI & PENGGUNA SISTEM KEWANGAN SURAU</h3>
    <div style="font-size:12px;margin-bottom:10px;">Tarikh Cetakan: {masa_sekarang().strftime("%d/%m/%Y %H:%M")}</div>
    <table>
        <tr><th>Bil</th><th>Username</th><th>Nama Penuh Pegawai</th><th>No. Telefon</th><th>Jawatan / Peranan</th><th>Kuasa Akses Data</th><th>Status Keahlian</th></tr>
        {tbl_rows}
    </table>
    <script>window.print();</script>
</body>
</html>"""
                show_printable_html(html_users, "Senarai_Pengguna.html")

            with st.expander("➕ Tambah Pengguna Baharu"):
                with st.form("form_add_user", clear_on_submit=True):
                    cu1, cu2 = st.columns(2)
                    nu_user = cu1.text_input("Username")
                    nu_pass = cu2.text_input("Kata Laluan Awal", type="password")
                    nu_nama = cu1.text_input("Nama Penuh Pegawai")
                    nu_tel = cu2.text_input("No. Telefon")
                    
                    roles_list = get_senarai_jawatan()
                    nu_role = cu1.selectbox("Pilih Jawatan / Peranan", roles_list)
                    nu_status = cu2.selectbox("Status Keahlian", ["Aktif", "Tidak Aktif"])
                    
                    f_u1, f_u2 = st.columns(2)
                    if f_u1.form_submit_button("💾 Daftarkan Pengguna", type="primary", use_container_width=True):
                        if nu_user.strip() and nu_pass.strip() and nu_nama.strip():
                            try:
                                c = conn.cursor()
                                c.execute("INSERT INTO users (username, password_hash, nama_penuh, no_telefon, peranan, status) VALUES (?, ?, ?, ?, ?, ?)",
                                          (nu_user.strip(), hash_password(nu_pass.strip()), nu_nama.strip(), nu_tel.strip(), nu_role, nu_status))
                                conn.commit()
                                log_audit(user["nama_penuh"], "TAMBAH PENGGUNA", f"{nu_user} ({nu_role}) - Status: {nu_status}")
                                st.success(f"Pengguna '{nu_user}' berjaya didaftarkan!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Username ini telah wujud!")
                        else:
                            st.warning("Sila lengkapkan maklumat wajib.")
                    if f_u2.form_submit_button("❌ Batal / Kosongkan", use_container_width=True):
                        pass

            with st.expander("✏️ Kemaskini Status / Maklumat Pengguna Sedia Ada"):
                if not df_u.empty:
                    u_map = {f"#{r['id']} - {r['nama_penuh']} ({r['username']})": r for _, r in df_u.iterrows()}
                    pilih_user_label = st.selectbox("Pilih Pengguna untuk Dikemaskini:", list(u_map.keys()))
                    usr_data = u_map[pilih_user_label]
                    
                    with st.form("form_update_user_status"):
                        col_eu1, col_eu2 = st.columns(2)
                        up_nama = col_eu1.text_input("Nama Penuh Pegawai", value=usr_data['nama_penuh'])
                        up_tel = col_eu2.text_input("No. Telefon", value=usr_data['no_telefon'] if usr_data['no_telefon'] != "Tiada" else "")
                        
                        r_opts = get_senarai_jawatan()
                        up_role = col_eu1.selectbox("Jawatan / Peranan", r_opts, index=r_opts.index(usr_data['peranan']) if usr_data['peranan'] in r_opts else 0)
                        up_status = col_eu2.selectbox("Status Keahlian", ["Aktif", "Tidak Aktif"], index=0 if usr_data['status'] == 'Aktif' else 1)
                        
                        e_u1, e_u2 = st.columns(2)
                        if e_u1.form_submit_button("💾 Simpan Kemaskini Pengguna", type="primary", use_container_width=True):
                            c = conn.cursor()
                            c.execute("UPDATE users SET nama_penuh = ?, no_telefon = ?, peranan = ?, status = ? WHERE id = ?",
                                      (up_nama.strip(), up_tel.strip(), up_role, up_status, int(usr_data['id'])))
                            conn.commit()
                            log_audit(user["nama_penuh"], "KEMASKINI PENGGUNA", f"Pengguna #{usr_data['id']} ({usr_data['username']}): Jawatan={up_role}, Status={up_status}")
                            st.success(f"Maklumat pengguna '{usr_data['username']}' berjaya dikemas kini!")
                            st.rerun()
                        if e_u2.form_submit_button("❌ Batal / Reset", use_container_width=True):
                            pass

        with adm_t_pwd:
            st.markdown("##### 🔑 Reset / Kemaskini Kata Laluan Pengguna (Mengikut ID)")
            st.caption("Pilih ID pengguna daripada senarai di bawah untuk menetapkan kata laluan baharu.")
            
            df_u_pwd = pd.read_sql_query("SELECT id, username, nama_penuh, peranan, status FROM users ORDER BY id ASC", conn)
            if not df_u_pwd.empty:
                st.dataframe(
                    df_u_pwd.rename(columns={
                        'id': 'ID', 'username': 'Username', 'nama_penuh': 'Nama Penuh', 'peranan': 'Jawatan', 'status': 'Status'
                    }),
                    use_container_width=True, hide_index=True
                )
                
                u_pwd_map = {f"ID #{r['id']} - {r['username']} ({r['nama_penuh']} | {r['peranan']})": r for _, r in df_u_pwd.iterrows()}
                pilih_pwd_user = st.selectbox("Pilih ID Pengguna:", list(u_pwd_map.keys()), key="sel_pwd_panel")
                u_pwd_target = u_pwd_map[pilih_pwd_user]
                
                with st.form("form_reset_pwd_panel", clear_on_submit=True):
                    st.info(f"Menetapkan kata laluan baharu bagi **ID #{u_pwd_target['id']}** — Username: `{u_pwd_target['username']}` ({u_pwd_target['nama_penuh']})")
                    cpw1, cpw2 = st.columns(2)
                    new_pwd_input = cpw1.text_input("Kata Laluan Baharu (min. 4 aksara):", type="password")
                    confirm_pwd_input = cpw2.text_input("Sahkan Kata Laluan Baharu:", type="password")
                    
                    rp_b1, rp_b2 = st.columns(2)
                    if rp_b1.form_submit_button("💾 Simpan Kata Laluan Baharu", type="primary", use_container_width=True):
                        if not new_pwd_input or len(new_pwd_input.strip()) < 4:
                            st.warning("Kata laluan mestilah sekurang-kurangnya 4 aksara.")
                        elif new_pwd_input.strip() != confirm_pwd_input.strip():
                            st.error("Pengesahan kata laluan tidak sepadan! Sila masukkan semula.")
                        else:
                            c = conn.cursor()
                            c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_pwd_input.strip()), int(u_pwd_target['id'])))
                            conn.commit()
                            log_audit(user["nama_penuh"], "RESET KATA LALUAN", f"Kata laluan bagi ID #{u_pwd_target['id']} ('{u_pwd_target['username']}') telah dikemaskini oleh Admin.")
                            st.success(f"✅ Kata laluan bagi ID #{u_pwd_target['id']} ('{u_pwd_target['username']}') berjaya dikemaskini!")
                    if rp_b2.form_submit_button("❌ Batal / Reset", use_container_width=True):
                        pass

        with adm_t2:
            st.markdown("##### Pengurusan Jawatan & Bidang Kuasa Dinamik")
            df_j = pd.read_sql_query("SELECT id, nama_jawatan, boleh_ubah_data, keterangan FROM jawatan ORDER BY id ASC", conn)
            df_j['Kuasa Akses'] = df_j['boleh_ubah_data'].map({1: 'Boleh Ubah & Rekod Data', 0: 'Paparan Sahaja / Pengesah'})
            st.dataframe(df_j[['id', 'nama_jawatan', 'Kuasa Akses', 'keterangan']], use_container_width=True, hide_index=True)
            
            with st.expander("➕ Tambah Jawatan Baharu"):
                with st.form("form_add_jawatan", clear_on_submit=True):
                    nj_nama = st.text_input("Nama Jawatan Baharu (cth: Penolong Bendahari)")
                    nj_kuasa = st.checkbox("Boleh Mengubah & Merekod Data (Kuasa Bendahari)")
                    nj_desc = st.text_input("Keterangan Bidang Tugas")
                    
                    j_b1, j_b2 = st.columns(2)
                    if j_b1.form_submit_button("💾 Simpan Jawatan", type="primary", use_container_width=True):
                        if nj_nama.strip():
                            try:
                                c = conn.cursor()
                                c.execute("INSERT INTO jawatan (nama_jawatan, boleh_ubah_data, keterangan) VALUES (?, ?, ?)",
                                          (nj_nama.strip(), 1 if nj_kuasa else 0, nj_desc.strip()))
                                conn.commit()
                                log_audit(user["nama_penuh"], "TAMBAH JAWATAN", f"Jawatan: {nj_nama.strip()} (Kuasa: {nj_kuasa})")
                                st.success("Jawatan berjaya ditambah!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Jawatan ini sudah wujud!")
                        else:
                            st.warning("Sila masukkan nama jawatan.")
                    if j_b2.form_submit_button("❌ Batal / Reset", use_container_width=True):
                        pass

            with st.expander("✏️ Kemaskini Jawatan Sedia Ada"):
                if not df_j.empty:
                    j_map = {f"#{r['id']} - {r['nama_jawatan']}": r for _, r in df_j.iterrows()}
                    sel_j_label = st.selectbox("Pilih Jawatan:", list(j_map.keys()))
                    j_target = j_map[sel_j_label]
                    
                    with st.form("form_edit_jawatan"):
                        ej_nama = st.text_input("Nama Jawatan:", value=j_target['nama_jawatan'])
                        ej_kuasa = st.checkbox("Boleh Mengubah & Merekod Data", value=bool(j_target['boleh_ubah_data'] == 1))
                        ej_desc = st.text_input("Keterangan Tugas:", value=j_target['keterangan'] or "")
                        
                        ej_b1, ej_b2 = st.columns(2)
                        if ej_b1.form_submit_button("💾 Simpan Perubahan Jawatan", type="primary", use_container_width=True):
                            if ej_nama.strip():
                                try:
                                    c = conn.cursor()
                                    c.execute("UPDATE jawatan SET nama_jawatan = ?, boleh_ubah_data = ?, keterangan = ? WHERE id = ?",
                                              (ej_nama.strip(), 1 if ej_kuasa else 0, ej_desc.strip(), int(j_target['id'])))
                                    c.execute("UPDATE users SET peranan = ? WHERE peranan = ?", (ej_nama.strip(), j_target['nama_jawatan']))
                                    conn.commit()
                                    log_audit(user["nama_penuh"], "KEMASKINI JAWATAN", f"Jawatan #{j_target['id']} dikemaskini kepada '{ej_nama.strip()}'")
                                    st.success("Jawatan berjaya dikemas kini!")
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error("Nama jawatan tersebut sudah digunakan!")
                            else:
                                st.warning("Nama jawatan tidak boleh dibiarkan kosong.")
                        if ej_b2.form_submit_button("❌ Batal / Reset", use_container_width=True):
                            pass

        with adm_t3:
            st.markdown("##### Kawalan Penutupan Tahun Kewangan")
            df_thn = pd.read_sql_query("SELECT tahun, status, ditutup_oleh, ditutup_pada FROM tahun_kewangan ORDER BY tahun DESC", conn)
            st.dataframe(df_thn, use_container_width=True, hide_index=True)
            
            ct1, ct2 = st.columns(2)
            thn_pilih = ct1.selectbox("Pilih Tahun", df_thn['tahun'].tolist() if not df_thn.empty else [datetime.now().strftime("%Y")])
            act_thn = ct2.radio("Tindakan", ["Kunci / Tutup Tahun", "Buka Semula Tahun"])
            if st.button("Laksanakan Status Tahun", type="primary"):
                c = conn.cursor()
                if "Tutup" in act_thn:
                    c.execute("UPDATE tahun_kewangan SET status = 'Tutup', ditutup_oleh = ?, ditutup_pada = ? WHERE tahun = ?",
                              (user['nama_penuh'], masa_sekarang().strftime("%Y-%m-%d %H:%M:%S"), str(thn_pilih)))
                    log_audit(user["nama_penuh"], "TUTUP TAHUN", f"Tahun {thn_pilih} ditutup.")
                    st.success(f"Tahun {thn_pilih} telah DITUTUP.")
                else:
                    c.execute("UPDATE tahun_kewangan SET status = 'Buka', ditutup_oleh = NULL, ditutup_pada = NULL WHERE tahun = ?", (str(thn_pilih),))
                    log_audit(user["nama_penuh"], "BUKA TAHUN", f"Tahun {thn_pilih} dibuka semula.")
                    st.success(f"Tahun {thn_pilih} telah DIBUKA SEMULA.")
                conn.commit()
                st.rerun()

        with adm_t4:
            st.markdown("##### 💾 Sandaran & Pemulihan Pangkalan Data (.db)")
            if os.path.exists('sistem_surau.db'):
                with open('sistem_surau.db', 'rb') as f_db:
                    st.download_button("💾 Muat Turun Fail Sandaran Pangkalan Data (sistem_surau.db)", data=f_db, file_name=f"Backup_Surau_{masa_sekarang().strftime('%Y%m%d_%H%M%S')}.db", mime="application/x-sqlite3", type="primary")
            
            st.markdown("---")
            st.markdown("##### 🔄 Pulihkan Pangkalan Data dari Fail (.db)")
            uploaded_db = st.file_uploader("Pilih fail .db untuk dipulihkan", type=["db", "sqlite", "sqlite3"])
            if uploaded_db is not None:
                if st.button("⚠️ Sahkan & Pulihkan Database", type="secondary"):
                    shutil.copy2('sistem_surau.db', f"sistem_surau_pre_restore_{masa_sekarang().strftime('%Y%m%d_%H%M%S')}.bak")
                    with open('sistem_surau.db', 'wb') as f_dest:
                        f_dest.write(uploaded_db.getbuffer())
                    log_audit(user["nama_penuh"], "PULIHKAN DATABASE", "Database dipulihkan via fail muat naik Web.")
                    st.success("Pangkalan data berjaya dipulihkan!")
                    st.rerun()

        with adm_t5:
            st.markdown("##### 🗄️ Statistik Fail Pangkalan Data SQLite3")
            db_size = os.path.getsize('sistem_surau.db') / 1024 if os.path.exists('sistem_surau.db') else 0
            st.write(f"**Lokasi Fail:** `{os.path.realpath('sistem_surau.db')}`")
            st.write(f"**Saiz Fail Semasa:** `{db_size:,.2f} KB`")
            
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM urusniaga"); n_trx = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM payment_vouchers"); n_pv = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM tuntutan"); n_tnt = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users"); n_usr = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM kategori"); n_kat = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM jawatan"); n_jwt = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM audit_log"); n_aud = c.fetchone()[0]
            
            st.write(f"• **Jumlah Baucar Bayaran (PV):** {n_pv:,} rekod")
            st.write(f"• **Jumlah Tuntutan Perbelanjaan:** {n_tnt:,} rekod")
            st.write(f"• **Jumlah Urusniaga:** {n_trx:,} rekod")
            st.write(f"• **Jumlah Pengguna:** {n_usr:,} orang")
            st.write(f"• **Jumlah Kategori:** {n_kat:,} kategori")
            st.write(f"• **Jumlah Jawatan:** {n_jwt:,} jawatan")
            st.write(f"• **Jumlah Jejak Audit:** {n_aud:,} log")
            
            if st.button("⚡ Optimumkan Pangkalan Data (VACUUM)"):
                conn.execute("VACUUM")
                log_audit(user["nama_penuh"], "VACUUM DB", "Database dioptimumkan via Web.")
                st.success("Pangkalan data telah dioptimumkan!")
        
        with adm_t6:
            st.markdown("##### 🕌 Kemaskini Maklumat & Nama Rasmi Surau")
            c = conn.cursor()
            c.execute("SELECT nama_surau, alamat_surau FROM tetapan WHERE id = 1")
            row_tetapan = c.fetchone()
            curr_nama = row_tetapan[0] if row_tetapan else "Surau An Najdah"
            curr_alamat = row_tetapan[1] if (row_tetapan and row_tetapan[1]) else ""
            
            with st.form("form_tetapan_surau"):
                input_nama_surau = st.text_input("Nama Rasmi Surau:", value=curr_nama)
                input_alamat = st.text_area("Alamat Surau (Pilihan):", value=curr_alamat)
                
                t_b1, t_b2 = st.columns(2)
                if t_b1.form_submit_button("💾 Simpan Maklumat Surau", type="primary", use_container_width=True):
                    if input_nama_surau.strip():
                        c.execute("UPDATE tetapan SET nama_surau = ?, alamat_surau = ? WHERE id = 1", 
                                  (input_nama_surau.strip(), input_alamat.strip()))
                        conn.commit()
                        log_audit(user["nama_penuh"], "KEMASKINI TETAPAN", f"Nama surau ditukar kepada '{input_nama_surau.strip()}'")
                        st.success(f"Nama surau berjaya dikemaskini kepada '{input_nama_surau.strip()}'!")
                        st.rerun()
                    else:
                        st.error("Nama surau tidak boleh dibiarkan kosong!")
                if t_b2.form_submit_button("❌ Batal / Reset", use_container_width=True):
                    pass
                
        conn.close()

if st.session_state['logged_in']:
    main_app()
else:
    login_page()
