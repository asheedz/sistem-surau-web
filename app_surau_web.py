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
# KONFIGURASI LAMAN (RESPONSIF MOBILE / DESKTOP)
# =========================================================================
st.set_page_config(
    page_title="Sistem Kewangan Surau",
    page_icon="🕌",
    layout="wide",
    initial_sidebar_state="auto"
)

# =========================================================================
# GAYA RESPONSIF KHAS UNTUK MOBILE (HANDPHONE) & TABLET
# =========================================================================
def inject_responsive_css():
    st.markdown("""
        <style>
        /* 1. Pengoptimuman Ruang Paparan Utama untuk Skrin Telefon (< 768px) */
        @media (max-width: 768px) {
            .main .block-container {
                padding-top: 1.2rem !important;
                padding-bottom: 2rem !important;
                padding-left: 0.8rem !important;
                padding-right: 0.8rem !important;
            }
            
            /* Sembunyikan kolum penjarak kosong di telefon */
            div[data-testid="column"]:empty {
                display: none !important;
            }

            /* Kolum borang disusun menegak (stacking) di skrin kecil */
            div[data-testid="stHorizontalBlock"] {
                flex-wrap: wrap !important;
                gap: 0.5rem !important;
            }
            div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }

            /* Butang sentuh lebih besar dan mesra jari (Touch Target >= 46px) */
            div[data-testid="stButton"] button {
                width: 100% !important;
                min-height: 46px !important;
                font-size: 15px !important;
                border-radius: 8px !important;
                margin: 4px 0 !important;
            }

            /* Cegah Safari iOS daripada auto-zoom bila menaip (font >= 16px) */
            input, select, textarea {
                font-size: 16px !important;
            }

            /* Kad Metrik Papan Pemuka tersusun kemas */
            div[data-testid="metric-container"] {
                padding: 12px 14px !important;
                background-color: #ffffff !important;
                border: 1px solid #e0e0e0 !important;
                border-radius: 10px !important;
                box-shadow: 0 2px 5px rgba(0,0,0,0.05) !important;
                margin-bottom: 8px !important;
            }
            div[data-testid="stMetricValue"] {
                font-size: 1.35rem !important;
                word-break: break-word !important;
            }
            div[data-testid="stMetricLabel"] {
                font-size: 0.82rem !important;
                font-weight: 600 !important;
            }

            /* Menu Tab boleh dileret ke tepi (Swipeable Carousel) */
            div[data-baseweb="tab-list"] {
                overflow-x: auto !important;
                flex-wrap: nowrap !important;
                scrollbar-width: thin !important;
                gap: 5px !important;
                padding-bottom: 4px !important;
            }
            button[data-baseweb="tab"] {
                padding: 8px 14px !important;
                font-size: 13.5px !important;
                white-space: nowrap !important;
            }

            /* Jadual Data (Dataframe) boleh diskrol secara mendatar */
            div[data-testid="stDataFrame"] {
                width: 100% !important;
                overflow-x: auto !important;
            }
        }

        /* 2. Pengoptimuman untuk Tablet (769px - 1024px) */
        @media (min-width: 769px) and (max-width: 1024px) {
            .main .block-container {
                padding-left: 1.5rem !important;
                padding-right: 1.5rem !important;
            }
            div[data-testid="metric-container"] {
                padding: 10px 12px !important;
            }
            div[data-testid="stMetricValue"] {
                font-size: 1.3rem !important;
            }
        }
        </style>
    """, unsafe_allow_html=True)

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
    
    # Periksa dan buat migrasi jika kolum no_telefon atau status belum wujud
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
# HALAMAN LOG MASUK (RESPONSIF MOBILE / DESKTOP)
# =========================================================================
def login_page():
    inject_responsive_css()
    
    # -------------------------------------------------------------
    # TETAPAN WARNA
    # -------------------------------------------------------------
    WARNA_BG_LUAR = "linear-gradient(135deg, #0e2716 0%, #1E4C2B 50%, #14341E 100%)"
    WARNA_KAD_FORM = "#ffffff"
    WARNA_TEKS_LABEL = "#1a3821"  # Hijau gelap pekat di atas kad putih
    WARNA_INPUT_BG = "#f4f6f4"
    WARNA_INPUT_TEKS = "#000000"
    WARNA_BORDER_INPUT = "#c2d1c5"
    
    st.markdown(f"""
        <style>
        .stApp {{
            background: {WARNA_BG_LUAR} !important;
        }}
        .login-card-container {{
            background-color: {WARNA_KAD_FORM} !important;
            padding: 35px 30px;
            border-radius: 15px;
            box-shadow: 0px 10px 30px rgba(0, 0, 0, 0.45);
            margin-top: 25px;
        }}
        div[data-testid="stTextInput"] label,
        div[data-testid="stTextInput"] label p {{
            color: {WARNA_TEKS_LABEL} !important;
            font-size: 14px !important;
            font-weight: 700 !important;
        }}
        div[data-testid="stTextInput"] input {{
            color: {WARNA_INPUT_TEKS} !important;
            background-color: {WARNA_INPUT_BG} !important;
            border: 1.5px solid {WARNA_BORDER_INPUT} !important;
            border-radius: 8px !important;
            font-size: 16px !important;
        }}
        div[data-testid="stTextInput"] input:focus {{
            border-color: #1E4C2B !important;
            box-shadow: 0 0 8px rgba(30, 76, 43, 0.3) !important;
        }}
        div[data-testid="stButton"] button[kind="primary"] {{
            background-color: #1E4C2B !important;
            color: #ffffff !important;
            border-radius: 8px !important;
            font-weight: bold !important;
            border: none !important;
        }}
        div[data-testid="stButton"] button[kind="primary"]:hover {{
            background-color: #14341E !important;
        }}
        @media (max-width: 768px) {{
            .login-card-container {{
                padding: 24px 16px !important;
                margin-top: 10px !important;
                border-radius: 12px !important;
            }}
        }}
        </style>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.25, 1])
    with col2:
        st.markdown('<div class="login-card-container">', unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center; color: #D4AF37; margin-bottom: 0;'>🕌</h1>", unsafe_allow_html=True)
        st.markdown(f"<h3 style='text-align: center; color: #D4AF37; margin-top: 5px; font-weight: 800;'>{get_nama_surau().upper()}</h3>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #555555; font-size: 13px; margin-bottom: 20px;'>Sistem Pengurusan Kewangan Surau</p>", unsafe_allow_html=True)
        st.markdown("<hr style='border: 0; border-top: 1px solid #e0e0e0; margin-bottom: 20px;'>", unsafe_allow_html=True)
        
        username = st.text_input("Nama Pengguna (Username)", placeholder="Masukkan username...")
        password = st.text_input("Kata Laluan (Password)", type="password", placeholder="Masukkan kata laluan...")
        
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        if st.button("🔓 LOG MASUK SEKARANG", use_container_width=True, type="primary"):
            if username and password:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT id, username, password_hash, nama_penuh, no_telefon, peranan, status FROM users WHERE username = ?", (username,))
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
                        log_audit(row[3], "LOG MASUK", f"Pengguna '{username}' ({row[5]} - {u_status}) log masuk via Web.")
                        st.rerun()
                else:
                    st.error("Nama pengguna atau kata laluan tidak sah!")
            else:
                st.warning("Sila masukkan username dan kata laluan.")
                
        st.markdown("<br><p style='font-size: 11px; color: #777777; text-align: center;'>Akaun Lalai: <b>admin</b> (admin123) | <b>bendahari</b> (benda123) | <b>pengerusi</b> (pengerusi123)</p>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# =========================================================================
# HALAMAN UTAMA (MAIN APP)
# =========================================================================
def main_app():
    inject_responsive_css()
    user = st.session_state['user_info']
    nama_surau = get_nama_surau()
    
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

    if st.sidebar.button("🚪 Log Keluar", use_container_width=True, type="secondary"):
        log_audit(user["nama_penuh"], "LOG KELUAR", f"Pengguna log keluar.")
        st.session_state['logged_in'] = False
        st.session_state['user_info'] = None
        st.rerun()

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
            
        # Kad Metrik
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
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
        @media (max-width: 768px) {{
            body {{ padding: 12px !important; }}
            .cards {{ display: block !important; }}
            .card {{ width: 100% !important; margin-bottom: 10px !important; }}
            .sign {{ display: block !important; margin-top: 30px !important; }}
            .sign-box {{ width: 100% !important; margin-bottom: 25px !important; }}
        }}
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
                c1, c2, c3 = st.columns(3)
                t_tarikh = c1.date_input("Tarikh Urusniaga", datetime.now(), key="t_tarikh_input")
                t_jenis = c2.selectbox("Jenis Urusniaga", ["Penerimaan (Masuk)", "Perbelanjaan (Keluar)"], key="t_jenis_input")
                
                # Kueri kategori mengikut jenis secara reaktif dengan key berasingan
                df_kat = pd.read_sql_query("SELECT nama FROM kategori WHERE jenis = ? ORDER BY nama ASC", conn, params=(t_jenis,))
                kategori_opts = df_kat['nama'].tolist() if not df_kat.empty else ["Lain-lain"]
                t_kat = c3.selectbox("Kategori Urusniaga", kategori_opts, key=f"t_kat_input_{t_jenis}")
                
                t_butiran = st.text_input("Butiran / Keterangan Urusniaga", key="t_butiran_input")
                t_amaun = st.number_input("Amaun (RM)", min_value=0.0, step=10.0, format="%.2f", key="t_amaun_input")
                
                if st.button("➕ Simpan Rekod Urusniaga", type="primary", key="btn_simpan_trx"):
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
                e_kat = c_e3.selectbox("Kategori", e_kats, index=cat_idx, key=f"e_kat_{trx_id}_{e_jenis}")
                
                e_butiran = st.text_input("Butiran", value=e_row[3], key=f"e_butiran_{trx_id}")
                e_amaun = st.number_input("Amaun (RM)", min_value=0.01, value=float(e_row[4]), step=10.0, format="%.2f", key=f"e_amaun_{trx_id}")
                
                # BETUL:
                if ce_btn1.button("💾 Simpan Perubahan", type="primary", key=f"btn_save_edit_{trx_id}"):
                    thn_e = e_tarikh.strftime("%Y")
                    bln_e = e_tarikh.strftime("%Y-%m")
