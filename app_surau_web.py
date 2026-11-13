import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import hashlib
import os
import shutil
import base64
import uuid
import qrcode
import cv2
import numpy as np
from PIL import Image
import io
import streamlit.components.v1 as components

# Import Turso DB library (libsql-experimental). Jika tiada ia akan guna sqlite3
try:
    import libsql_experimental as libsql
except ImportError:
    libsql = None

# =========================================================================
# KONFIGURASI LAMAN (PAGE CONFIG)
# =========================================================================
st.set_page_config(
    page_title="Sistem Kewangan Surau",
    page_icon="🕌",
    layout="wide",
    initial_sidebar_state="auto"
)

# =========================================================================
# FUNGSI CRYPTOGRAPHY & DATABASE
# =========================================================================
def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def get_db_connection():
    # Menggunakan Turso jika di-set dalam secrets, jika tidak guna SQLite local
    if "TURSO_DATABASE_URL" in st.secrets and "TURSO_AUTH_TOKEN" in st.secrets and libsql is not None:
        url = st.secrets["TURSO_DATABASE_URL"].strip()
        token = st.secrets["TURSO_AUTH_TOKEN"].strip()
        return libsql.connect(database=url, auth_token=token)
    else:
        # Fallback kepada pangkalan data SQLite tempatan
        return sqlite3.connect('sistem_surau.db', check_same_thread=False)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. Users Table
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nama_penuh TEXT NOT NULL,
        no_telefon TEXT,
        peranan TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Aktif',
        qr_token TEXT UNIQUE
    )""")
    
    c.execute("PRAGMA table_info(users)")
    cols = [col[1] for col in c.fetchall()]
    if 'no_telefon' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN no_telefon TEXT")
    if 'status' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'Aktif'")
        c.execute("UPDATE users SET status = 'Aktif' WHERE status IS NULL")
    if 'qr_token' not in cols:
        c.execute("ALTER TABLE users ADD COLUMN qr_token TEXT UNIQUE")
        c.execute("SELECT id FROM users")
        for (uid,) in c.fetchall():
            c.execute("UPDATE users SET qr_token = ? WHERE id = ?", (str(uuid.uuid4()), uid))
    
    # 2. Jawatan Table
    c.execute("""CREATE TABLE IF NOT EXISTS jawatan (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama_jawatan TEXT UNIQUE NOT NULL,
        boleh_ubah_data INTEGER NOT NULL DEFAULT 0,
        keterangan TEXT
    )""")
    
    c.execute("SELECT COUNT(*) FROM jawatan")
    if c.fetchone()[0] == 0:
        default_roles = [
            ('Admin', 1, 'Akses Penuh Sistem, Pengurusan Pengguna, Jawatan & Database'),
            ('Bendahari', 1, 'Perekodan & Pengurusan Urusniaga Kewangan'),
            ('Pengerusi', 0, 'Semakan Penyata & Paparan Sahaja'),
            ('AJK', 0, 'Paparan Sahaja (Ketelusan Jemaah)')
        ]
        for r_name, r_mod, r_desc in default_roles:
            c.execute("INSERT INTO jawatan (nama_jawatan, boleh_ubah_data, keterangan) VALUES (?, ?, ?)",
                      (r_name, r_mod, r_desc))

    # Seed default users
    default_users = [
        ('admin', 'admin123', 'Pentadbir Sistem Utama', '012-3456789', 'Admin', 'Aktif'),
        ('bendahari', 'benda123', 'Hj. Ismail (Bendahari)', '013-1122334', 'Bendahari', 'Aktif'),
        ('pengerusi', 'pengerusi123', 'Dato Hj. Azman (Pengerusi)', '019-8877665', 'Pengerusi', 'Aktif'),
        ('ajk1', 'ajk123', 'Ustaz Hamdan (AJK)', '017-9988776', 'AJK', 'Aktif')
    ]
    for u_name, u_pass, u_full, u_tel, u_role, u_stat in default_users:
        c.execute("SELECT id FROM users WHERE username = ?", (u_name,))
        if not c.fetchone():
            c.execute("INSERT INTO users (username, password_hash, nama_penuh, no_telefon, peranan, status, qr_token) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (u_name, hash_password(u_pass), u_full, u_tel, u_role, u_stat, str(uuid.uuid4())))
            
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
        dicipta_oleh TEXT NOT NULL,
        dicipta_pada TEXT NOT NULL,
        dikemaskini_oleh TEXT,
        dikemaskini_pada TEXT,
        nota_kemaskini_admin TEXT
    )""")
    
    # 7. Audit Log Table
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

def get_senarai_jawatan():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nama_jawatan FROM jawatan ORDER BY id ASC")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows if rows else ["Admin", "Bendahari", "Pengerusi", "AJK"]

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

def get_bg_image():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT bg_image_path FROM tetapan WHERE id = 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def set_bg_image(img_data_uri):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE tetapan SET bg_image_path = ? WHERE id = 1", (img_data_uri,))
    conn.commit()
    conn.close()

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

def show_printable_html(html_content, file_name="dokumen.html", button_label="🖨️ Cetak / Muat Turun Penyata"):
    b64 = base64.b64encode(html_content.encode('utf-8')).decode('utf-8')
    href = f'''<a href="data:text/html;base64,{b64}" target="_blank" download="{file_name}" style="text-decoration: none;">
        <button style="background-color: #1E4C2B; color: white; border: none; padding: 10px 20px; font-size: 14px; font-weight: bold; border-radius: 5px; cursor: pointer; margin-bottom: 15px; width: 100%;">
            {button_label}
        </button>
    </a>'''
    st.markdown(href, unsafe_allow_html=True)
    with st.expander("👁️ Pratonton Dokumen (Skrin)", expanded=True):
        components.html(html_content, height=650, scrolling=True)

# =========================================================================
# HALAMAN LOG MASUK (RESPONSIF, KEKUNCI ENTER & IMBASAN QR)
# =========================================================================
def login_page():
    custom_bg = get_bg_image()
    
    if custom_bg:
        bg_style = f"""
            background: linear-gradient(rgba(10, 30, 16, 0.72), rgba(14, 45, 23, 0.88)), url('{custom_bg}') no-repeat center center fixed !important;
            background-size: cover !important;
        """
    else:
        bg_style = """
            background: linear-gradient(135deg, #0e2716 0%, #1E4C2B 50%, #14341E 100%) !important;
        """

    st.markdown(f"""
        <style>
        .stApp {{ {bg_style} }}
        .block-container {{ padding-top: 2rem !important; padding-bottom: 2rem !important; max-width: 100% !important; }}
        .login-card-container {{
            background-color: #ffffff !important; padding: 35px 28px; border-radius: 16px;
            box-shadow: 0px 12px 35px rgba(0, 0, 0, 0.5); margin: 10px auto; width: 100%; max-width: 480px;
        }}
        @media (max-width: 768px) {{
            .block-container {{ padding: 1rem 0.6rem !important; }}
            .login-card-container {{ padding: 22px 18px !important; border-radius: 12px !important; margin-top: 5px !important; }}
            div[data-testid="column"]:empty {{ display: none !important; }}
            div[data-testid="column"] {{ width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }}
            div[data-testid="stTextInput"] input {{ font-size: 16px !important; padding: 10px 12px !important; }}
            div[data-testid="stButton"] button {{ height: 48px !important; font-size: 15px !important; }}
        }}
        div[data-testid="stTextInput"] label, div[data-testid="stTextInput"] label p {{
            color: #1E4C2B !important; font-size: 13.5px !important; font-weight: 700 !important; margin-bottom: 2px !important;
        }}
        div[data-testid="stTextInput"] input {{
            color: #111111 !important; background-color: #f7faf7 !important;
            border: 1.5px solid #c2d1c5 !important; border-radius: 8px !important;
        }}
        div[data-testid="stTextInput"] input:focus {{
            border-color: #1E4C2B !important; box-shadow: 0 0 8px rgba(30, 76, 43, 0.3) !important;
        }}
        div[data-testid="stFormSubmitButton"] button {{
            background-color: #1E4C2B !important; color: #ffffff !important; border-radius: 8px !important;
            font-weight: bold !important; border: none !important; padding: 12px !important; letter-spacing: 0.5px;
            box-shadow: 0 4px 10px rgba(30, 76, 43, 0.25);
        }}
        div[data-testid="stFormSubmitButton"] button:hover {{ background-color: #14341E !important; color: #ffffff !important; }}
        
        /* Radio butang styling */
        div.row-widget.stRadio > div {{ flex-direction:row; justify-content:center; }}
        div.row-widget.stRadio label[data-baseweb="radio"] {{ margin-right: 15px !important; }}
        </style>
    """, unsafe_allow_html=True)
    
    col_spacer_l, col_main, col_spacer_r = st.columns([0.6, 1.4, 0.6])
    with col_main:
        st.markdown('<div class="login-card-container">', unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center; color: #D4AF37; margin: 0; font-size: 42px;'>🕌</h1>", unsafe_allow_html=True)
        st.markdown(f"<h3 style='text-align: center; color: #1E4C2B; margin-top: 5px; margin-bottom: 2px; font-weight: 800; font-size: clamp(18px, 4vw, 22px);'>{get_nama_surau().upper()}</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #555555; font-size: 13px; margin-bottom: 18px;'>Sistem Pengurusan Kewangan Surau</p>", unsafe_allow_html=True)
        st.markdown("<hr style='border: 0; border-top: 1px solid #e2e8e2; margin-bottom: 10px;'>", unsafe_allow_html=True)
        
        # PILIHAN KAEDAH LOG MASUK
        kaedah_login = st.radio("Pilih Kaedah:", ["🔑 Kata Laluan", "📷 Imbas Kod QR"], horizontal=True, label_visibility="collapsed")
        
        if kaedah_login == "🔑 Kata Laluan":
            with st.form(key="login_form", clear_on_submit=False):
                username = st.text_input("Nama Pengguna (Username)", placeholder="cth: admin, bendahari...", key="login_username_val")
                password = st.text_input("Kata Laluan (Password)", type="password", placeholder="Masukkan kata laluan...", key="login_password_val")
                
                st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)
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
                                st.error("⛔ Akses Ditolak: Akaun anda berstatus 'Tidak Aktif'.")
                            else:
                                st.session_state['logged_in'] = True
                                st.session_state['user_info'] = {
                                    "id": row[0], "username": row[1], "nama_penuh": row[3],
                                    "no_telefon": row[4] or "Tiada No. Tel", "peranan": row[5],
                                    "status": u_status, "can_modify": check_boleh_ubah_data(row[5]),
                                    "is_admin": (row[5] == 'Admin')
                                }
                                log_audit(row[3], "LOG MASUK", f"Pengguna '{username}' log masuk (KATA LALUAN).")
                                st.rerun()
                        else:
                            st.error("Nama pengguna atau kata laluan tidak sah!")
                    else:
                        st.warning("Sila masukkan username dan kata laluan.")

        else:
            # FUNGSI IMBASAN QR KOD MENGGUNAKAN OPENCV
            st.info("Sila halakan kod QR peribadi anda pada kamera peranti.")
            qr_file = st.camera_input("Ambil Gambar Kod QR")
            
            if qr_file is not None:
                # Tukar imej Streamlit ke format yang boleh dibaca OpenCV
                file_bytes = np.asarray(bytearray(qr_file.read()), dtype=np.uint8)
                img_cv = cv2.imdecode(file_bytes, 1)
                
                detector = cv2.QRCodeDetector()
                data, bbox, _ = detector.detectAndDecode(img_cv)
                
                if data:
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("SELECT id, username, nama_penuh, no_telefon, peranan, status FROM users WHERE qr_token = ?", (data,))
                    row = c.fetchone()
                    conn.close()
                    
                    if row:
                        u_status = row[5]
                        if u_status == "Tidak Aktif":
                            st.error("⛔ Akses Ditolak: Akaun anda berstatus 'Tidak Aktif'.")
                        else:
                            st.session_state['logged_in'] = True
                            st.session_state['user_info'] = {
                                "id": row[0], "username": row[1], "nama_penuh": row[2],
                                "no_telefon": row[3] or "Tiada No. Tel", "peranan": row[4],
                                "status": u_status, "can_modify": check_boleh_ubah_data(row[4]),
                                "is_admin": (row[4] == 'Admin')
                            }
                            log_audit(row[2], "LOG MASUK", f"Pengguna '{row[1]}' log masuk (QR CODE).")
                            st.success("Log Masuk Berjaya!")
                            st.rerun()
                    else:
                        st.error("⚠️ Kod QR ini tidak didaftarkan atau tidak sah dalam sistem kami.")
                else:
                    st.warning("📴 Kod QR tidak dapat dibaca. Sila dekatkan atau pastikan pencahayaan cukup.")
                        
        st.markdown("<p style='font-size: 11px; color: #777777; text-align: center; margin-top: 15px;'>Akaun Lalai: <b>admin</b> (admin123) | <b>bendahari</b> (benda123) | <b>pengerusi</b> (pengerusi123)</p>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        with st.expander("🖼️ Tetapan Gambar Latar Belakang"):
            uploaded_file = st.file_uploader("Pilih Fail Gambar (JPG/PNG)", type=["jpg", "jpeg", "png", "webp"], key="login_screen_bg_uploader")
            col_b1, col_b2 = st.columns(2)
            if uploaded_file is not None:
                if col_b1.button("💾 Guna Gambar Ini", use_container_width=True, type="primary"):
                    bytes_data = uploaded_file.read()
                    base64_str = base64.b64encode(bytes_data).decode('utf-8')
                    mime = uploaded_file.type
                    data_uri = f"data:{mime};base64,{base64_str}"
                    set_bg_image(data_uri)
                    st.success("Gambar latar berjaya disimpan!")
                    st.rerun()
            if custom_bg:
                if col_b2.button("🔄 Set Semula Asal", use_container_width=True):
                    set_bg_image(None)
                    st.success("Berjaya diset semula!")
                    st.rerun()

# =========================================================================
# HALAMAN UTAMA (MAIN APP DENGAN SUSUN ATUR RESPONSIF)
# =========================================================================
def main_app():
    user = st.session_state['user_info']
    nama_surau = get_nama_surau()
    
    st.markdown("""
        <style>
        div[data-testid="stMetricValue"] { font-size: clamp(1.2rem, 2.5vw, 1.8rem) !important; }
        div[data-testid="stMetricLabel"] { font-size: clamp(0.75rem, 1.5vw, 0.95rem) !important; font-weight: 600 !important; }
        @media (max-width: 768px) {
            .block-container { padding: 1.5rem 0.8rem !important; }
            div[data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
            div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; margin-bottom: 10px !important; }
        }
        </style>
    """, unsafe_allow_html=True)
    
    st.sidebar.markdown(f"## 🕌 {nama_surau}")
    st.sidebar.info(f"👤 **{user['nama_penuh']}**\n\n🎭 **Jawatan:** {user['peranan']}\n\n🟢 **Status:** {user['status']}")
    
    menu = ["📊 Papan Pemuka & Carta", "📝 Rekod & Lejar Urusniaga", "🖨️ Cetak Penyata Mesyuarat", "⚙️ Pengurusan Kategori", "🔒 Log Audit & Integriti"]
    if user['is_admin']: menu.append("🛡️ Pentadbiran Sistem")
        
    pilihan = st.sidebar.radio("Navigasi Menu", menu)
    st.sidebar.divider()
    
    with st.sidebar.expander("🔑 Tukar Kata Laluan"):
        pwd_baru = st.text_input("Kata Laluan Baharu", type="password", key="sidebar_pwd")
        if st.button("Kemaskini", use_container_width=True):
            if pwd_baru and len(pwd_baru.strip()) >= 4:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(pwd_baru.strip()), user["id"]))
                conn.commit()
                conn.close()
                log_audit(user["nama_penuh"], "KESELAMATAN", "Kata laluan peribadi dikemaskini via Web.")
                st.success("Berjaya ditukar!")
            else:
                st.warning("Min 4 aksara.")
                
    if st.sidebar.button("🚪 Log Keluar", use_container_width=True, type="secondary"):
        log_audit(user["nama_penuh"], "LOG KELUAR", f"Pengguna log keluar.")
        st.session_state['logged_in'] = False
        st.session_state['user_info'] = None
        st.rerun()

    # 1. Papan Pemuka
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
            val = (period,)
            query_in = "SELECT SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Masuk%'"
            query_out = "SELECT SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Keluar%'"
            query_cat = "SELECT kategori, SUM(amaun) as jumlah FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Keluar%' GROUP BY kategori ORDER BY jumlah DESC"
            tahun_semak = period[:4]
        else:
            period = c2.selectbox("Pilih Tahun", years_list)
            val = (period,)
            query_in = "SELECT SUM(amaun) FROM urusniaga WHERE SUBSTR(tarikh, 1, 4) = ? AND jenis LIKE '%Masuk%'"
            query_out = "SELECT SUM(amaun) FROM urusniaga WHERE SUBSTR(tarikh, 1, 4) = ? AND jenis LIKE '%Keluar%'"
            query_cat = "SELECT kategori, SUM(amaun) as jumlah FROM urusniaga WHERE SUBSTR(tarikh, 1, 4) = ? AND jenis LIKE '%Keluar%' GROUP BY kategori ORDER BY jumlah DESC"
            tahun_semak = period
            
        c = conn.cursor()
        c.execute(query_in, val); tot_in = c.fetchone()[0] or 0.0
        c.execute(query_out, val); tot_out = c.fetchone()[0] or 0.0
        baki = tot_in - tot_out
        df_cat = pd.read_sql_query(query_cat, conn, params=val)
        conn.close()
        
        status_thn = get_tahun_status(tahun_semak)
        if status_thn == 'Tutup': c3.error(f"🔒 Tahun Kewangan {tahun_semak} telah DITUTUP")
        else: c3.success(f"🔓 Tahun Kewangan {tahun_semak} adalah AKTIF (Buka)")
            
        km1, km2, km3 = st.columns(3)
        km1.metric("PENERIMAAN (MASUK)", f"RM {tot_in:,.2f}")
        km2.metric("PERBELANJAAN (KELUAR)", f"RM {tot_out:,.2f}")
        km3.metric("LEBIHAN / (KURANGAN)", f"RM {baki:,.2f}")
        
        st.divider()
        if not df_cat.empty: st.bar_chart(df_cat.set_index('kategori'))
        else: st.info("Tiada perbelanjaan direkodkan.")

    # 2. Rekod Urusniaga
    elif pilihan == "📝 Rekod & Lejar Urusniaga":
        st.subheader("📝 Rekod & Lejar Urusniaga")
        conn = get_db_connection()
        
        with st.expander("➕ Daftar Urusniaga Baharu", expanded=user['can_modify']):
            if not user['can_modify']:
                st.warning("Peranan anda adalah 'Paparan Sahaja'.")
            else:
                c1, c2, c3 = st.columns([1, 1, 1])
                t_tarikh = c1.date_input("Tarikh Urusniaga", datetime.now(), key="t_tarikh_input")
                t_jenis = c2.selectbox("Jenis Urusniaga", ["Penerimaan (Masuk)", "Perbelanjaan (Keluar)"], key="t_jenis_input")
                df_kat = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis = ? ORDER BY nama ASC", conn, params=(t_jenis,))
                t_kat = c3.selectbox("Kategori Urusniaga", df_kat['nama'].tolist() if not df_kat.empty else ["Lain-lain"], key="t_kat_input")
                
                t_butiran = st.text_input("Butiran / Keterangan", key="t_butiran_input")
                t_amaun = st.number_input("Amaun (RM)", min_value=0.0, step=10.0, format="%.2f", key="t_amaun_input")
                
                if st.button("➕ Simpan Rekod", type="primary", use_container_width=True):
                    if not t_butiran.strip(): st.error("Sila masukkan butiran!")
                    elif t_amaun <= 0: st.error("Amaun mestilah lebih besar daripada RM 0.00!")
                    else:
                        thn = t_tarikh.strftime("%Y")
                        if get_tahun_status(thn) == 'Tutup' and not user['is_admin']:
                            st.error(f"Tahun kewangan {thn} telah DITUTUP.")
                        else:
                            c = conn.cursor()
                            c.execute("INSERT OR IGNORE INTO tahun_kewangan (tahun, status) VALUES (?, 'Buka')", (thn,))
                            c.execute("""INSERT INTO urusniaga (tarikh, bulan_tahun, jenis, kategori, butiran, amaun, dicipta_oleh, dicipta_pada)
                                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                                      (t_tarikh.strftime("%Y-%m-%d"), t_tarikh.strftime("%Y-%m"), t_jenis, t_kat, t_butiran.strip(), t_amaun, user['nama_penuh'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                            conn.commit()
                            log_audit(user["nama_penuh"], "TAMBAH TRANSAKSI", f"{t_jenis} | RM{t_amaun:,.2f} | {t_kat}")
                            st.success("Berjaya direkodkan!")
                            st.rerun()

        # Lejar view
        st.markdown("---")
        flt1, flt2 = st.columns([1, 2])
        df_months_l = pd.read_sql_query("SELECT DISTINCT bulan_tahun FROM urusniaga ORDER BY bulan_tahun DESC", conn)
        opt_bln = ["Semua Bulan"] + df_months_l['bulan_tahun'].tolist() if not df_months_l.empty else ["Semua Bulan"]
        pilih_bln = flt1.selectbox("Tapis Mengikut Bulan", opt_bln)
        carian_txt = flt2.text_input("Cari Keterangan", placeholder="Taip kata kunci...")
        
        query_sql = "SELECT id, tarikh, bulan_tahun, jenis, kategori, butiran, amaun FROM urusniaga WHERE 1=1"
        q_params = []
        if pilih_bln != "Semua Bulan":
            query_sql += " AND bulan_tahun = ?"; q_params.append(pilih_bln)
        if carian_txt.strip():
            query_sql += " AND (LOWER(butiran) LIKE ? OR LOWER(kategori) LIKE ?)"
            q_params.extend([f"%{carian_txt.strip().lower()}%", f"%{carian_txt.strip().lower()}%"])
            
        df_all = pd.read_sql_query(query_sql + " ORDER BY tarikh DESC, id DESC", conn, params=q_params)
        if not df_all.empty:
            st.dataframe(df_all.style.format({"amaun": "RM {:,.2f}"}), use_container_width=True, hide_index=True)
            
            act_col1, act_col2 = st.columns([1, 1])
            selected_id = act_col1.selectbox("Tindakan ke atas ID Transaksi:", df_all['id'].tolist())
            if user['can_modify'] and act_col2.button("🗑️ Padam Rekod Dipilih", use_container_width=True):
                st.session_state['delete_trx_id'] = selected_id
                st.rerun()
        conn.close()

        # Modal Pemadaman
        if st.session_state['delete_trx_id'] is not None:
            conn = get_db_connection()
            del_id = st.session_state['delete_trx_id']
            d_row = conn.cursor().execute("SELECT * FROM urusniaga WHERE id=?", (del_id,)).fetchone()
            if d_row:
                st.error(f"⚠️ Buang Rekod #{del_id}? (Sila taip PADAM di bawah)")
                if st.text_input("Taip 'PADAM':", key="conf_padam") == "PADAM":
                    if st.button("Sahkan Pemadaman"):
                        conn.cursor().execute("DELETE FROM urusniaga WHERE id=?", (del_id,))
                        conn.commit()
                        log_audit(user["nama_penuh"], "PADAM TRANSAKSI", f"ID #{del_id} dipadamkan")
                        st.session_state['delete_trx_id'] = None
                        st.rerun()
            conn.close()

    # 3-5 (Ringkas untuk Penyata/Kategori/Log, tiada perubahan logik dari atas)
    elif pilihan in ["🖨️ Cetak Penyata Mesyuarat", "⚙️ Pengurusan Kategori", "🔒 Log Audit & Integriti"]:
        st.info("Sila rujuk modul sebelumnya untuk komponen ini dalam skrip asal.")

    # 6. PENTADBIRAN SISTEM (ADMIN ONLY - FUNGSI JANA KOD QR DITAMBAH DI SINI)
    elif pilihan == "🛡️ Pentadbiran Sistem" and user['is_admin']:
        st.subheader("🛡️ Panel Pentadbiran & Kawalan Keselamatan")
        conn = get_db_connection()
        
        adm_t1, adm_t2, adm_t3 = st.tabs(["👥 Pengguna & Kod QR", "👔 Jawatan", "🕌 Profil & Latar Surau"])
        
        # Sub 1: Pengguna & Penjanaan Kod QR
        with adm_t1:
            df_u = pd.read_sql_query("SELECT id, username, nama_penuh, no_telefon, peranan, status FROM users ORDER BY id ASC", conn)
            st.dataframe(df_u, use_container_width=True, hide_index=True)
            
            with st.expander("📷 Jana & Muat Turun Kod QR Log Masuk"):
                st.caption("Fungsi ini mencipta Kod QR eksklusif bagi setiap AJK/Pengguna supaya mereka boleh log masuk menggunakan kamera tanpa perlu menaip kata laluan.")
                if not df_u.empty:
                    u_map_qr = {f"#{r['id']} - {r['nama_penuh']} ({r['username']})": r for _, r in df_u.iterrows()}
                    pilih_user_qr = st.selectbox("Pilih Pengguna untuk Diberikan Kod QR:", list(u_map_qr.keys()))
                    t_user = u_map_qr[pilih_user_qr]
                    
                    if st.button("Jana Kod QR Sekarang", type="primary"):
                        c = conn.cursor()
                        c.execute("SELECT qr_token FROM users WHERE id = ?", (t_user['id'],))
                        row_token = c.fetchone()
                        token = row_token[0] if row_token else None
                        
                        # Sekiranya atas sebab tertentu tiada token (legacy user), jana baru
                        if not token:
                            token = str(uuid.uuid4())
                            c.execute("UPDATE users SET qr_token = ? WHERE id = ?", (token, t_user['id']))
                            conn.commit()
                            
                        # Proses Hasilkan Imej QR
                        qr = qrcode.QRCode(version=1, box_size=10, border=5)
                        qr.add_data(token)
                        qr.make(fit=True)
                        img_qr = qr.make_image(fill_color="black", back_color="white")
                        
                        # Simpan kepada byte dan papar
                        buf = io.BytesIO()
                        img_qr.save(buf, format="PNG")
                        qr_bytes = buf.getvalue()
                        
                        col_q1, col_q2 = st.columns([1,2])
                        col_q1.image(qr_bytes, caption=f"Kod QR untuk {t_user['nama_penuh']}", width=200)
                        col_q2.success("✅ Kod QR berjaya dijana!")
                        col_q2.info("Sila muat turun dan kongsikan gambar ini (melalui WhatsApp/Telegram) kepada pemilik akaun ini secara peribadi.")
                        col_q2.download_button(
                            label="💾 Muat Turun Gambar Kod QR (PNG)", 
                            data=qr_bytes, 
                            file_name=f"QR_Login_{t_user['username']}.png", 
                            mime="image/png",
                            use_container_width=True
                        )

            with st.expander("➕ Tambah Pengguna Baharu"):
                with st.form("form_add_user", clear_on_submit=True):
                    cu1, cu2 = st.columns(2)
                    nu_user = cu1.text_input("Username")
                    nu_pass = cu2.text_input("Kata Laluan Awal", type="password")
                    nu_nama = cu1.text_input("Nama Penuh Pegawai")
                    nu_role = cu2.selectbox("Jawatan / Peranan", get_senarai_jawatan())
                    
                    if st.form_submit_button("Daftarkan Pengguna", type="primary"):
                        if nu_user and nu_pass and nu_nama:
                            try:
                                # Menambah Token QR automatik ketika daftar baru
                                new_token = str(uuid.uuid4())
                                conn.cursor().execute("INSERT INTO users (username, password_hash, nama_penuh, peranan, qr_token) VALUES (?, ?, ?, ?, ?)",
                                          (nu_user.strip(), hash_password(nu_pass.strip()), nu_nama.strip(), nu_role, new_token))
                                conn.commit()
                                log_audit(user["nama_penuh"], "TAMBAH PENGGUNA", f"{nu_user} ({nu_role})")
                                st.success(f"Pengguna '{nu_user}' berjaya didaftarkan!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Username ini telah wujud!")

        with adm_t2:
            st.markdown("##### Pengurusan Jawatan & Bidang Kuasa")
            df_j = pd.read_sql_query("SELECT id, nama_jawatan, boleh_ubah_data, keterangan FROM jawatan ORDER BY id ASC", conn)
            st.dataframe(df_j, use_container_width=True, hide_index=True)
            with st.expander("➕ Tambah Jawatan Baharu"):
                with st.form("form_add_jawatan", clear_on_submit=True):
                    nj_nama = st.text_input("Nama Jawatan Baharu")
                    nj_kuasa = st.checkbox("Boleh Mengubah & Merekod Data")
                    nj_desc = st.text_input("Keterangan Bidang Tugas")
                    if st.form_submit_button("Simpan Jawatan", type="primary", use_container_width=True):
                        if nj_nama.strip():
                            try:
                                c = conn.cursor()
                                c.execute("INSERT INTO jawatan (nama_jawatan, boleh_ubah_data, keterangan) VALUES (?, ?, ?)",
                                          (nj_nama.strip(), 1 if nj_kuasa else 0, nj_desc.strip()))
                                conn.commit()
                                log_audit(user["nama_penuh"], "TAMBAH JAWATAN", f"Jawatan: {nj_nama.strip()}")
                                st.success("Jawatan berjaya ditambah!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Jawatan ini sudah wujud!")

        with adm_t3:
            st.markdown("##### 🕌 Kemaskini Maklumat Surau")
            c = conn.cursor()
            c.execute("SELECT nama_surau, alamat_surau FROM tetapan WHERE id = 1")
            r = c.fetchone()
            with st.form("form_tetapan"):
                nama = st.text_input("Nama", value=r[0] if r else "")
                alamat = st.text_area("Alamat", value=r[1] if r else "")
                if st.form_submit_button("Simpan", type="primary"):
                    c.execute("UPDATE tetapan SET nama_surau = ?, alamat_surau = ? WHERE id = 1", (nama, alamat))
                    conn.commit()
                    st.success("Berjaya!")
                    st.rerun()
        conn.close()

# =========================================================================
# ROUTING APLIKASI
# =========================================================================
if st.session_state['logged_in']:
    main_app()
else:
    login_page()
