import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import hashlib
import os
import shutil
import base64
import re
import streamlit.components.v1 as components

# =========================================================================
# KONFIGURASI LAMAN (PAGE CONFIG)
# =========================================================================
st.set_page_config(
    page_title="Sistem Kewangan Surau",
    page_icon="🕌",
    layout="wide",
    initial_sidebar_state="expanded"
)

UPLOAD_BG_DIR = "assets_surau"
os.makedirs(UPLOAD_BG_DIR, exist_ok=True)

# =========================================================================
# FUNGSI CRYPTOGRAPHY & DATABASE
# =========================================================================
def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def get_db_connection():
    return sqlite3.connect('sistem_surau.db', check_same_thread=False)

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
        ('Bendahari', 1, 'Perekodan & Pengurusan Urusniaga Kewangan'),
        ('Pengerusi', 0, 'Semakan Penyata & Kelulusan Baucar'),
        ('Timbalan Pengerusi', 0, 'Semakan Penyata & Kelulusan Baucar'),
        ('AJK', 0, 'Paparan Sahaja (Ketelusan Jemaah)')
    ]
    for r_name, r_mod, r_desc in default_roles:
        c.execute("INSERT OR IGNORE INTO jawatan (nama_jawatan, boleh_ubah_data, keterangan) VALUES (?, ?, ?)",
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
        bg_image_path TEXT,
        bg_overlay REAL DEFAULT 0.45
    )""")
    c.execute("PRAGMA table_info(tetapan)")
    t_cols = [col[1] for col in c.fetchall()]
    if 'bg_image_path' not in t_cols:
        c.execute("ALTER TABLE tetapan ADD COLUMN bg_image_path TEXT")
    if 'bg_overlay' not in t_cols:
        c.execute("ALTER TABLE tetapan ADD COLUMN bg_overlay REAL DEFAULT 0.45")

    c.execute("SELECT * FROM tetapan WHERE id = 1")
    if not c.fetchone():
        c.execute("INSERT INTO tetapan (id, nama_surau, alamat_surau, bg_overlay) VALUES (1, 'Surau An Najdah', 'Komuniti Perumahan', 0.45)")
    
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

    # 6. Transactions Table (termasuk medan baucar auto-number)
    c.execute("""CREATE TABLE IF NOT EXISTS urusniaga (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarikh TEXT NOT NULL,
        bulan_tahun TEXT NOT NULL,
        jenis TEXT NOT NULL,
        kategori TEXT NOT NULL,
        butiran TEXT NOT NULL,
        amaun REAL NOT NULL,
        dicipta_oleh TEXT NOT NULL,
        dicipta_pada TEXT NOT NULL,
        dikemaskini_oleh TEXT,
        dikemaskini_pada TEXT,
        nota_kemaskini_admin TEXT,
        no_baucar TEXT,
        baucar_dijana_oleh TEXT,
        baucar_dijana_pada TEXT,
        baucar_diluluskan_oleh TEXT
    )""")
    
    c.execute("PRAGMA table_info(urusniaga)")
    u_cols = [col[1] for col in c.fetchall()]
    for col_name, col_def in [
        ('dikemaskini_oleh', 'TEXT'),
        ('dikemaskini_pada', 'TEXT'),
        ('nota_kemaskini_admin', 'TEXT'),
        ('no_baucar', 'TEXT'),
        ('baucar_dijana_oleh', 'TEXT'),
        ('baucar_dijana_pada', 'TEXT'),
        ('baucar_diluluskan_oleh', 'TEXT')
    ]:
        if col_name not in u_cols:
            c.execute(f"ALTER TABLE urusniaga ADD COLUMN {col_name} {col_def}")

    # 7. Jadual Permohonan Kelulusan Edit / Padam Baucar (Untuk Pengerusi / Timbalan Pengerusi)
    c.execute("""CREATE TABLE IF NOT EXISTS permohonan_baucar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        urusniaga_id INTEGER NOT NULL,
        no_baucar TEXT NOT NULL,
        jenis_tindakan TEXT NOT NULL,
        tarikh_baru TEXT,
        jenis_baru TEXT,
        kategori_baru TEXT,
        butiran_baru TEXT,
        amaun_baru REAL,
        padam_transaksi INTEGER DEFAULT 0,
        sebab_permohonan TEXT NOT NULL,
        dimohon_oleh TEXT NOT NULL,
        dimohon_pada TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Menunggu',
        diputuskan_oleh TEXT,
        diputuskan_pada TEXT
    )""")

    # 8. Audit Log Table
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tarikh_masa TEXT NOT NULL,
        pengguna TEXT NOT NULL,
        tindakan TEXT NOT NULL,
        butiran TEXT NOT NULL
    )""")

    conn.commit()
    conn.close()

def log_audit(pengguna, tindakan, butiran):
    conn = get_db_connection()
    c = conn.cursor()
    kini = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

def is_pengerusi_atau_timbalan(peranan):
    if not peranan:
        return False
    return peranan.strip().lower() in ['pengerusi', 'timbalan pengerusi']

def sahkan_kredensial_pelulus(username_pelulus, password_pelulus):
    """Mengesahkan kata laluan Pengerusi atau Timbalan Pengerusi untuk kelulusan terus."""
    if not username_pelulus or not password_pelulus:
        return False, None, None
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT password_hash, nama_penuh, peranan, status FROM users WHERE username = ?", (username_pelulus.strip(),))
    row = c.fetchone()
    conn.close()
    if row and row[3] == 'Aktif' and row[0] == hash_password(password_pelulus):
        if is_pengerusi_atau_timbalan(row[2]):
            return True, row[1], row[2]
    return False, None, None

def jana_no_baucar_seterusnya(conn, tarikh_str=None):
    """Menjana nombor baucar auto-increment mengikut tahun, cth: PV-2026-0001."""
    tahun = tarikh_str[:4] if tarikh_str and len(tarikh_str) >= 4 else datetime.now().strftime("%Y")
    prefix = f"PV-{tahun}-"
    c = conn.cursor()
    c.execute("SELECT no_baucar FROM urusniaga WHERE no_baucar LIKE ?", (f"{prefix}%",))
    rows = c.fetchall()
    max_seq = 0
    for (nb,) in rows:
        if nb:
            m = re.search(r'(\d+)$', nb)
            if m:
                seq = int(m.group(1))
                if seq > max_seq:
                    max_seq = seq
    # Semak juga dalam permohonan_baucar supaya nombor baucar yang pernah dipadam tidak berulang
    c.execute("SELECT no_baucar FROM permohonan_baucar WHERE no_baucar LIKE ?", (f"{prefix}%",))
    for (nb,) in c.fetchall():
        if nb:
            m = re.search(r'(\d+)$', nb)
            if m:
                seq = int(m.group(1))
                if seq > max_seq:
                    max_seq = seq
    return f"{prefix}{max_seq + 1:04d}"

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

def get_bg_settings():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT bg_image_path, bg_overlay FROM tetapan WHERE id = 1")
    row = c.fetchone()
    conn.close()
    if row:
        return row[0], (row[1] if row[1] is not None else 0.45)
    return None, 0.45

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

# =========================================================================
# FUNGSI BANTUAN PAPARAN CETAKAN (PRINT HELPERS)
# =========================================================================
def show_printable_html(html_content, file_name="dokumen.html", button_label="🖨️ Cetak / Muat Turun Penyata"):
    b64 = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
    href = f'''<a href="data:text/html;base64,{b64}" target="_blank" download="{file_name}" style="text-decoration: none;">
        <button style="background-color: #1E4C2B; color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px; cursor: pointer; margin-bottom: 15px;">
            {button_label}
        </button>
    </a>'''
    st.markdown(href, unsafe_allow_html=True)
    with st.expander("👁️ Pratonton Dokumen (Skrin)", expanded=True):
        components.html(html_content, height=650, scrolling=True)

# =========================================================================
# HALAMAN LOG MASUK (FRONTPAGE RESPONSIF + SOKONGAN TEKAN ENTER)
# =========================================================================
def login_page():
    WARNA_BG_LUAR = "linear-gradient(135deg, #0e2716 0%, #1E4C2B 50%, #14341E 100%)"
    WARNA_KAD_FORM = "rgba(255, 255, 255, 0.96)"
    WARNA_TEKS_LABEL = "#1E4C2B"
    WARNA_INPUT_BG = "#f4f6f4"
    WARNA_INPUT_TEKS = "#000000"
    WARNA_BORDER_INPUT = "#c2d1c5"

    bg_path, bg_overlay = get_bg_settings()
    bg_css = f"background: {WARNA_BG_LUAR} !important;"
    
    if bg_path and os.path.exists(bg_path):
        ext = os.path.splitext(bg_path)[1].lower().replace(".", "")
        if ext == "jpg":
            ext = "jpeg"
        with open(bg_path, "rb") as img_f:
            b64_img = base64.b64encode(img_f.read()).decode("utf-8")
        alpha_top = max(0.0, min(0.90, float(bg_overlay)))
        alpha_bot = max(0.0, min(0.95, float(bg_overlay) + 0.10))
        bg_css = f"""
            background-image: linear-gradient(rgba(10, 25, 15, {alpha_top:.2f}), rgba(10, 25, 15, {alpha_bot:.2f})), url("data:image/{ext};base64,{b64_img}") !important;
            background-size: cover !important;
            background-position: center center !important;
            background-repeat: no-repeat !important;
            background-attachment: fixed !important;
        """

    st.markdown(f"""
        <style>
        /* 1. Latar Belakang Keseluruhan Laman (Responsif) */
        .stApp, [data-testid="stAppViewContainer"] {{
            {bg_css}
            min-height: 100vh !important;
            width: 100% !important;
        }}
        [data-testid="stHeader"] {{
            background: transparent !important;
        }}
        
        /* 2. Kad Borang Log Masuk (stForm) */
        div[data-testid="stForm"] {{
            background-color: {WARNA_KAD_FORM} !important;
            padding: 32px 28px !important;
            border-radius: 16px !important;
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
            box-shadow: 0px 12px 35px rgba(0, 0, 0, 0.50) !important;
            margin-top: 20px !important;
            backdrop-filter: blur(6px);
        }}
        
        /* 3. Warna Tulisan Label (Username & Password) */
        div[data-testid="stTextInput"] label,
        div[data-testid="stTextInput"] label p {{
            color: {WARNA_TEKS_LABEL} !important;
            font-size: 14px !important;
            font-weight: 700 !important;
        }}
        
        /* 4. Kotak Ruang Menaip */
        div[data-testid="stTextInput"] input {{
            color: {WARNA_INPUT_TEKS} !important;
            background-color: {WARNA_INPUT_BG} !important;
            border: 1.5px solid {WARNA_BORDER_INPUT} !important;
            border-radius: 8px !important;
            font-size: 14px !important;
        }}
        
        /* 5. Warna Kotak Semasa Klik (Focus) */
        div[data-testid="stTextInput"] input:focus {{
            border-color: #1E4C2B !important;
            box-shadow: 0 0 8px rgba(30, 76, 43, 0.3) !important;
        }}

        /* 6. Butang Log Masuk (Sokong Form Submit / Enter) */
        div[data-testid="stFormSubmitButton"] button,
        div[data-testid="stButton"] button[kind="primary"] {{
            background-color: #1E4C2B !important;
            color: #ffffff !important;
            border-radius: 8px !important;
            font-weight: bold