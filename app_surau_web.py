import streamlit as st
import sqlite3
from datetime import datetime
import pandas as pd
import hashlib
import os
import shutil
import base64
import streamlit.components.v1 as components

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
        dicipta_oleh TEXT NOT NULL,
        dicipta_pada TEXT NOT NULL,
        dikemaskini_oleh TEXT,
        dikemaskini_pada TEXT,
        nota_kemaskini_admin TEXT
    )""")
    
    c.execute("PRAGMA table_info(urusniaga)")
    u_cols = [col[1] for col in c.fetchall()]
    if 'dikemaskini_oleh' not in u_cols:
        c.execute("ALTER TABLE urusniaga ADD COLUMN dikemaskini_oleh TEXT")
    if 'dikemaskini_pada' not in u_cols:
        c.execute("ALTER TABLE urusniaga ADD COLUMN dikemaskini_pada TEXT")
    if 'nota_kemaskini_admin' not in u_cols:
        c.execute("ALTER TABLE urusniaga ADD COLUMN nota_kemaskini_admin TEXT")

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

# =========================================================================
# FUNGSI BANTUAN PAPARAN CETAKAN (PRINT HELPERS)
# =========================================================================
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
# HALAMAN LOG MASUK (RESPONSIF, KEKUNCI ENTER & GAMBAR CUSTOM)
# =========================================================================
def login_page():
    custom_bg = get_bg_image()
    
    # Latar belakang adaptif: Guna gambar custom jika wujud, jika tiada guna kecerunan hijau lalai
    if custom_bg:
        bg_style = f"""
            background: linear-gradient(rgba(10, 30, 16, 0.72), rgba(14, 45, 23, 0.88)), url('{custom_bg}') no-repeat center center fixed !important;
            background-size: cover !important;
        """
    else:
        bg_style = """
            background: linear-gradient(135deg, #0e2716 0%, #1E4C2B 50%, #14341E 100%) !important;
        """

    # Suntikan CSS Responsif Tablet & Mobile
    st.markdown(f"""
        <style>
        /* 1. Latar Belakang Keseluruhan */
        .stApp {{
            {bg_style}
        }}
        
        /* 2. Responsif Padding Container Utama */
        .block-container {{
            padding-top: 2rem !important;
            padding-bottom: 2rem !important;
            max-width: 100% !important;
        }}
        
        /* 3. Bekas Kad Borang Log Masuk */
        .login-card-container {{
            background-color: #ffffff !important;
            padding: 35px 28px;
            border-radius: 16px;
            box-shadow: 0px 12px 35px rgba(0, 0, 0, 0.5);
            margin: 10px auto;
            width: 100%;
            max-width: 480px;
        }}
        
        /* 4. Penyesuaian Skrin Tablet & Telefon Bimbit (Mobile First) */
        @media (max-width: 768px) {{
            .block-container {{
                padding: 1rem 0.6rem !important;
            }}
            .login-card-container {{
                padding: 22px 18px !important;
                border-radius: 12px !important;
                margin-top: 5px !important;
            }}
            /* Sembunyikan spacer columns kosong pada mobile */
            div[data-testid="column"]:empty {{
                display: none !important;
            }}
            div[data-testid="column"] {{
                width: 100% !important;
                flex: 1 1 100% !important;
                min-width: 100% !important;
            }}
            div[data-testid="stTextInput"] input {{
                font-size: 16px !important; /* Elak auto-zoom iOS Safari */
                padding: 10px 12px !important;
            }}
            div[data-testid="stButton"] button {{
                height: 48px !important;
                font-size: 15px !important;
            }}
        }}

        @media (min-width: 769px) and (max-width: 1024px) {{
            /* Tablet Layout */
            .login-card-container {{
                padding: 30px 24px !important;
                max-width: 460px;
            }}
        }}

        /* 5. Warna Teks Label & Borang */
        div[data-testid="stTextInput"] label,
        div[data-testid="stTextInput"] label p {{
            color: #1E4C2B !important;
            font-size: 13.5px !important;
            font-weight: 700 !important;
            margin-bottom: 2px !important;
        }}
        
        div[data-testid="stTextInput"] input {{
            color: #111111 !important;
            background-color: #f7faf7 !important;
            border: 1.5px solid #c2d1c5 !important;
            border-radius: 8px !important;
        }}
        
        div[data-testid="stTextInput"] input:focus {{
            border-color: #1E4C2B !important;
            box-shadow: 0 0 8px rgba(30, 76, 43, 0.3) !important;
        }}

        /* 6. Butang Log Masuk */
        div[data-testid="stFormSubmitButton"] button {{
            background-color: #1E4C2B !important;
            color: #ffffff !important;
            border-radius: 8px !important;
            font-weight: bold !important;
            border: none !important;
            padding: 12px !important;
            letter-spacing: 0.5px;
            box-shadow: 0 4px 10px rgba(30, 76, 43, 0.25);
        }}
        div[data-testid="stFormSubmitButton"] button:hover {{
            background-color: #14341E !important;
            color: #ffffff !important;
        }}
        </style>
    """, unsafe_allow_html=True)
    
    col_spacer_l, col_main, col_spacer_r = st.columns([0.6, 1.4, 0.6])
    with col_main:
        st.markdown('<div class="login-card-container">', unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center; color: #D4AF37; margin: 0; font-size: 42px;'>🕌</h1>", unsafe_allow_html=True)
        st.markdown(f"<h3 style='text-align: center; color: #1E4C2B; margin-top: 5px; margin-bottom: 2px; font-weight: 800; font-size: clamp(18px, 4vw, 22px);'>{get_nama_surau().upper()}</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #555555; font-size: 13px; margin-bottom: 18px;'>Sistem Pengurusan Kewangan Surau</p>", unsafe_allow_html=True)
        st.markdown("<hr style='border: 0; border-top: 1px solid #e2e8e2; margin-bottom: 18px;'>", unsafe_allow_html=True)
        
        # PENGGUNAAN st.form: MEMASTIKAN TEKAN 'ENTER' AKAN TERUS SUBMIT BORANG
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
                                "is_admin": (row[5] == 'Admin')
                            }
                            log_audit(row[3], "LOG MASUK", f"Pengguna '{username}' ({row[5]} - {u_status}) log masuk.")
                            st.rerun()
                    else:
                        st.error("Nama pengguna atau kata laluan tidak sah!")
                else:
                    st.warning("Sila masukkan username dan kata laluan.")
                    
        st.markdown("<p style='font-size: 11px; color: #777777; text-align: center; margin-top: 15px;'>Akaun Lalai: <b>admin</b> (admin123) | <b>bendahari</b> (benda123) | <b>pengerusi</b> (pengerusi123)</p>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

        # FUNGSI MEMASUKKAN GAMBAR CUSTOM DI MUKA DEPAN
        with st.expander("🖼️ Tetapan Gambar Latar Belakang Muka Depan"):
            st.caption("Muat naik gambar surau/masjid pilihan anda untuk menghiasi skrin log masuk:")
            uploaded_file = st.file_uploader("Pilih Fail Gambar (JPG/PNG)", type=["jpg", "jpeg", "png", "webp"], key="login_screen_bg_uploader")
            
            col_b1, col_b2 = st.columns(2)
            if uploaded_file is not None:
                if col_b1.button("💾 Gunakan Gambar Ini", use_container_width=True, type="primary"):
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
                    st.success("Gambar latar berjaya diset semula kepada asal!")
                    st.rerun()

# =========================================================================
# HALAMAN UTAMA (MAIN APP DENGAN SUSUN ATUR RESPONSIF)
# =========================================================================
def main_app():
    user = st.session_state['user_info']
    nama_surau = get_nama_surau()
    
    # Suntikan CSS Responsif untuk Papan Pemuka & Jadual
    st.markdown("""
        <style>
        /* Pengoptimuman Kad Metrik untuk Mobile & Tablet */
        div[data-testid="stMetricValue"] {
            font-size: clamp(1.2rem, 2.5vw, 1.8rem) !important;
        }
        div[data-testid="stMetricLabel"] {
            font-size: clamp(0.75rem, 1.5vw, 0.95rem) !important;
            font-weight: 600 !important;
        }
        
        @media (max-width: 768px) {
            .block-container {
                padding: 1.5rem 0.8rem !important;
            }
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
            }
            div[data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
                margin-bottom: 10px !important;
            }
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Sidebar
    st.sidebar.markdown(f"## 🕌 {nama_surau}")
    st.sidebar.info(f"👤 **{user['nama_penuh']}**\n\n🎭 **Jawatan:** {user['peranan']}\n\n🟢 **Status:** {user['status']}\n\n📞 **Tel:** {user['no_telefon']}")
    
    menu = [
        "📊 Papan Pemuka & Carta",
        "📝 Rekod & Lejar Urusniaga",
        "🖨️ Cetak Penyata Mesyuarat",
        "⚙️ Pengurusan Kategori",
        "🔒 Log Audit & Integriti"
    ]
    if user['is_admin']:
        menu.append("🛡️ Pentadbiran Sistem")
        
    pilihan = st.sidebar.radio("Navigasi Menu", menu)
    st.sidebar.divider()
    
    # Tukar Kata Laluan Sendiri
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

    # Ubah Nama Surau (Khusus untuk Admin)
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
        conn.close()
        
        status_thn = get_tahun_status(tahun_semak)
        if status_thn == 'Tutup':
            c3.error(f"🔒 Tahun Kewangan {tahun_semak} telah DITUTUP")
        else:
            c3.success(f"🔓 Tahun Kewangan {tahun_semak} adalah AKTIF (Buka)")
            
        # Kad Metrik Responsif
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
            
        # Butang Cetak Papan Pemuka
        st.divider()
        if st.button("🖨️ Jana & Cetak Papan Pemuka (PDF / HTML)", use_container_width=True):
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Penyata Papan Pemuka - {period}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 25px; background: #fff; color: #222; }}
        .header {{ text-align: center; border-bottom: 3px double #1E4C2B; padding-bottom: 12px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 22px; color: #1E4C2B; text-transform: uppercase; }}
        .cards {{ display: flex; flex-wrap: wrap; justify-content: space-between; margin-bottom: 25px; gap: 10px; }}
        .card {{ flex: 1 1 30%; padding: 12px; border-radius: 6px; box-sizing: border-box; text-align: center; }}
        .sign {{ display: flex; justify-content: space-between; margin-top: 60px; }}
        .sign-box {{ width: 28%; text-align: center; border-top: 1px solid #000; padding-top: 5px; font-weight: bold; font-size: 13px; }}
        @media (max-width: 768px) {{
            .card {{ flex: 1 1 100%; }}
            .sign {{ flex-direction: column; gap: 40px; }}
            .sign-box {{ width: 100%; }}
        }}
        @media print {{ .btn {{ display: none; }} body {{ padding: 0; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:8px 16px;border:none;cursor:pointer;border-radius:4px;margin-bottom:15px;font-weight:bold;">🖨️ Cetak / Simpan PDF</button>
    <div class="header">
        <h1>{nama_surau}</h1>
        <h3 style="margin:4px 0;">RINGKASAN PAPAN PEMUKA & STATUS KEDUDUKAN KEWANGAN</h3>
        <div>Mod: {mod} | Tempoh: {period} | Tarikh Cetakan: {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>
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
    # 2. REKOD & LEJAR URUSNIAGA
    # ---------------------------------------------------------------------
    elif pilihan == "📝 Rekod & Lejar Urusniaga":
        st.subheader("📝 Rekod & Lejar Urusniaga")
        conn = get_db_connection()
        
        # Seksyen Tambah
        with st.expander("➕ Daftar Urusniaga Baharu", expanded=user['can_modify']):
            if not user['can_modify']:
                st.warning("Peranan anda adalah 'Paparan Sahaja'. Hanya pegawai dengan kuasa ubah data dibenarkan menambah urusniaga.")
            else:
                c1, c2, c3 = st.columns([1, 1, 1])
                t_tarikh = c1.date_input("Tarikh Urusniaga", datetime.now(), key="t_tarikh_input")
                t_jenis = c2.selectbox("Jenis Urusniaga", ["Penerimaan (Masuk)", "Perbelanjaan (Keluar)"], key="t_jenis_input")
                
                df_kat = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis = ? ORDER BY nama ASC", conn, params=(t_jenis,))
                kategori_opts = df_kat['nama'].tolist() if not df_kat.empty else ["Lain-lain"]
                t_kat = c3.selectbox("Kategori Urusniaga", kategori_opts, key="t_kat_input")
                
                t_butiran = st.text_input("Butiran / Keterangan Urusniaga", key="t_butiran_input")
                t_amaun = st.number_input("Amaun (RM)", min_value=0.0, step=10.0, format="%.2f", key="t_amaun_input")
                
                if st.button("➕ Simpan Rekod Urusniaga", type="primary", key="btn_simpan_trx", use_container_width=True):
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
                                      (t_tarikh.strftime("%Y-%m-%d"), bln_thn, t_jenis, t_kat, t_butiran.strip(), t_amaun, user['nama_penuh'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                            conn.commit()
                            log_audit(user["nama_penuh"], "TAMBAH TRANSAKSI", f"{t_jenis} | RM{t_amaun:,.2f} | {t_kat} | {t_butiran}")
                            st.success("Urusniaga berjaya direkodkan!")
                            if 't_butiran_input' in st.session_state:
                                del st.session_state['t_butiran_input']
                            if 't_amaun_input' in st.session_state:
                                del st.session_state['t_amaun_input']
                            st.rerun()

        # Modal Edit Transaksi
        if st.session_state['edit_trx_id'] is not None:
            trx_id = st.session_state['edit_trx_id']
            c = conn.cursor()
            c.execute("SELECT tarikh, jenis, kategori, butiran, amaun FROM urusniaga WHERE id = ?", (trx_id,))
            e_row = c.fetchone()
            if e_row:
                st.warning(f"✏️ Mengemas kini Transaksi #{trx_id}")
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
                                   user['nama_penuh'], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), trx_id))
                        conn.commit()
                        log_audit(user["nama_penuh"], "KEMASKINI TRANSAKSI", f"ID #{trx_id} dikemaskini: RM{e_amaun:,.2f}")
                        st.session_state['edit_trx_id'] = None
                        st.success("Transaksi berjaya dikemaskini!")
                        st.rerun()
                if ce_btn2.button("Batal", key=f"btn_cancel_edit_{trx_id}", use_container_width=True):
                    st.session_state['edit_trx_id'] = None
                    st.rerun()

        # Modal Padam Transaksi
        if st.session_state['delete_trx_id'] is not None:
            del_id = st.session_state['delete_trx_id']
            c = conn.cursor()
            c.execute("SELECT tarikh, jenis, kategori, butiran, amaun FROM urusniaga WHERE id = ?", (del_id,))
            d_row = c.fetchone()
            if d_row:
                st.error(f"⚠️ PENGESAHAN PEMADAMAN: Transaksi #{del_id} | {d_row[0]} | {d_row[1]} | RM{d_row[4]:,.2f} ({d_row[3]})")
                st.caption("Tindakan ini adalah KEKAL. Sila taip perkataan **PADAM** di bawah untuk mengesahkan pemadaman:")
                confirm_txt = st.text_input("Taip 'PADAM' untuk mengesahkan:", key="confirm_padam_box")
                cd_b1, cd_b2 = st.columns(2)
                if cd_b1.button("🗑️ Sahkan & Padam Rekod", type="primary", use_container_width=True):
                    if confirm_txt.strip().upper() == "PADAM":
                        thn_d = d_row[0][:4]
                        if get_tahun_status(thn_d) == 'Tutup' and not user['is_admin']:
                            st.error(f"Tahun {thn_d} telah ditutup. Tidak boleh dipadam.")
                        else:
                            c.execute("DELETE FROM urusniaga WHERE id = ?", (del_id,))
                            conn.commit()
                            log_audit(user["nama_penuh"], "PADAM TRANSAKSI", f"ID #{del_id} dipadamkan: {d_row[3]} (RM{d_row[4]:,.2f})")
                            st.session_state['delete_trx_id'] = None
                            st.success(f"Rekod #{del_id} berjaya dipadam!")
                            st.rerun()
                    else:
                        st.error("Perkataan tidak sepadan! Pemadaman dibatalkan.")
                if cd_b2.button("Batal Pemadaman", use_container_width=True):
                    st.session_state['delete_trx_id'] = None
                    st.rerun()

        # Modal Baucar Bayaran (PV)
        if st.session_state['view_voucher_id'] is not None:
            pv_id = st.session_state['view_voucher_id']
            c = conn.cursor()
            c.execute("SELECT id, tarikh, jenis, kategori, butiran, amaun FROM urusniaga WHERE id = ?", (pv_id,))
            pv_row = c.fetchone()
            if pv_row:
                st.info(f"📄 Baucar Bayaran PV-{pv_id:04d}")
                html_pv = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Baucar Bayaran PV-{pv_id:04d}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; background: #fafafa; }}
        .box {{ max-width: 800px; margin: 0 auto; background: #fff; border: 2px solid #222; padding: 25px; }}
        .header {{ text-align: center; border-bottom: 2px solid #222; padding-bottom: 15px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 20px; color: #1E4C2B; text-transform: uppercase; }}
        .header h2 {{ margin: 5px 0 0 0; font-size: 15px; color: #444; }}
        .info-table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
        .info-table td {{ padding: 8px 4px; font-size: 14px; vertical-align: top; }}
        .label {{ font-weight: bold; width: 130px; color: #333; }}
        .val {{ border-bottom: 1px dotted #666; color: #111; }}
        .amount-panel {{ background: #f0f7f2; border: 1px solid #1E4C2B; padding: 12px 15px; margin: 20px 0; }}
        .amount-val {{ font-size: 20px; font-weight: bold; color: #1E4C2B; }}
        .signatures {{ display: flex; justify-content: space-between; margin-top: 40px; }}
        .sign-box {{ width: 30%; text-align: center; }}
        .sign-line {{ border-top: 1px solid #333; margin-top: 50px; padding-top: 5px; font-weight: bold; font-size: 12px; }}
        @media (max-width: 600px) {{
            .signatures {{ flex-direction: column; gap: 30px; }}
            .sign-box {{ width: 100%; }}
        }}
        @media print {{ .btn {{ display: none; }} body {{ padding: 0; }} .box {{ border: 2px solid #000; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:8px 16px;border:none;cursor:pointer;border-radius:4px;margin-bottom:15px;font-weight:bold;width:100%;">🖨️ Cetak Baucar / Simpan PDF</button>
    <div class="box">
        <div class="header">
            <h1>{nama_surau}</h1>
            <h2>BAUCAR BAYARAN / PAYMENT VOUCHER</h2>
        </div>
        <table class="info-table">
            <tr>
                <td class="label">No. Baucar:</td>
                <td class="val"><strong>PV-{pv_id:04d}</strong></td>
                <td class="label" style="text-align: right; width: 80px;">Tarikh:</td>
                <td class="val" style="width: 120px;">{pv_row[1]}</td>
            </tr>
            <tr>
                <td class="label">Kategori Bayaran:</td>
                <td class="val" colspan="3">{pv_row[3]}</td>
            </tr>
            <tr>
                <td class="label">Maksud / Butiran:</td>
                <td class="val" colspan="3">{pv_row[4]}</td>
            </tr>
        </table>
        <div class="amount-panel">
            <div style="font-size: 12px; font-weight: bold; color: #1E4C2B;">JUMLAH DIBAYAR:</div>
            <div class="amount-val">RM {pv_row[5]:,.2f}</div>
        </div>
        <div class="signatures">
            <div class="sign-box"><div class="sign-line">Disediakan Oleh<br>(Bendahari)</div></div>
            <div class="sign-box"><div class="sign-line">Disemak / Diluluskan<br>(Pengerusi)</div></div>
            <div class="sign-box"><div class="sign-line">Diterima Oleh<br>(Penerima Bayaran)</div></div>
        </div>
    </div>
    <script>window.print();</script>
</body>
</html>"""
                show_printable_html(html_pv, f"Baucar_Bayaran_PV_{pv_id}.html", "🖨️ Buka & Cetak Baucar Bayaran")
                if st.button("Tutup Paparan Baucar", use_container_width=True):
                    st.session_state['view_voucher_id'] = None
                    st.rerun()

        # Penapis dan Jadual Lejar
        st.markdown("---")
        flt1, flt2 = st.columns([1, 2])
        
        df_months_l = pd.read_sql_query("SELECT DISTINCT bulan_tahun FROM urusniaga ORDER BY bulan_tahun DESC", conn)
        opt_bln = ["Semua Bulan"] + df_months_l['bulan_tahun'].tolist() if not df_months_l.empty else ["Semua Bulan"]
        pilih_bln = flt1.selectbox("Tapis Mengikut Bulan", opt_bln)
        carian_txt = flt2.text_input("Cari Keterangan / Kategori", placeholder="Taip kata kunci carian...")
        
        query_sql = "SELECT id, tarikh, bulan_tahun, jenis, kategori, butiran, amaun FROM urusniaga WHERE 1=1"
        q_params = []
        if pilih_bln != "Semua Bulan":
            query_sql += " AND bulan_tahun = ?"
            q_params.append(pilih_bln)
        if carian_txt.strip():
            query_sql += " AND (LOWER(butiran) LIKE ? OR LOWER(kategori) LIKE ?)"
            q_params.append(f"%{carian_txt.strip().lower()}%")
            q_params.append(f"%{carian_txt.strip().lower()}%")
            
        query_sql += " ORDER BY tarikh DESC, id DESC"
        df_all = pd.read_sql_query(query_sql, conn, params=q_params)
        
        if not df_all.empty:
            st.dataframe(
                df_all.style.format({"amaun": "RM {:,.2f}"}),
                use_container_width=True,
                hide_index=True
            )
            
            st.markdown("##### 🛠️ Tindakan ke atas Rekod:")
            act_col1, act_col2, act_col3 = st.columns([1.5, 1, 1])
            selected_id = act_col1.selectbox("Pilih No. ID Transaksi:", df_all['id'].tolist(), key="sel_trx_id")
            
            sel_row = df_all[df_all['id'] == selected_id].iloc[0]
            is_keluar = "Keluar" in sel_row['jenis']
            
            if act_col2.button("📄 Jana Baucar Bayaran", disabled=not is_keluar, use_container_width=True):
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
            st.download_button("📊 Muat Turun Data (CSV)", data=csv_data, file_name=f"Lejar_Surau_{datetime.now().strftime('%Y%m%d')}.csv", mime="text/csv", use_container_width=True)
        else:
            st.info("Tiada rekod transaksi dijumpai mengikut kriteria tapisan.")
            
        conn.close()

    # ---------------------------------------------------------------------
    # 3. CETAK PENYATA MESYUARAT (BULANAN & TAHUNAN)
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
            
            if st.button("🖨️ Jana Penyata Bulanan Rasmi", type="primary", use_container_width=True):
                c = conn.cursor()
                c.execute("SELECT SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Masuk%'", (sel_period,))
                tot_in = c.fetchone()[0] or 0.0
                c.execute("SELECT SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Keluar%'", (sel_period,))
                tot_out = c.fetchone()[0] or 0.0
                baki = tot_in - tot_out
                
                c.execute("SELECT kategori, SUM(amaun) FROM urusniaga WHERE bulan_tahun = ? AND jenis LIKE '%Keluar%' GROUP BY kategori ORDER BY 2 DESC", (sel_period,))
                cat_rows = c.fetchall()
                c.execute("SELECT tarikh, jenis, kategori, butiran, amaun FROM urusniaga WHERE bulan_tahun = ? ORDER BY tarikh ASC, id ASC", (sel_period,))
                trx_rows = c.fetchall()
                
                cat_html = "".join([f"<tr><td>{cat}</td><td style='text-align:right;'>RM {amt:,.2f}</td></tr>" for cat, amt in cat_rows])
                trx_items = []
                for r in trx_rows:
                    badge = "<span style='color:green;font-weight:bold;'>MASUK</span>" if "Masuk" in r[1] else "<span style='color:red;font-weight:bold;'>KELUAR</span>"
                    trx_items.append(f"<tr><td>{r[0]}</td><td>{badge}</td><td>{r[2]}</td><td>{r[3]}</td><td style='text-align:right;'>RM {r[4]:,.2f}</td></tr>")
                trx_html = "".join(trx_items)
                
                html_rep = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Laporan Kewangan Bulanan - {sel_period}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; background: #fff; color: #222; }}
        .header {{ text-align: center; border-bottom: 3px double #1E4C2B; padding-bottom: 12px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 22px; color: #1E4C2B; text-transform: uppercase; }}
        .summary-grid {{ display: flex; flex-wrap: wrap; justify-content: space-between; margin-bottom: 20px; gap: 10px; }}
        .card {{ flex: 1 1 30%; border: 1px solid #ddd; padding: 10px; border-radius: 4px; box-sizing: border-box; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; }}
        th, td {{ border: 1px solid #ccc; padding: 8px 10px; }}
        th {{ background-color: #1E4C2B; color: #fff; text-align: left; }}
        .sign-area {{ display: flex; justify-content: space-between; margin-top: 40px; page-break-inside: avoid; }}
        .sign-box {{ width: 28%; text-align: center; border-top: 1px solid #000; padding-top: 5px; font-weight: bold; font-size: 12px; }}
        @media (max-width: 650px) {{
            .card {{ flex: 1 1 100%; }}
            .sign-area {{ flex-direction: column; gap: 30px; }}
            .sign-box {{ width: 100%; }}
        }}
        @media print {{ .btn {{ display: none; }} body {{ padding: 0; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:8px 16px;border:none;cursor:pointer;border-radius:4px;margin-bottom:15px;font-weight:bold;width:100%;">🖨️ Cetak / Simpan sebagai PDF</button>
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
        <tr><th>Tarikh</th><th>Jenis</th><th>Kategori</th><th>Butiran</th><th style="text-align:right;">Amaun (RM)</th></tr>
        {trx_html if trx_rows else "<tr><td colspan='5'>Tiada transaksi.</td></tr>"}
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
            
            if st.button("🖨️ Jana Penyata Tahunan Rasmi (AGM)", type="primary", use_container_width=True):
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Penyata Kewangan Tahunan - {sel_year}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; background: #fff; color: #222; }}
        .header {{ text-align: center; border-bottom: 3px double #1E4C2B; padding-bottom: 12px; margin-bottom: 20px; }}
        .header h1 {{ margin: 0; font-size: 22px; color: #1E4C2B; text-transform: uppercase; }}
        table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; }}
        th, td {{ border: 1px solid #ccc; padding: 8px 10px; }}
        th {{ background-color: #1E4C2B; color: #fff; text-align: left; }}
        .sign-area {{ display: flex; justify-content: space-between; margin-top: 50px; }}
        .sign-box {{ width: 28%; text-align: center; border-top: 1px solid #000; padding-top: 5px; font-weight: bold; font-size: 12px; }}
        @media (max-width: 650px) {{
            .sign-area {{ flex-direction: column; gap: 30px; }}
            .sign-box {{ width: 100%; }}
        }}
        @media print {{ .btn {{ display: none; }} body {{ padding: 0; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:8px 16px;border:none;cursor:pointer;border-radius:4px;margin-bottom:15px;font-weight:bold;width:100%;">🖨️ Cetak / Simpan sebagai PDF</button>
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
    # 4. PENGURUSAN KATEGORI
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
                    if st.form_submit_button("Simpan Kategori", type="primary", use_container_width=True):
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
                    kat_options = {f"[{r['jenis']}] {r['nama']}": (r['id'], r['nama']) for _, r in df_kats_all.iterrows()}
                    pilih_kat_label = st.selectbox("Pilih Kategori untuk Diubah:", list(kat_options.keys()))
                    
                    kat_id_edit, nama_kat_asal = kat_options[pilih_kat_label]
                    nama_kat_baru = st.text_input("Nama Baharu Kategori:", value=nama_kat_asal, key="edit_kat_input")
                    
                    st.caption("ℹ️ Nota: Menukar nama kategori akan mengemas kini semua transaksi lejar terdahulu secara automatik demi integriti data.")
                    
                    if st.button("💾 Simpan Perubahan Nama Kategori", type="primary", use_container_width=True):
                        if nama_kat_baru.strip() and nama_kat_baru.strip() != nama_kat_asal:
                            try:
                                c = conn.cursor()
                                c.execute("UPDATE kategori SET nama = ? WHERE id = ?", (nama_kat_baru.strip(), kat_id_edit))
                                c.execute("UPDATE urusniaga SET kategori = ? WHERE kategori = ?", (nama_kat_baru.strip(), nama_kat_asal))
                                conn.commit()
                                log_audit(user["nama_penuh"], "KEMASKINI KATEGORI", f"Kategori '{nama_kat_asal}' ditukar ke '{nama_kat_baru.strip()}'")
                                st.success(f"Kategori '{nama_kat_asal}' berjaya ditukar kepada '{nama_kat_baru.strip()}'!")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                st.error("Nama kategori tersebut telah digunakan!")
                        else:
                            st.warning("Sila masukkan nama baharu yang berbeza.")
                            
        st.markdown("#### Senarai Kategori Sedia Ada")
        df_kats = pd.read_sql_query("SELECT id, jenis, nama FROM kategori ORDER BY jenis DESC, nama ASC", conn)
        st.dataframe(df_kats, use_container_width=True, hide_index=True)
        
        col_k1, col_k2 = st.columns([1, 2])
        if col_k1.button("🖨️ Cetak Senarai Kategori", use_container_width=True):
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Senarai Kategori Kewangan</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; padding: 20px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th, td {{ border: 1px solid #333; padding: 7px 10px; }}
        th {{ background: #1E4C2B; color: white; }}
        .grid-box {{ display: flex; justify-content: space-between; gap: 20px; margin-top: 20px; }}
        .col-half {{ width: 48%; }}
        @media (max-width: 600px) {{
            .grid-box {{ flex-direction: column; }}
            .col-half {{ width: 100%; }}
        }}
        @media print {{ .btn {{ display: none; }} }}
    </style>
</head>
<body>
    <button class="btn" onclick="window.print()" style="background:#1E4C2B;color:#fff;padding:8px 16px;border:none;cursor:pointer;border-radius:4px;margin-bottom:15px;font-weight:bold;width:100%;">🖨️ Cetak / Simpan PDF</button>
    <h2 style="color:#1E4C2B;text-align:center;margin-bottom:3px;">{nama_surau}</h2>
    <h3 style="text-align:center;margin-top:0;">CARTA KATEGORI PENERIMAAN (MASUK) & PERBELANJAAN (KELUAR)</h3>
    <div style="font-size:12px;margin-bottom:10px;">Tarikh Cetakan: {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>
    <div class="grid-box">
        <div class="col-half">
            <h4 style="color:#274E13;margin-bottom:5px;">1. Kategori Penerimaan (Duit Masuk)</h4>
            <table><tr><th style="width:40px;">Bil</th><th>Nama Kategori Masuk</th></tr>{inc_html}</table>
        </div>
        <div class="col-half">
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
    # 5. LOG AUDIT & INTEGRITI DATA
    # ---------------------------------------------------------------------
    elif pilihan == "🔒 Log Audit & Integriti":
        st.subheader("🔒 Jejak Audit Keselamatan & Integriti (Audit Trail)")
        st.caption("Semua aktiviti log masuk, penambahan, pengemaskinian, dan pemadaman data direkodkan secara kekal.")
        conn = get_db_connection()
        df_audit = pd.read_sql_query("SELECT id, tarikh_masa, pengguna, tindakan, butiran FROM audit_log ORDER BY id DESC LIMIT 500", conn)
        conn.close()
        st.dataframe(df_audit, use_container_width=True, hide_index=True)

    # ---------------------------------------------------------------------
    # 6. PENTADBIRAN SISTEM (ADMIN ONLY)
    # ---------------------------------------------------------------------
    elif pilihan == "🛡️ Pentadbiran Sistem" and user['is_admin']:
        st.subheader("🛡️ Panel Pentadbiran & Kawalan Keselamatan")
        conn = get_db_connection()
        
        adm_t1, adm_t2, adm_t3, adm_t4, adm_t5, adm_t6 = st.tabs([
            "👥 Pengguna", 
            "👔 Jawatan", 
            "📅 Tutup/Buka Tahun", 
            "💾 Sandaran & Pulih", 
            "🗄️ Statistik DB",
            "🕌 Profil & Latar Surau"
        ])
        
        # Sub 1: Pengguna
        with adm_t1:
            st.markdown("##### Senarai Pengguna & Status Keahlian")
            df_u = pd.read_sql_query("SELECT id, username, nama_penuh, no_telefon, peranan, status FROM users ORDER BY id ASC", conn)
            df_u['Status Keahlian'] = df_u['status'].apply(lambda s: "🟢 Aktif" if s == "Aktif" else "🔴 Tidak Aktif")
            st.dataframe(df_u[['id', 'username', 'nama_penuh', 'no_telefon', 'peranan', 'Status Keahlian']], use_container_width=True, hide_index=True)
            
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
                    
                    if st.form_submit_button("Daftarkan Pengguna", type="primary", use_container_width=True):
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
                        
                        if st.form_submit_button("💾 Simpan Kemaskini Pengguna", type="primary", use_container_width=True):
                            c = conn.cursor()
                            c.execute("UPDATE users SET nama_penuh = ?, no_telefon = ?, peranan = ?, status = ? WHERE id = ?",
                                      (up_nama.strip(), up_tel.strip(), up_role, up_status, int(usr_data['id'])))
                            conn.commit()
                            log_audit(user["nama_penuh"], "KEMASKINI PENGGUNA", f"Pengguna #{usr_data['id']}: Jawatan={up_role}, Status={up_status}")
                            st.success(f"Maklumat pengguna '{usr_data['username']}' berjaya dikemas kini!")
                            st.rerun()

            with st.expander("🔑 Reset Kata Laluan Pengguna"):
                if not df_u.empty:
                    u_pwd_map = {f"#{r['id']} - {r['username']} ({r['nama_penuh']})": r for _, r in df_u.iterrows()}
                    pilih_pwd_user = st.selectbox("Pilih Pengguna:", list(u_pwd_map.keys()), key="sel_pwd_u")
                    u_pwd_target = u_pwd_map[pilih_pwd_user]
                    
                    new_pwd_input = st.text_input("Kata Laluan Baharu:", type="password", key="new_pwd_admin_input")
                    if st.button("Reset Kata Laluan Sekarang", type="primary", use_container_width=True):
                        if new_pwd_input and len(new_pwd_input.strip()) >= 4:
                            c = conn.cursor()
                            c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_pwd_input.strip()), int(u_pwd_target['id'])))
                            conn.commit()
                            log_audit(user["nama_penuh"], "RESET KATA LALUAN", f"Kata laluan bagi '{u_pwd_target['username']}' direset.")
                            st.success(f"Kata laluan bagi '{u_pwd_target['username']}' berjaya direset!")
                        else:
                            st.warning("Kata laluan mestilah sekurang-kurangnya 4 aksara.")

        # Sub 2: Jawatan
        with adm_t2:
            st.markdown("##### Pengurusan Jawatan & Bidang Kuasa")
            df_j = pd.read_sql_query("SELECT id, nama_jawatan, boleh_ubah_data, keterangan FROM jawatan ORDER BY id ASC", conn)
            df_j['Kuasa Akses'] = df_j['boleh_ubah_data'].map({1: 'Boleh Ubah & Rekod Data', 0: 'Paparan Sahaja (View Only)'})
            st.dataframe(df_j[['id', 'nama_jawatan', 'Kuasa Akses', 'keterangan']], use_container_width=True, hide_index=True)
            
            with st.expander("➕ Tambah Jawatan Baharu"):
                with st.form("form_add_jawatan", clear_on_submit=True):
                    nj_nama = st.text_input("Nama Jawatan Baharu")
                    nj_kuasa = st.checkbox("Boleh Mengubah & Merekod Data (Kuasa Bendahari)")
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
                        else:
                            st.warning("Sila masukkan nama jawatan.")

        # Sub 3: Tutup/Buka Tahun
        with adm_t3:
            st.markdown("##### Kawalan Penutupan Tahun Kewangan")
            df_thn = pd.read_sql_query("SELECT tahun, status, ditutup_oleh, ditutup_pada FROM tahun_kewangan ORDER BY tahun DESC", conn)
            st.dataframe(df_thn, use_container_width=True, hide_index=True)
            
            ct1, ct2 = st.columns(2)
            thn_pilih = ct1.selectbox("Pilih Tahun", df_thn['tahun'].tolist() if not df_thn.empty else [datetime.now().strftime("%Y")])
            act_thn = ct2.radio("Tindakan", ["Kunci / Tutup Tahun", "Buka Semula Tahun"])
            if st.button("Laksanakan Status Tahun", type="primary", use_container_width=True):
                c = conn.cursor()
                if "Tutup" in act_thn:
                    c.execute("UPDATE tahun_kewangan SET status = 'Tutup', ditutup_oleh = ?, ditutup_pada = ? WHERE tahun = ?",
                              (user['nama_penuh'], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(thn_pilih)))
                    log_audit(user["nama_penuh"], "TUTUP TAHUN", f"Tahun {thn_pilih} ditutup.")
                    st.success(f"Tahun {thn_pilih} telah DITUTUP.")
                else:
                    c.execute("UPDATE tahun_kewangan SET status = 'Buka', ditutup_oleh = NULL, ditutup_pada = NULL WHERE tahun = ?", (str(thn_pilih),))
                    log_audit(user["nama_penuh"], "BUKA TAHUN", f"Tahun {thn_pilih} dibuka semula.")
                    st.success(f"Tahun {thn_pilih} telah DIBUKA SEMULA.")
                conn.commit()
                st.rerun()

        # Sub 4: Backup & Restore
        with adm_t4:
            st.markdown("##### 💾 Sandaran & Pemulihan Database (.db)")
            if os.path.exists('sistem_surau.db'):
                with open('sistem_surau.db', 'rb') as f_db:
                    st.download_button(
                        "💾 Muat Turun Fail Sandaran Database",
                        data=f_db,
                        file_name=f"Backup_Surau_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                        mime="application/x-sqlite3",
                        type="primary",
                        use_container_width=True
                    )
            
            st.markdown("---")
            st.markdown("##### 🔄 Pulihkan Database dari Fail")
            uploaded_db = st.file_uploader("Pilih fail .db untuk dipulihkan", type=["db", "sqlite", "sqlite3"])
            if uploaded_db is not None:
                if st.button("⚠️ Sahkan & Pulihkan Database", type="secondary", use_container_width=True):
                    shutil.copy2('sistem_surau.db', f"sistem_surau_pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak")
                    with open('sistem_surau.db', 'wb') as f_dest:
                        f_dest.write(uploaded_db.getbuffer())
                    log_audit(user["nama_penuh"], "PULIHKAN DATABASE", "Database dipulihkan via fail muat naik Web.")
                    st.success("Pangkalan data berjaya dipulihkan!")
                    st.rerun()

        # Sub 5: Statistik DB
        with adm_t5:
            st.markdown("##### 🗄️ Statistik Fail Pangkalan Data SQLite3")
            db_size = os.path.getsize('sistem_surau.db') / 1024 if os.path.exists('sistem_surau.db') else 0
            st.write(f"**Saiz Fail Semasa:** `{db_size:,.2f} KB`")
            
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM urusniaga"); n_trx = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM users"); n_usr = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM kategori"); n_kat = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM jawatan"); n_jwt = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM audit_log"); n_aud = c.fetchone()[0]
            
            st.write(f"• **Jumlah Urusniaga:** {n_trx:,} rekod")
            st.write(f"• **Jumlah Pengguna:** {n_usr:,} orang")
            st.write(f"• **Jumlah Kategori:** {n_kat:,} kategori")
            st.write(f"• **Jumlah Log Audit:** {n_aud:,} log")
            
            if st.button("⚡ Optimumkan Pangkalan Data (VACUUM)", use_container_width=True):
                conn.execute("VACUUM")
                log_audit(user["nama_penuh"], "VACUUM DB", "Database dioptimumkan via Web.")
                st.success("Pangkalan data telah dioptimumkan!")
        
        # Sub 6: Profil & Latar Belakang Surau
        with adm_t6:
            st.markdown("##### 🕌 Kemaskini Maklumat & Gambar Latar Belakang Muka Depan")
            c = conn.cursor()
            c.execute("SELECT nama_surau, alamat_surau FROM tetapan WHERE id = 1")
            row_tetapan = c.fetchone()
            curr_nama = row_tetapan[0] if row_tetapan else "Surau An Najdah"
            curr_alamat = row_tetapan[1] if (row_tetapan and row_tetapan[1]) else ""
            
            with st.form("form_tetapan_surau"):
                input_nama_surau = st.text_input("Nama Rasmi Surau:", value=curr_nama)
                input_alamat = st.text_area("Alamat Surau (Pilihan):", value=curr_alamat)
                
                if st.form_submit_button("💾 Simpan Maklumat Surau", type="primary", use_container_width=True):
                    if input_nama_surau.strip():
                        c.execute("UPDATE tetapan SET nama_surau = ?, alamat_surau = ? WHERE id = 1", 
                                  (input_nama_surau.strip(), input_alamat.strip()))
                        conn.commit()
                        log_audit(user["nama_penuh"], "KEMASKINI TETAPAN", f"Nama surau ditukar kepada '{input_nama_surau.strip()}'")
                        st.success("Maklumat surau berjaya dikemaskini!")
                        st.rerun()
                    else:
                        st.error("Nama surau tidak boleh dibiarkan kosong!")
            
            st.markdown("---")
            st.markdown("##### 🖼️ Gambar Latar Log Masuk")
            adm_img_upload = st.file_uploader("Muat Naik Gambar Latar Utama (JPG/PNG)", type=["jpg", "jpeg", "png", "webp"], key="adm_bg_uploader")
            c_adm_b1, c_adm_b2 = st.columns(2)
            if adm_img_upload is not None:
                if c_adm_b1.button("Simpan Latar Baharu", type="primary", use_container_width=True):
                    b64_str = base64.b64encode(adm_img_upload.read()).decode('utf-8')
                    data_uri = f"data:{adm_img_upload.type};base64,{b64_str}"
                    set_bg_image(data_uri)
                    log_audit(user["nama_penuh"], "KEMASKINI LATAR", "Gambar latar login dikemaskini oleh Admin.")
                    st.success("Gambar latar berjaya disimpan!")
                    st.rerun()
            if get_bg_image():
                if c_adm_b2.button("Padam & Reset ke Warna Lalai", use_container_width=True):
                    set_bg_image(None)
                    st.success("Gambar latar diset semula!")
                    st.rerun()
                
        conn.close()

# =========================================================================
# ROUTING APLIKASI
# =========================================================================
if st.session_state['logged_in']:
    main_app()
else:
    login_page()