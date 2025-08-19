import streamlit as st
import pandas as pd
from utils.auth import require_auth, require_role
from utils.database import get_db_connection
import sqlite3

def app():
    require_auth()
    
    st.title("Manajemen Inventaris")
    
    # Tabs for different inventory functions
    tab1, tab2, tab3 = st.tabs(["Daftar Inventaris", "Tambah Item", "Kategori"])
    
    with tab1:
        display_inventory()
    
    with tab2:
        add_inventory_item()
    
    with tab3:
        manage_categories()

# Move the add_inventory_item function outside of any other function
def add_inventory_item():
    st.subheader("Tambah Item Baru")
    
    with st.form("add_item_form"):
        name = st.text_input("Nama Item")
        description = st.text_area("Deskripsi")
        
        # Get categories from database for dropdown
        conn = get_db_connection()
        categories = pd.read_sql_query("SELECT DISTINCT category FROM items ORDER BY category", conn)
        conn.close()
        
        category_list = categories['category'].tolist() if not categories.empty else []
        
        col1, col2 = st.columns(2)
        
        with col1:
            category_option = st.radio("Kategori", ["Pilih dari daftar", "Tambah baru"])
            
            if category_option == "Pilih dari daftar" and category_list:
                category = st.selectbox("Pilih Kategori", category_list)
            else:
                category = st.text_input("Masukkan Kategori Baru")
        with col2:
            unit = st.text_input("Satuan (mis. pcs, box, botol)")
            min_stock = st.number_input("Stok Minimum", min_value=0, value=10)
            current_stock = st.number_input("Stok Awal", min_value=0, value=0)
        
        submit = st.form_submit_button("Tambah Item")
        
        if submit:
            if not name or not category or not unit:
                st.error("Nama, kategori, dan satuan harus diisi!")
            else:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                try:
                    cursor.execute(
                        """
                        INSERT INTO items (name, description, category, unit, min_stock, current_stock)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (name, description, category, unit, min_stock, current_stock)
                    )
                    conn.commit()
                    st.success("Item berhasil ditambahkan!")
                    
                    # Add initial stock transaction if current_stock > 0
                    if current_stock > 0:
                        item_id = cursor.lastrowid
                        cursor.execute(
                            """
                            INSERT INTO inventory_transactions 
                            (item_id, transaction_type, quantity, to_department_id, created_by, notes)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (item_id, 'receive', current_stock, 1, st.session_state['user']['id'], 'Stok awal')
                        )
                        conn.commit()
                except sqlite3.Error as e:
                    st.error(f"Error: {e}")
                finally:
                    conn.close()

def display_inventory():
    st.subheader("Daftar Inventaris")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Get categories from database
        conn = get_db_connection()
        categories = pd.read_sql_query("SELECT DISTINCT category FROM items ORDER BY category", conn)
        conn.close()
        
        category_filter = st.selectbox(
            "Filter berdasarkan Kategori",
            ["Semua"] + categories['category'].tolist()
        )
    
    with col2:
        stock_filter = st.selectbox(
            "Filter berdasarkan Status Stok",
            ["Semua", "Stok Rendah", "Stok Habis", "Stok Sehat"]
        )
    
    with col3:
        search_term = st.text_input("Cari Item", "")
    
    # Get inventory data
    conn = get_db_connection()
    query = "SELECT * FROM items"
    params = []
    
    # Apply filters
    conditions = []
    
    if category_filter != "Semua":
        conditions.append("category = ?")
        params.append(category_filter)
    
    if stock_filter == "Stok Rendah":
        conditions.append("current_stock <= min_stock AND current_stock > 0")
    elif stock_filter == "Stok Habis":
        conditions.append("current_stock = 0")
    elif stock_filter == "Stok Sehat":
        conditions.append("current_stock > min_stock")
    
    if search_term:
        conditions.append("(name LIKE ? OR description LIKE ?)")
        params.extend([f"%{search_term}%", f"%{search_term}%"])
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY category, name"
    
    inventory = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if not inventory.empty:
        # Add edit buttons and format the dataframe
        inventory['Aksi'] = None
        
        # Define columns to display
        columns_to_display = ['id', 'name', 'category', 'unit', 'current_stock', 'min_stock']
        if 'description' in inventory.columns:
            columns_to_display.append('description')
        
        # Display the dataframe
        st.dataframe(inventory[columns_to_display])
        
        # Item details and edit
        st.subheader("Detail Item")
        item_id = st.number_input("Pilih ID Item untuk diedit", min_value=1, step=1)
        
        if st.button("Tampilkan Detail"):
            conn = get_db_connection()
            item = pd.read_sql_query("SELECT * FROM items WHERE id = ?", conn, params=(item_id,))
            conn.close()
            
            if not item.empty:
                item = item.iloc[0]
                
                with st.form("edit_item_form"):
                    st.subheader(f"Edit Item: {item['name']}")
                    
                    name = st.text_input("Nama Item", item['name'])
                    description = st.text_area("Deskripsi", item.get('description', ''))
                    category = st.text_input("Kategori", item['category'])
                    unit = st.text_input("Satuan", item['unit'])
                    min_stock = st.number_input("Stok Minimum", value=int(item['min_stock']), min_value=0)
                    current_stock = st.number_input("Stok Saat Ini", value=int(item['current_stock']), min_value=0)
                    
                    submit = st.form_submit_button("Simpan Perubahan")
                    
                    if submit:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        
                        try:
                            cursor.execute(
                                """
                                UPDATE items 
                                SET name = ?, description = ?, category = ?, unit = ?, 
                                    min_stock = ?, current_stock = ?, updated_at = CURRENT_TIMESTAMP
                                WHERE id = ?
                                """,
                                (name, description, category, unit, min_stock, current_stock, item_id)
                            )
                            conn.commit()
                            st.success("Item berhasil diperbarui!")
                        except sqlite3.Error as e:
                            st.error(f"Error: {e}")
                        finally:
                            conn.close()
            else:
                st.error("Item tidak ditemukan!")
    else:
        st.info("Tidak ada item yang ditemukan.")


def manage_categories():
        st.subheader("Manajemen Kategori")
        
        # Get categories from database
        conn = get_db_connection()
        categories = pd.read_sql_query(
            """
            SELECT category, COUNT(*) as item_count 
            FROM items 
            GROUP BY category 
            ORDER BY category
            """, 
            conn
        )
        conn.close()
        
        if not categories.empty:
            st.write("Kategori yang ada:")
            for _, row in categories.iterrows():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{row['category']}**")
                with col2:
                    st.write(f"{row['item_count']} item")
        else:
            st.info("Belum ada kategori yang ditambahkan.")
        
        # Add new category
        with st.form("add_category_form"):
            st.subheader("Tambah Kategori Baru")
            new_category = st.text_input("Nama Kategori")
            submit = st.form_submit_button("Tambah Kategori")
            
            if submit and new_category:
                # Check if category already exists
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM items WHERE category = ?", (new_category,))
                count = cursor.fetchone()[0]
                
                if count > 0:
                    st.error(f"Kategori '{new_category}' sudah ada!")
                else:
                    # Add a dummy item to create the category
                    try:
                        cursor.execute(
                            """
                            INSERT INTO items (name, description, category, unit, min_stock, current_stock)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (f"Kategori {new_category}", f"Kategori baru: {new_category}", new_category, "pcs", 0, 0)
                        )
                        conn.commit()
                        st.success(f"Kategori '{new_category}' berhasil ditambahkan!")
                    except sqlite3.Error as e:
                        st.error(f"Error: {e}")
                    finally:
                        conn.close()
                        
if __name__ == "__main__":
    app()