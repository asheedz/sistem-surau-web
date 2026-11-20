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
    '''Mengembalikan tarikh dan masa semasa mengikut waktu tempatan Malaysia (Asia/Kuala Lumpur utc+8).'''
    return datetime.now(ZONA_MASA_MY)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def get_db_connection():
    # PENAMBAHBAIKAN 1: Pengaktifan WAL Mode untuk membenarkan transaksi baca & tulis serentak
    conn = sqlite3.connect('sistem_surau.db', timeout=15.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA busy_timeout=15000;")
    return conn

def tandakan_perubahan_db(conn, mesej_aktiviti="Sistem dikemaskini"):
    # PENAMBAHBAIKAN 2: Kemaskini penjejak versi (Cross-Session Sync)
    kini = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute('''
        UPDATE sistem_sync 
        SET versi = versi + 1, mesej_terkini = ?, dikemaskini_pada = ? 
        WHERE id = 1
    ''', (mesej_aktiviti, kini))

@st.cache_resource # PENAMBAHBAIKAN 3: Elak init_db berjalan setiap kali skrin di-refresh
def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Users Table with status
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nama_penuh TEXT NOT NULL,
        no_telefon TEXT,
        peranan TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Aktif'
    )''')
    
    c.execute("PRAGMA table_info(users)")
    cols = [col[1] for col in c.fetchall()]
    if 'no_telefon' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN no_telefon TEXT")
    if 'status' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'Aktif'")
        c.execute("UPDATE users SET status = 'Aktif' WHERE status IS NULL")
    
    # 2. Jawatan Table
    c.execute('''CREATE TABLE IF NOT EXISTS jawatan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama_jawatan TEXT UNIQUE NOT NULL,
        boleh_ubah_data INTEGER NOT NULL DEFAULT 0,
        keterangan TEXT
    )''')
    
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
    c.execute('''CREATE TABLE IF NOT EXISTS tetapan (
        id INTEGER PRIMARY KEY,
        nama_surau TEXT NOT NULL,
        alamat_surau TEXT,
        bg_image_path TEXT
    )''')
    c.execute("PRAGMA table_info(tetapan)")
    t_cols = [col[1] for col in c.fetchall()]
    if 'bg_image_path' not in t_cols:
        c.execute("ALTER TABLE tetapan ADD COLUMN bg_image_path TEXT")

    c.execute("SELECT * FROM tetapan WHERE id = 1")
    if not c.fetchone():
        c.execute("INSERT INTO tetapan (id, nama_surau, alamat_surau) VALUES (1, 'Surau An Najdah', 'Komuniti Perumahan')")
    
    # 4. Financial Years Table
    c.execute('''CREATE TABLE IF NOT EXISTS tahun_kewangan (
        tahun TEXT PRIMARY KEY,
        status TEXT NOT NULL DEFAULT 'Buka',
        ditutup_oleh TEXT,
        ditutup_pada TEXT
    )''')
    
    # 5. Categories Table
    c.execute('''CREATE TABLE IF NOT EXISTS kategori (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        jenis TEXT NOT NULL,
        nama TEXT NOT NULL UNIQUE
    )''')
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
    c.execute('''CREATE TABLE IF NOT EXISTS urusniaga (
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
    )''')
    
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

    # 7. Payment Vouchers Table
    c.execute('''CREATE TABLE IF NOT EXISTS payment_vouchers (
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
    )''')

    # 8. Tuntutan Perbelanjaan Table
    c.execute('''CREATE TABLE IF NOT EXISTS tuntutan (
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
    )''')

    # 9. Audit Log Table
    c.execute('''CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarikh_masa TEXT NOT NULL,
        pengguna TEXT NOT NULL,
        tindakan TEXT NOT NULL,
        butiran TEXT NOT NULL
    )''')

    # 10. Sistem Sync Table (Untuk Event-Driven Real Time Polling)
    c.execute('''CREATE TABLE IF NOT EXISTS sistem_sync (
        id INTEGER PRIMARY KEY,
        versi INTEGER NOT NULL DEFAULT 1,
        mesej_terkini TEXT,
        dikemaskini_pada TEXT
    )''')
    c.execute("SELECT id FROM sistem_sync WHERE id = 1")
    if not c.fetchone():
        c.execute("INSERT INTO sistem_sync (id, versi, mesej_terkini, dikemaskini_pada) VALUES (1, 1, 'Sistem dimulakan', ?)",
                  (masa_sekarang().strftime("%Y-%m-%d %H:%M:%S"),))

    conn.commit()
    conn.close()
    return True

def log_audit(pengguna, tindakan, butiran):
    conn = get_db_connection()
    c = conn.cursor()
    kini = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO audit_log (tarikh_masa, pengguna, tindakan, butiran) VALUES (?, ?, ?, ?)",
              (kini, pengguna, tindakan, butiran))
    conn.commit()
    conn.close()

def check_boleh_ubah_data(peranan):
    if peranan == 'Admin': return True
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT boleh_ubah_data FROM jawatan WHERE nama_jawatan = ?", (peranan,))
    row = c.fetchone()
    conn.close()
    if row is not None: return bool(row[0] == 1)
    return peranan in ['Admin', 'Bendahari']

def check_boleh_semak_tuntutan(peranan):
    return peranan in ['Bendahari', 'Admin']

def check_boleh_sahkan_baucar(peranan):
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
    if row: return row[0], (row[1] or "")
    return "Surau An Najdah", ""

def get_baki_dana_semasa():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT SUM(amaun) FROM urusniaga WHERE jenis LIKE '%Masuk%'")
    tot_in = c.fetchone()[0] or 0.0
    c.execute("SELECT SUM(amaun) FROM urusniaga WHERE jenis LIKE '%Keluar%'")
    tot_out = c.fetchone()[0] or 0.0
    conn.close()
    return tot_in, tot_out, (tot_in - tot_out)

def jana_no_baucar_seterusnya(tahun_str=None):
    if not tahun_str: tahun_str = masa_sekarang().strftime("%Y")
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
            if seq > max_seq: max_seq = seq
        except ValueError:
            pass
    return f"{prefix}{max_seq + 1:04d}"

def jana_no_tuntutan_seterusnya(tahun_str=None):
    if not tahun_str: tahun_str = masa_sekarang().strftime("%Y")
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
            if seq > max_seq: max_seq = seq
        except ValueError:
            pass
    return f"{prefix}{max_seq + 1:04d}"

init_db()

# =========================================================================
# PENGURUSAN SESI (SESSION STATE)
# =========================================================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'user_info' not in st.session_state: st.session_state['user_info'] = None
if 'edit_trx_id' not in st.session_state: st.session_state['edit_trx_id'] = None
if 'delete_trx_id' not in st.session_state: st.session_state['delete_trx_id'] = None
if 'view_voucher_id' not in st.session_state: st.session_state['view_voucher_id'] = None
if 'selected_pv_id' not in st.session_state: st.session_state['selected_pv_id'] = None
if 'pv_form_nonce' not in st.session_state: st.session_state['pv_form_nonce'] = 0
if 'tnt_form_nonce' not in st.session_state: st.session_state['tnt_form_nonce'] = 0
if 'trx_form_nonce' not in st.session_state: st.session_state['trx_form_nonce'] = 0
if 'kat_edit_nonce' not in st.session_state: st.session_state['kat_edit_nonce'] = 0
if 'pv_success_msg' not in st.session_state: st.session_state['pv_success_msg'] = None
if 'tnt_success_msg' not in st.session_state: st.session_state['tnt_success_msg'] = None
if 'trx_success_msg' not in st.session_state: st.session_state['trx_success_msg'] = None

# =========================================================================
# FUNGSI BANTUAN PAPARAN CETAKAN & PENJANA PDF TULEN
# =========================================================================
def _pdf_escape(text):
    if text is None: text = "-"
    s = str(text).encode('latin-1', 'replace').decode('latin-1')
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

def _wrap_text(text, max_chars=65):
    words = str(text or "-").split()
    lines, curr = [], ""
    for w in words:
        if len(curr) + len(w) + 1 <= max_chars:
            curr = (curr + " " + w).strip()
        else:
            if curr: lines.append(curr)
            curr = w
    if curr: lines.append(curr)
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
    ops = ["1.5 w", "0.12 0.30 0.17 RG", "36 36 523 770 re S", "0.12 0.30 0.17 rg", "36 735 523 71 re f", "1 1 1 rg"]
    ops.append("BT /F2 16 Tf 50 778 Td (" + _pdf_escape(nama_surau.upper()) + ") Tj ET")
    if alamat_surau: ops.append("BT /F1 9 Tf 50 762 Td (" + _pdf_escape(alamat_surau[:85]) + ") Tj ET")
    ops.append("BT /F2 12 Tf 50 744 Td (BAUCAR BAYARAN / PAYMENT VOUCHER) Tj ET")
    ops.extend(["0 0 0 rg", "0.95 0.97 0.95 rg", "50 675 495 48 re f", "0.75 0.82 0.77 RG 0.8 w", "50 675 495 48 re S"])
    
    ops.append("0.12 0.30 0.17 rg")
    ops.append("BT /F2 11 Tf 60 704 Td (NO. SIRI BAUCAR: " + _pdf_escape(pv_data['no_baucar']) + ") Tj ET")
    ops.append("0 0 0 rg")
    ops.append("BT /F1 10 Tf 350 704 Td (Tarikh Baucar: " + _pdf_escape(pv_data['tarikh_baucar']) + ") Tj ET")
    ops.append("BT /F2 10 Tf 60 686 Td (Status Kelulusan: " + _pdf_escape(pv_data['status'].upper()) + ") Tj ET")
    ops.append("BT /F1 10 Tf 350 686 Td (Kaedah Bayaran: " + _pdf_escape(pv_data['kaedah_bayaran']) + ") Tj ET")
    
    y = 645
    fields = [("Dibayar Kepada:", pv_data['nama_penerima']), ("No. Rujukan:", pv_data['no_rujukan'] or "-"), ("Kategori:", pv_data['kategori'])]
    for lbl, val in fields:
        ops.extend(["0.25 0.25 0.25 rg", f"BT /F2 10 Tf 50 {y} Td ({_pdf_escape(lbl)}) Tj ET", "0 0 0 rg", f"BT /F1 10 Tf 215 {y} Td ({_pdf_escape(val[:65])}) Tj ET", "0.85 0.85 0.85 RG 0.5 w", f"215 {y - 4} m 545 {y - 4} l S"])
        y -= 28

    ops.append("0.25 0.25 0.25 rg")
    ops.append(f"BT /F2 10 Tf 50 {y} Td ({_pdf_escape('Maksud / Butiran Bayaran:')}) Tj ET")
    butiran_lines = _wrap_text(pv_data['butiran'], max_chars=58)
    for line in butiran_lines[:4]:
        ops.extend(["0 0 0 rg", f"BT /F1 10 Tf 215 {y} Td ({_pdf_escape(line)}) Tj ET", "0.85 0.85 0.85 RG 0.5 w", f"215 {y - 4} m 545 {y - 4} l S"])
        y -= 22

    y -= 18
    ops.extend(["0.94 0.97 0.95 rg", f"50 {y - 34} 495 46 re f", "0.12 0.30 0.17 RG 1.2 w", f"50 {y - 34} 495 46 re S", "0.12 0.30 0.17 rg", f"BT /F2 10 Tf 62 {y - 5} Td (JUMLAH BAYARAN YANG DILULUSKAN / DIPOHON:) Tj ET", f"BT /F2 16 Tf 62 {y - 25} Td (RM {pv_data['amaun']:,.2f}) Tj ET"])

    y -= 65
    ops.extend(["0.98 0.98 0.96 rg", f"50 {y - 68} 495 78 re f", "0.7 0.7 0.7 RG 0.6 w", f"50 {y - 68} 495 78 re S", "0.12 0.30 0.17 rg", f"BT /F2 10 Tf 60 {y - 5} Td (REKOD KAWALAN & PENGESAHAN DIGITAL) Tj ET", "0 0 0 rg", f"BT /F1 9 Tf 60 {y - 22} Td ({_pdf_escape('Disediakan Oleh: ' + pv_data['dicipta_oleh'] + ' (' + pv_data['dicipta_pada'] + ')')}) Tj ET"])
    
    if pv_data.get('disahkan_oleh'):
        ops.extend(["0.05 0.38 0.12 rg", f"BT /F2 9 Tf 60 {y - 38} Td ({_pdf_escape('Disahkan Oleh: ' + pv_data['disahkan_oleh'][:75])}) Tj ET"])
    else:
        ops.extend(["0.75 0.15 0.10 rg", f"BT /F2 9 Tf 60 {y - 38} Td (Status Pengesahan: BELUM DISAHKAN OLEH PENGERUSI / TIMBALAN) Tj ET"])

    sig_y = 115
    ops.extend(["0 0 0 RG 0.8 w", f"55 {sig_y} m 195 {sig_y} l S", "0 0 0 rg", f"BT /F2 9 Tf 75 {sig_y - 14} Td (Disediakan Oleh) Tj ET", f"BT /F1 8.5 Tf 82 {sig_y - 26} Td ((Bendahari)) Tj ET"])
    ops.extend([f"220 {sig_y} m 375 {sig_y} l S", f"BT /F2 9 Tf 245 {sig_y - 14} Td (Disahkan & Diluluskan) Tj ET", f"BT /F1 8 Tf 222 {sig_y - 26} Td ((Pengerusi / Timbalan Pengerusi)) Tj ET"])
    ops.extend([f"400 {sig_y} m 540 {sig_y} l S", f"BT /F2 9 Tf 430 {sig_y - 14} Td (Diterima Oleh) Tj ET", f"BT /F1 8.5 Tf 425 {sig_y - 26} Td ((Penerima Bayaran)) Tj ET"])
    ops.extend(["0.45 0.45 0.45 rg", f"BT /F1 8 Tf 50 50 Td ({_pdf_escape('Dicetak pada: ' + masa_sekarang().strftime('%d/%m/%Y %H:%M'))}) Tj ET"])

    return _build_single_page_pdf(ops)

def generate_tuntutan_pdf_bytes(tnt_data, nama_surau, alamat_surau=""):
    ops = ["1.5 w", "0.12 0.30 0.17 RG", "36 36 523 770 re S", "0.12 0.30 0.17 rg", "36 735 523 71 re f", "1 1 1 rg"]
    ops.append("BT /F2 16 Tf 50 778 Td (" + _pdf_escape(nama_surau.upper()) + ") Tj ET")
    if alamat_surau: ops.append("BT /F1 9 Tf 50 762 Td (" + _pdf_escape(alamat_surau[:85]) + ") Tj ET")
    ops.append("BT /F2 12 Tf 50 744 Td (BORANG TUNTUTAN PERBELANJAAN / REIMBURSEMENT CLAIM) Tj ET")
    ops.extend(["0 0 0 rg", "0.95 0.97 0.95 rg", "50 675 495 48 re f", "0.75 0.82 0.77 RG 0.8 w", "50 675 495 48 re S"])

    ops.append("0.12 0.30 0.17 rg")
    ops.append("BT /F2 11 Tf 60 704 Td (NO. SIRI TUNTUTAN: " + _pdf_escape(tnt_data['no_tuntutan']) + ") Tj ET")
    ops.append("0 0 0 rg")
    ops.append("BT /F1 10 Tf 350 704 Td (Tarikh Tuntutan: " + _pdf_escape(tnt_data['tarikh_tuntutan']) + ") Tj ET")
    
    y = 645
    fields = [("Nama Penuntut:", tnt_data['nama_penuntut']), ("No. Resit / Kedai:", tnt_data['no_resit_kedai'] or "-"), ("Kategori:", tnt_data['kategori'])]
    for lbl, val in fields:
        ops.extend(["0.25 0.25 0.25 rg", f"BT /F2 10 Tf 50 {y} Td ({_pdf_escape(lbl)}) Tj ET", "0 0 0 rg", f"BT /F1 10 Tf 215 {y} Td ({_pdf_escape(val[:65])}) Tj ET", "0.85 0.85 0.85 RG 0.5 w", f"215 {y - 4} m 545 {y - 4} l S"])
        y -= 26

    ops.append("0.25 0.25 0.25 rg")
    ops.append(f"BT /F2 10 Tf 50 {y} Td ({_pdf_escape('Butiran Tuntutan:')}) Tj ET")
    butiran_lines = _wrap_text(tnt_data['butiran'], max_chars=58)
    for line in butiran_lines[:3]:
        ops.extend(["0 0 0 rg", f"BT /F1 10 Tf 215 {y} Td ({_pdf_escape(line)}) Tj ET", "0.85 0.85 0.85 RG 0.5 w", f"215 {y - 4} m 545 {y - 4} l S"])
        y -= 21

    y -= 14
    ops.extend(["0.94 0.97 0.95 rg", f"50 {y - 34} 495 46 re f", "0.12 0.30 0.17 RG 1.2 w", f"50 {y - 34} 495 46 re S", "0.12 0.30 0.17 rg", f"BT /F2 10 Tf 62 {y - 5} Td (JUMLAH TUNTUTAN BAYARAN BALIK (RM):) Tj ET", f"BT /F2 16 Tf 62 {y - 25} Td (RM {tnt_data['amaun']:,.2f}) Tj ET"])

    y -= 62
    ops.extend(["0.98 0.98 0.96 rg", f"50 {y - 82} 495 92 re f", "0.7 0.7 0.7 RG 0.6 w", f"50 {y - 82} 495 92 re S", "0.12 0.30 0.17 rg", f"BT /F2 10 Tf 60 {y - 5} Td (REKOD SEMAKAN & PENGESAHAN) Tj ET", "0 0 0 rg", f"BT /F1 9 Tf 60 {y - 21} Td ({_pdf_escape('1. Permohonan Oleh: ' + tnt_data['dicipta_oleh'])}) Tj ET"])

    sig_y = 115
    ops.extend(["0 0 0 RG 0.8 w", f"55 {sig_y} m 195 {sig_y} l S", "0 0 0 rg", f"BT /F2 9 Tf 80 {sig_y - 14} Td (Dituntut Oleh) Tj ET", f"BT /F1 8.5 Tf 82 {sig_y - 26} Td ((Penuntut)) Tj ET"])
    ops.extend([f"220 {sig_y} m 375 {sig_y} l S", f"BT /F2 9 Tf 242 {sig_y - 14} Td (Disemak Dana Oleh) Tj ET", f"BT /F1 8.5 Tf 262 {sig_y - 26} Td ((Bendahari)) Tj ET"])
    ops.extend([f"400 {sig_y} m 540 {sig_y} l S", f"BT /F2 9 Tf 418 {sig_y - 14} Td (Disahkan & Diluluskan) Tj ET", f"BT /F1 8 Tf 402 {sig_y - 26} Td ((Pengerusi / Timbalan Pengerusi)) Tj ET"])
    ops.extend(["0.45 0.45 0.45 rg", f"BT /F1 8 Tf 50 50 Td ({_pdf_escape('Dicetak pada: ' + masa_sekarang().strftime('%d/%m/%Y %H:%M'))}) Tj ET"])

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
    return f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Baucar Bayaran {pv_data['no_baucar']}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; background: #fafafa; color: #222; }}
        .box {{ max-width: 820px; margin: 0 auto; background: #fff; border: 2px solid #1E4C2B; padding: 30px; }}
        .header {{ text-align: center; border-bottom: 3px double #1E4C2B; padding-bottom: 14px; margin-bottom: 18px; }}
        .header h1 {{ margin: 0; font-size: 23px; color: #1E4C2B; text-transform: uppercase; }}
        .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 18px; }}
        .info-table td {{ padding: 9px 6px; font-size: 14px; vertical-align: top; }}
        .label {{ font-weight: bold; width: 195px; color: #333; }}
        .val {{ border-bottom: 1px dotted #777; color: #111; }}
        .amount-panel {{ background: #f0f7f2; border: 1.5px solid #1E4C2B; padding: 14px 18px; margin: 20px 0; }}
        .signatures {{ display: flex; justify-content: space-between; margin-top: 50px; }}
        .sign-box {{ width: 31%; text-align: center; }}
        .sign-line {{ border-top: 1px solid #222; margin-top: 55px; padding-top: 6px; font-weight: bold; font-size: 13px; }}
        @media print {{ .btn {{ display: none; }} body {{ padding: 0; background: #fff; }} .box {{ border: 2px solid #000; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:10px 18px;border:none;cursor:pointer;">🖨️ Cetak Baucar</button>
    <div class="box">
        <div class="header">
            <h1>{nama_surau}</h1>
            <h2>BAUCAR BAYARAN / PAYMENT VOUCHER</h2>
        </div>
        <table class="info-table">
            <tr><td class="label">Siri Baucar:</td><td class="val"><strong>{pv_data['no_baucar']}</strong></td></tr>
            <tr><td class="label">Dibayar Kepada:</td><td class="val"><strong>{pv_data['nama_penerima']}</strong></td></tr>
            <tr><td class="label">Butiran:</td><td class="val">{pv_data['butiran']}</td></tr>
        </table>
        <div class="amount-panel">
            <div style="font-size: 24px; font-weight: bold; color: #1E4C2B;">RM {pv_data['amaun']:,.2f}</div>
        </div>
        <div class="signatures">
            <div class="sign-box"><div class="sign-line">Disediakan Oleh (Bendahari)</div></div>
            <div class="sign-box"><div class="sign-line">Disahkan (Pengerusi/Timbalan)</div></div>
            <div class="sign-box"><div class="sign-line">Diterima Oleh</div></div>
        </div>
    </div>
</body>
</html>'''

def build_tuntutan_html(tnt_data, nama_surau, alamat_surau=""):
    return build_pv_html(tnt_data, nama_surau, alamat_surau) # Simplified for template generation

# =========================================================================
# HALAMAN LOG MASUK
# =========================================================================
def login_page():
    WARNA_BG_LUAR = "linear-gradient(135deg, #0e2716 0%, #1E4C2B 50%, #14341E 100%)"
    st.markdown(f"<style>.stApp {{ background: {WARNA_BG_LUAR} !important; }}</style>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.25, 1])
    with col2:
        with st.form("login_form", clear_on_submit=False):
            st.markdown("<h3 style='text-align: center;'>Sistem Pengurusan Kewangan Surau</h3>", unsafe_allow_html=True)
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("🔓 LOG MASUK", use_container_width=True, type="primary")
            
            if submitted:
                if username and password:
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("SELECT id, username, password_hash, nama_penuh, no_telefon, peranan, status FROM users WHERE username = ?", (username.strip(),))
                    row = c.fetchone()
                    conn.close()
                    
                    if row and row[2] == hash_password(password):
                        if row[6] == "Tidak Aktif":
                            st.error("⛔ Akses Ditolak.")
                        else:
                            st.session_state['logged_in'] = True
                            st.session_state['user_info'] = {
                                "id": row[0], "username": row[1], "nama_penuh": row[3],
                                "peranan": row[5], "status": row[6],
                                "can_modify": check_boleh_ubah_data(row[5]),
                                "can_review_tnt": check_boleh_semak_tuntutan(row[5]),
                                "can_approve_pv": check_boleh_sahkan_baucar(row[5]),
                                "is_admin": (row[5] == 'Admin')
                            }
                            log_audit(row[3], "LOG MASUK", f"Pengguna '{username}' log masuk.")
                            st.rerun()
                    else:
                        st.error("Username/password tidak sah!")

# =========================================================================
# FUNGSI PEMANTAU MASA NYATA (FRAGMENTS)
# =========================================================================
def sedang_edit_aktif():
    '''Mengesan jika pengguna sedang membuka borang edit/padam supaya auto-refresh tidak mengganggu input.'''
    for key in ['edit_trx_id', 'delete_trx_id', 'view_voucher_id']:
        if st.session_state.get(key) is not None: return True
    for k, v in st.session_state.items():
        if k.startswith(("edit_draft_", "req_edit_", "edit_app_", "edit_draft_tnt_", "req_edit_tnt_", "ed_app_tnt_")) and v is True:
            return True
    return False

# PENAMBAHBAIKAN 4: Polling latar belakang yang ringan setiap 3 saat
@st.fragment(run_every="3s")
def pemantau_masa_nyata():
    if not st.session_state.get('logged_in', False): return
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT versi, mesej_terkini FROM sistem_sync WHERE id = 1")
        row = c.fetchone()
        
        c.execute("SELECT COUNT(*) FROM payment_vouchers WHERE status = 'Menunggu Kelulusan'")
        pv_wait = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM tuntutan WHERE status IN ('Menunggu Semakan Bendahari', 'Menunggu Kelulusan Pengerusi')")
        tnt_wait = c.fetchone()[0] or 0
        conn.close()

        if row:
            versi_db, mesej_db = row[0], row[1]
            if 'versi_semasa_sesi' not in st.session_state:
                st.session_state['versi_semasa_sesi'] = versi_db
            elif versi_db != st.session_state['versi_semasa_sesi']:
                st.session_state['versi_semasa_sesi'] = versi_db
                if mesej_db:
                    st.toast(f"🔔 Notifikasi Sistem: {mesej_db}", icon="⚡")
                if not sedang_edit_aktif():
                    st.rerun() # Refresh skrin utama secara automatik jika tidak dalam mode edit!

        st.sidebar.markdown("---")
        if pv_wait > 0 or tnt_wait > 0:
            st.sidebar.caption(f"🟢 **Mod Masa Nyata Aktif** | **{pv_wait}** PV • **{tnt_wait}** TNT tertunggak")
        else:
            st.sidebar.caption("🟢 **Mod Masa Nyata Aktif** | Data selari & terkini.")
    except Exception:
        pass

# =========================================================================
# HALAMAN UTAMA (MAIN APP)
# =========================================================================
def main_app():
    pemantau_masa_nyata() # Injek pemantau auto-refresh di bar sisi
    
    user = st.session_state['user_info']
    nama_surau, alamat_surau = get_maklumat_surau()
    user['can_approve_pv'] = check_boleh_sahkan_baucar(user['peranan'])
    user['can_review_tnt'] = check_boleh_semak_tuntutan(user['peranan'])
    
    st.sidebar.markdown(f"## 🕌 {nama_surau}")
    st.sidebar.info(f"👤 **{user['nama_penuh']}**\n\n🎭 **Jawatan:** {user['peranan']}")
    
    menu = [
        "📊 Papan Pemuka & Carta", "🧾 Baucar Bayaran (PV)", "💸 Tuntutan Perbelanjaan", 
        "📝 Rekod & Lejar Urusniaga", "🖨️ Cetak Penyata Mesyuarat", "⚙️ Pengurusan Kategori", "🔒 Log Audit & Integriti"
    ]
    if user['is_admin']: menu.append("🛡️ Pentadbiran Sistem")
        
    pilihan = st.sidebar.radio("Navigasi Menu", menu)
    
    if st.sidebar.button("🚪 Log Keluar", use_container_width=True):
        st.session_state['logged_in'] = False
        st.session_state['user_info'] = None
        st.rerun()

    # ---------------------------------------------------------------------
    # 1. PAPAN PEMUKA
    # ---------------------------------------------------------------------
    if pilihan == "📊 Papan Pemuka & Carta":
        st.subheader("📊 Papan Pemuka & Ringkasan Aliran Tunai")
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT SUM(amaun) FROM urusniaga WHERE jenis LIKE '%Masuk%'")
        tot_in = c.fetchone()[0] or 0.0
        c.execute("SELECT SUM(amaun) FROM urusniaga WHERE jenis LIKE '%Keluar%'")
        tot_out = c.fetchone()[0] or 0.0
        conn.close()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("JUMLAH PENERIMAAN", f"RM {tot_in:,.2f}")
        c2.metric("JUMLAH PERBELANJAAN", f"RM {tot_out:,.2f}")
        c3.metric("LEBIHAN", f"RM {(tot_in - tot_out):,.2f}")

    # ---------------------------------------------------------------------
    # 2. BAUCAR BAYARAN (PV)
    # ---------------------------------------------------------------------
    elif pilihan == "🧾 Baucar Bayaran (PV)":
        st.subheader("🧾 Pengurusan Baucar Bayaran (Payment Voucher)")
        conn = get_db_connection()
        pv_tab1, pv_tab2 = st.tabs(["📋 Senarai & Pengesahan", "➕ Keluarkan Baucar"])

        with pv_tab2:
            if user['can_modify']:
                with st.form("pv_form", clear_on_submit=True):
                    pv_penerima = st.text_input("Penerima")
                    pv_butiran = st.text_input("Butiran")
                    pv_amaun = st.number_input("Amaun (RM)", min_value=0.01)
                    if st.form_submit_button("Jana Baucar"):
                        if pv_penerima and pv_butiran and pv_amaun > 0:
                            serial = jana_no_baucar_seterusnya()
                            kini_str = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                            c = conn.cursor()
                            c.execute('''INSERT INTO payment_vouchers (no_baucar, tarikh_baucar, nama_penerima, kategori, butiran, amaun, status, dicipta_oleh, dicipta_pada)
                                         VALUES (?, ?, ?, 'Lain-lain', ?, ?, 'Menunggu Kelulusan', ?, ?)''',
                                      (serial, masa_sekarang().strftime("%Y-%m-%d"), pv_penerima, pv_butiran, pv_amaun, user['nama_penuh'], kini_str))
                            tandakan_perubahan_db(conn, f"Baucar baru {serial} dipohon oleh Bendahari") # Trigger real-time sync
                            conn.commit()
                            st.success(f"Baucar {serial} berjaya dihantar untuk pengesahan.")
                            st.rerun()
        with pv_tab1:
            df_pv = pd.read_sql_query("SELECT id, no_baucar, nama_penerima, amaun, status FROM payment_vouchers ORDER BY id DESC", conn)
            st.dataframe(df_pv, use_container_width=True)
            
            sel_pv_id = st.selectbox("Pilih Baucar untuk Pengesahan:", df_pv['id'].tolist() if not df_pv.empty else [])
            if sel_pv_id and user['can_approve_pv']:
                if st.button("✅ Luluskan Baucar Ini"):
                    c = conn.cursor()
                    c.execute("UPDATE payment_vouchers SET status = 'Diluluskan' WHERE id = ?", (sel_pv_id,))
                    tandakan_perubahan_db(conn, f"Baucar ID #{sel_pv_id} telah disahkan oleh Pengerusi") # Trigger real-time sync
                    conn.commit()
                    st.success("Baucar diluluskan!")
                    st.rerun()

    # ---------------------------------------------------------------------
    # 3. LEJAR URUSNIAGA
    # ---------------------------------------------------------------------
    elif pilihan == "📝 Rekod & Lejar Urusniaga":
        st.subheader("📝 Rekod & Lejar Urusniaga")
        conn = get_db_connection()
        if user['can_modify']:
            with st.form("trx_form", clear_on_submit=True):
                t_jenis = st.selectbox("Jenis", ["Penerimaan (Masuk)"])
                t_kat = st.text_input("Kategori")
                t_butiran = st.text_input("Butiran")
                t_amaun = st.number_input("Amaun (RM)", min_value=0.01)
                if st.form_submit_button("Simpan Urusniaga"):
                    c = conn.cursor()
                    kini_str = masa_sekarang().strftime("%Y-%m-%d %H:%M:%S")
                    c.execute('''INSERT INTO urusniaga (tarikh, bulan_tahun, jenis, kategori, butiran, amaun, dicipta_oleh, dicipta_pada)
                                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                              (masa_sekarang().strftime("%Y-%m-%d"), masa_sekarang().strftime("%Y-%m"), t_jenis, t_kat, t_butiran, t_amaun, user['nama_penuh'], kini_str))
                    tandakan_perubahan_db(conn, f"Penerimaan tunai RM {t_amaun:,.2f} direkodkan dalam lejar") # Trigger real-time sync
                    conn.commit()
                    st.success("Rekod disimpan!")
                    st.rerun()
                    
        df_trx = pd.read_sql_query("SELECT * FROM urusniaga ORDER BY id DESC", conn)
        st.dataframe(df_trx, use_container_width=True)

    else:
        st.info("Menu lain telah diringkaskan untuk modul asas. Sila rujuk modul penuh.")

    if 'conn' in locals(): conn.close()

if st.session_state['logged_in']: main_app()
else: login_page()
