import streamlit as st
import pandas as pd
from utils.auth import login_user, logout_user, get_user_by_id, update_user
from utils.database import MongoDBConnection, get_items_low_stock, get_recent_transactions, init_db
from utils.helpers import get_stock_status, get_department_consumption, get_top_consumed_items
import os
from datetime import datetime
from bson import ObjectId

# Initialize MongoDB connection and database
@st.cache_resource
def initialize_database():
    """Initialize database connection and create collections"""
    try:
        init_db()
        return True
    except Exception as e:
        st.error(f"Failed to initialize database: {e}")
        return False

# Set page configuration
st.set_page_config(
    page_title="KALKULIS",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'authenticated' not in st.session_state:
    st.session_state['authenticated'] = False

# Initialize database
if 'db_initialized' not in st.session_state:
    st.session_state['db_initialized'] = initialize_database()

# Sidebar navigation
def sidebar_nav():
    st.sidebar.title("Navigasi KALKULIS")
    
    if st.session_state.get('authenticated', False):
        user = st.session_state['user']
        st.sidebar.write(f"Selamat datang, **{user['full_name']}**!")
        st.sidebar.write(f"Role: {user['role']}")
        st.sidebar.write(f"Departemen: {user.get('department', 'Tidak ditentukan')}")
        
        st.sidebar.divider()
        
        # Navigation menu
        menu_options = [
            "Dashboard",
            "Manajemen Inventori", 
            "Permintaan Barang",
            "Transfer Barang",
            "Laporan",
            "Forecasting",
            "Profil Pengguna",
            "Notifikasi",
            "Rekomendasi",
            "Analytics"
        ]
        
        # Filter menu based on role
        if user['role'] == 'admin':
            menu_options.append("Manajemen Pengguna")
        
        selected_page = st.sidebar.selectbox("Pilih Menu", menu_options)
        
        # Logout button
        if st.sidebar.button("Logout", use_container_width=True):
            from utils.auth import logout_user
            logout_user()
            st.rerun()
            
        return selected_page
    
    return None

# Login page
def login_page():
    st.title("Kalkulasi Kebutuhan Logistik (KALKULIS)")
    
    # Create tabs for login and registration
    login_tab, register_tab, info_tab = st.tabs(["Login", "Daftar Baru", "Tentang Aplikasi"])
    
    with login_tab:
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.image("https://img.freepik.com/free-vector/hospital-logo-design-vector-medical-cross_53876-136743.jpg", width=300)
            
        with col2:
            st.subheader("Silakan Login")
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            
            if st.button("Login"):
                if login_user(username, password):
                    st.success("Login berhasil!")
                    st.rerun()
                else:
                    st.error("Username atau password salah!")
    
    with register_tab:
        st.subheader("Daftar Pengguna Baru")
        
        # Registration form
        with st.form("registration_form"):
            full_name = st.text_input("Nama Lengkap")
            new_username = st.text_input("Username")
            new_password = st.text_input("Password", type="password")
            confirm_password = st.text_input("Konfirmasi Password", type="password")
            
            # Default role for new users
            role = st.selectbox("Role", ["staff", "manager"], index=0)
            
            # Updated department selection with new klaster options
            departments = [
                "Klaster Manajemen",
                "Klaster Ibu dan Anak", 
                "Klaster Usia Produktif dan Lanjut Usia",
                "Klaster Pencegahan Penyakit Menular",
                "Lintas Klaster - Apotek Farmasi",
                "Lintas Klaster - Laboratorium",
                "Lintas Klaster - Kesehatan Gigi",
                "Lintas Klaster - Layanan Kegawatdaruratan"
            ]
            
            department = st.selectbox("Departemen/Klaster", departments)
            
            submit_button = st.form_submit_button("Daftar")
            
            if submit_button:
                if not full_name or not new_username or not new_password:
                    st.error("Semua field harus diisi!")
                elif new_password != confirm_password:
                    st.error("Password dan konfirmasi password tidak cocok!")
                else:
                    # Register new user
                    from utils.auth import register_user
                    success, message = register_user(new_username, new_password, full_name, role, department)
                    
                    if success:
                        st.success(f"Pendaftaran berhasil! {message}")
                        st.info("Silakan login dengan akun baru Anda.")
                    else:
                        st.error(f"Pendaftaran gagal: {message}")
    
    with info_tab:
        st.subheader("Tentang KALKULIS")
        
        st.markdown("""
                
        ### Fungsi Utama:
        - **Manajemen Stok**: Monitoring stok barang medis dan non-medis secara real-time
        - **Pengadaan**: Mengelola permintaan dan pengadaan barang
        - **Distribusi**: Tracking distribusi barang antar departemen
        - **Laporan**: Menghasilkan laporan konsumsi dan stok
        - **Forecasting**: Prediksi kebutuhan stok berdasarkan histori penggunaan
        
        ### Cara Penggunaan:
        1. **Login**: Gunakan akun yang telah terdaftar atau daftar akun baru
        2. **Dashboard**: Lihat ringkasan stok dan transaksi terbaru
        3. **Manajemen Inventori**: Tambah, edit, dan hapus item inventori
        4. **Permintaan**: Buat permintaan pengadaan barang
        5. **Transfer**: Kelola transfer barang antar departemen
        6. **Laporan**: Lihat laporan konsumsi dan prediksi kebutuhan
        
        ### Role Pengguna:
        - **Admin**: Memiliki akses penuh ke semua fitur
        - **Staff**: Dapat mengelola inventori dan membuat permintaan
        - **Manager**: Dapat melihat laporan dan approve permintaan
        
        ### Fitur Tambahan:
        - Notifikasi stok rendah otomatis
        - Prediksi kebutuhan stok berdasarkan AI
        - Grafik visualisasi data konsumsi
        - Export laporan ke format Excel/PDF
        """)
        
        st.info("💡 **Tips**: Pastikan untuk selalu logout setelah selesai menggunakan aplikasi untuk menjaga keamanan data!")

# Dashboard page
def dashboard_page():
    st.title("Dashboard KALKULIS")
    
    # Get stock status
    stock_status = get_stock_status()
    
    # Display KPIs
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Item", stock_status['total_items'])
    
    with col2:
        st.metric("Stok Sehat", stock_status['healthy_stock'])
    
    with col3:
        st.metric("Stok Rendah", stock_status['low_stock'])
    
    with col4:
        st.metric("Stok Habis", stock_status['out_of_stock'])
    
    # Display low stock items
    st.subheader("Item dengan Stok Rendah")
    low_stock_items = get_items_low_stock()
    
    if not low_stock_items.empty:
        # Add progress bar for stock level
        low_stock_items['stock_percentage'] = (low_stock_items['current_stock'] / low_stock_items['min_stock']) * 100
        low_stock_items['stock_percentage'] = low_stock_items['stock_percentage'].clip(upper=100)
        
        for _, item in low_stock_items.iterrows():
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**{item['name']}** ({item['category']})")
                st.progress(int(item['stock_percentage']))
                
            with col2:
                st.write(f"Stok: **{item['current_stock']}** {item['unit']}")
                st.write(f"Min: **{item['min_stock']}** {item['unit']}")
    else:
        st.info("Tidak ada item dengan stok rendah.")
    
    # Recent transactions
    st.subheader("Transaksi Terbaru")
    transactions = get_recent_transactions(limit=5)
    
    if not transactions.empty:
        st.dataframe(transactions)
    else:
        st.info("Belum ada transaksi.")
    
    # Department consumption
    st.subheader("Konsumsi per Departemen (30 Hari Terakhir)")
    dept_consumption = get_department_consumption()
    
    if not dept_consumption.empty:
        st.bar_chart(dept_consumption.set_index('department')['total_consumption'])
    else:
        st.info("Belum ada data konsumsi departemen.")
    
    # Top consumed items
    st.subheader("Item Paling Banyak Digunakan (30 Hari Terakhir)")
    top_items = get_top_consumed_items(limit=5)
    
    if not top_items.empty:
        st.bar_chart(top_items.set_index('item_name')['total_consumption'])
    else:
        st.info("Belum ada data konsumsi item.")

# Profile page
def profile_page():
    st.title("Profil Pengguna")
    
    # Get current user info
    user_id = st.session_state['user']['id']
    username = st.session_state['user']['username']
    current_name = st.session_state['user']['full_name']
    current_role = st.session_state['user']['role']
    current_department = st.session_state['user']['department']
    
    # Display current info
    st.subheader("Informasi Profil")
    col1, col2 = st.columns(2)
    
    with col1:
        st.text_input("Username", value=username, disabled=True)
        st.text_input("Role", value=current_role.upper(), disabled=True)
    
    with col2:
        st.text_input("Departemen/Klaster", value=current_department, disabled=True)
    
    st.markdown("---")
    
    # Update profile form
    st.subheader("Update Profil")
    
    with st.form("update_profile_form"):
        new_full_name = st.text_input("Nama Lengkap Baru", value=current_name)
        
        # Updated department selection with new klaster options
        departments = [
            "Klaster Manajemen",
            "Klaster Ibu dan Anak", 
            "Klaster Usia Produktif dan Lanjut Usia",
            "Klaster Pencegahan Penyakit Menular",
            "Lintas Klaster - Apotek Farmasi",
            "Lintas Klaster - Laboratorium",
            "Lintas Klaster - Kesehatan Gigi",
            "Lintas Klaster - Layanan Kegawatdaruratan"
        ]
        
        # Find current department index
        try:
            current_dept_index = departments.index(current_department)
        except ValueError:
            current_dept_index = 0
            
        new_department = st.selectbox("Departemen/Klaster Baru", departments, index=current_dept_index)
        
        submit_profile = st.form_submit_button("Update Profil")
        
        if submit_profile:
            if new_full_name != current_name or new_department != current_department:
                try:
                    # Update user in MongoDB
                    success = update_user(user_id, {
                        "full_name": new_full_name,
                        "department": new_department
                    })
                    
                    if success:
                        # Update session state
                        st.session_state['user']['full_name'] = new_full_name
                        st.session_state['user']['department'] = new_department
                        
                        st.success("Profil berhasil diperbarui!")
                        st.rerun()
                    else:
                        st.error("Gagal memperbarui profil")
                        
                except Exception as e:
                    st.error(f"Gagal update profil: {str(e)}")
            else:
                st.info("Tidak ada perubahan yang dilakukan.")
    
    st.markdown("---")
    
    # Change password form
    st.subheader("Ganti Password")
    
    with st.form("change_password_form"):
        current_password = st.text_input("Password Lama", type="password")
        new_password = st.text_input("Password Baru", type="password")
        confirm_password = st.text_input("Konfirmasi Password Baru", type="password")
        
        submit_password = st.form_submit_button("Ganti Password")
        
        if submit_password:
            if not all([current_password, new_password, confirm_password]):
                st.error("Semua field password harus diisi!")
            elif new_password != confirm_password:
                st.error("Password baru dan konfirmasi tidak cocok!")
            elif len(new_password) < 6:
                st.error("Password minimal 6 karakter!")
            else:
                try:
                    from utils.auth import verify_password, hash_password
                    
                    # Get current user from database
                    user_data = get_user_by_id(user_id)
                    if not user_data:
                        st.error("Pengguna tidak ditemukan")
                        return
                    
                    # Verify current password
                    if verify_password(user_data['password'], current_password):
                        # Update password
                        hashed_new_password = hash_password(new_password)
                        
                        success = update_user(user_id, {
                            "password": hashed_new_password
                        })
                        
                        if success:
                            st.success("Password berhasil diubah!")
                        else:
                            st.error("Gagal mengubah password")
                    else:
                        st.error("Password lama tidak sesuai!")
                        
                except Exception as e:
                    st.error(f"Gagal mengubah password: {str(e)}")

# Wrapper functions for page modules
def inventory_page():
    from pages.inventory import app
    app()

def requests_page():
    from pages.requests import app
    app()

def transfers_page():
    from pages.transfers import app
    app()

def report_page():
    from pages.report import app
    app()

def forecast_page():
    from pages.forecast import app
    app()

# Main app function
def main():
    # Check if database is initialized
    if not st.session_state.get('db_initialized', False):
        st.error("Database initialization failed. Please check your MongoDB connection.")
        return
    
    if not st.session_state.get('authenticated', False):
        login_page()
    else:
        page = sidebar_nav()
        
        if page == "Dashboard":
            dashboard_page()
        elif page == "Profil Pengguna":
            profile_page()
        elif page == "Manajemen Inventori":
            inventory_page()
        elif page == "Permintaan Barang":
            requests_page()
        elif page == "Transfer Barang":
            transfers_page()
        elif page == "Notifikasi":
            from utils.notifications import NotificationManager
            manager = NotificationManager()
            manager.display_notification_dashboard()
        elif page == "Rekomendasi":
            from utils.recommendations import InventoryRecommendation
            recommender = InventoryRecommendation()
            recommender.display_recommendation_dashboard()
        elif page == "Analytics":
            from utils.analytics import InventoryAnalytics
            analytics = InventoryAnalytics()
            analytics.display_analytics_dashboard()
        elif page == "Laporan":
            report_page()
        elif page == "Forecasting":
            forecast_page()
        elif page == "Manajemen Pengguna":
            if st.session_state['user']['role'] == 'admin':
                st.title("Manajemen Pengguna")
                st.write("Fitur manajemen pengguna akan segera tersedia...")
                
                # You can add user management functionality here
                from utils.auth import get_all_users
                
                users = get_all_users()
                if users:
                    st.subheader("Daftar Pengguna")
                    # Convert to DataFrame for better display
                    import pandas as pd
                    users_df = pd.DataFrame(users)
                    st.dataframe(users_df[['username', 'full_name', 'role', 'department', 'is_active']])
                else:
                    st.info("Tidak ada pengguna ditemukan")
            else:
                st.error("Anda tidak memiliki akses ke halaman ini!")

if __name__ == "__main__":
    main()