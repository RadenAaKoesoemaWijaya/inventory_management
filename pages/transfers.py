import streamlit as st
import pandas as pd
from datetime import datetime
from utils.auth import require_auth, require_role
from utils.database import get_db_connection
import sqlite3

def app():
    require_auth()
    
    st.title("Transfer Barang")
    
    # Tabs for different transfer functions
    tab1, tab2, tab3 = st.tabs(["Penerimaan Barang", "Distribusi Barang", "Riwayat Transfer"])
    
    with tab1:
        receive_items()
    
    with tab2:
        distribute_items()
    
    with tab3:
        transfer_history()

def receive_items():
    st.subheader("Penerimaan Barang")
    st.write("Gunakan form ini untuk mencatat penerimaan barang dari pemasok atau bagian pengadaan.")
    
    # Get items from database
    conn = get_db_connection()
    items = pd.read_sql_query("SELECT id, name, category, unit FROM items ORDER BY category, name", conn)
    conn.close()
    
    if items.empty:
        st.warning("Belum ada item dalam database. Silakan tambahkan item terlebih dahulu.")
        return
    
    with st.form("receive_items_form"):
        # Select item
        item_options = [f"{row['id']} - {row['name']} ({row['category']})" for _, row in items.iterrows()]
        selected_item = st.selectbox("Pilih Item", item_options)
        item_id = int(selected_item.split(" - ")[0])
        
        # Get item details
        conn = get_db_connection()
        item_details = pd.read_sql_query("SELECT * FROM items WHERE id = ?", conn, params=(item_id,))
        conn.close()
        
        if not item_details.empty:
            item = item_details.iloc[0]
            st.write(f"Stok saat ini: **{item['current_stock']}** {item['unit']}")
        
        # Quantity
        quantity = st.number_input("Jumlah", min_value=1, value=1)
        
        # Source department (usually Procurement)
        conn = get_db_connection()
        departments = pd.read_sql_query("SELECT id, name FROM departments ORDER BY name", conn)
        conn.close()
        
        dept_options = [f"{row['id']} - {row['name']}" for _, row in departments.iterrows()]
        from_dept = st.selectbox("Dari Departemen", dept_options, 
                                index=next((i for i, d in enumerate(dept_options) if "Procurement" in d or "Pengadaan" in d), 0))
        from_dept_id = int(from_dept.split(" - ")[0])
        
        # Target department (usually Warehouse)
        to_dept = st.selectbox("Ke Departemen", dept_options,
                              index=next((i for i, d in enumerate(dept_options) if "Warehouse" in d or "Gudang" in d), 0))
        to_dept_id = int(to_dept.split(" - ")[0])
        
        # Notes
        notes = st.text_area("Catatan", placeholder="Masukkan nomor PO, nomor batch, atau informasi lainnya")
        
        # Submit button
        submit = st.form_submit_button("Proses Penerimaan")
        
        if submit:
            if from_dept_id == to_dept_id:
                st.error("Departemen asal dan tujuan tidak boleh sama!")
            else:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                try:
                    # Begin transaction
                    cursor.execute("BEGIN TRANSACTION")
                    
                    # Update item stock
                    cursor.execute(
                        "UPDATE items SET current_stock = current_stock + ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (quantity, item_id)
                    )
                    
                    # Record transaction
                    cursor.execute(
                        """
                        INSERT INTO inventory_transactions 
                        (item_id, transaction_type, quantity, from_department_id, to_department_id, notes, created_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (item_id, 'receive', quantity, from_dept_id, to_dept_id, notes, st.session_state['user']['id'])
                    )
                    
                    # Commit transaction
                    cursor.execute("COMMIT")
                    st.success(f"Penerimaan {quantity} {item['unit']} {item['name']} berhasil dicatat!")
                    
                except sqlite3.Error as e:
                    cursor.execute("ROLLBACK")
                    st.error(f"Error: {e}")
                finally:
                    conn.close()

def distribute_items():
    st.subheader("Distribusi Barang")
    st.write("Gunakan form ini untuk mencatat distribusi barang dari gudang ke unit-unit.")
    
    # Get items from database
    conn = get_db_connection()
    items = pd.read_sql_query(
        "SELECT id, name, category, unit, current_stock FROM items WHERE current_stock > 0 ORDER BY category, name", 
        conn
    )
    conn.close()
    
    if items.empty:
        st.warning("Tidak ada item dengan stok tersedia. Silakan tambahkan stok terlebih dahulu.")
        return
    
    with st.form("distribute_items_form"):
        # Select item
        item_options = [f"{row['id']} - {row['name']} ({row['category']}) - Stok: {row['current_stock']} {row['unit']}" 
                        for _, row in items.iterrows()]
        selected_item = st.selectbox("Pilih Item", item_options)
        item_id = int(selected_item.split(" - ")[0])
        
        # Get item details
        conn = get_db_connection()
        item_details = pd.read_sql_query("SELECT * FROM items WHERE id = ?", conn, params=(item_id,))
        conn.close()
        
        if not item_details.empty:
            item = item_details.iloc[0]
            max_qty = item['current_stock']
            st.write(f"Stok tersedia: **{max_qty}** {item['unit']}")
            
            # Quantity
            quantity = st.number_input("Jumlah", min_value=1, max_value=int(max_qty), value=1)
            
            # Departments
            conn = get_db_connection()
            departments = pd.read_sql_query("SELECT id, name FROM departments ORDER BY name", conn)
            conn.close()
            
            dept_options = [f"{row['id']} - {row['name']}" for _, row in departments.iterrows()]
            
            # Source department (usually Warehouse)
            from_dept = st.selectbox("Dari Departemen", dept_options,
                                    index=next((i for i, d in enumerate(dept_options) if "Warehouse" in d or "Gudang" in d), 0))
            from_dept_id = int(from_dept.split(" - ")[0])
            
            # Target department
            to_dept = st.selectbox("Ke Departemen", dept_options)
            to_dept_id = int(to_dept.split(" - ")[0])
            
            # Notes
            notes = st.text_area("Catatan", placeholder="Masukkan informasi tambahan jika diperlukan")
            
            # Submit button
            submit = st.form_submit_button("Proses Distribusi")
            
            if submit:
                if from_dept_id == to_dept_id:
                    st.error("Departemen asal dan tujuan tidak boleh sama!")
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    try:
                        # Begin transaction
                        cursor.execute("BEGIN TRANSACTION")
                        
                        # Update item stock
                        cursor.execute(
                            "UPDATE items SET current_stock = current_stock - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (quantity, item_id)
                        )
                        
                        # Record transaction
                        cursor.execute(
                            """
                            INSERT INTO inventory_transactions 
                            (item_id, transaction_type, quantity, from_department_id, to_department_id, notes, created_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (item_id, 'issue', quantity, from_dept_id, to_dept_id, notes, st.session_state['user']['id'])
                        )
                        
                        # Commit transaction
                        cursor.execute("COMMIT")
                        st.success(f"Distribusi {quantity} {item['unit']} {item['name']} berhasil dicatat!")
                        
                    except sqlite3.Error as e:
                        cursor.execute("ROLLBACK")
                        st.error(f"Error: {e}")
                    finally:
                        conn.close()

def transfer_history():
    st.subheader("Riwayat Transfer")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Transaction type filter
        transaction_type = st.selectbox(
            "Jenis Transaksi",
            ["Semua", "Penerimaan", "Distribusi"]
        )
        
        # Map to database values
        if transaction_type == "Penerimaan":
            transaction_filter = "receive"
        elif transaction_type == "Distribusi":
            transaction_filter = "issue"
        else:
            transaction_filter = None
    
    with col2:
        # Department filter
        conn = get_db_connection()
        departments = pd.read_sql_query("SELECT id, name FROM departments ORDER BY name", conn)
        conn.close()
        
        dept_options = ["Semua"] + [row['name'] for _, row in departments.iterrows()]
        selected_dept = st.selectbox("Departemen", dept_options)
        
        if selected_dept != "Semua":
            dept_id = departments[departments['name'] == selected_dept]['id'].iloc[0]
        else:
            dept_id = None
    
    with col3:
        # Date range
        date_range = st.date_input(
            "Rentang Tanggal",
            value=(datetime.now().replace(day=1), datetime.now()),
            max_value=datetime.now()
        )
        
        if len(date_range) == 2:
            start_date = date_range[0]
            end_date = date_range[1]
        else:
            start_date = date_range[0]
            end_date = date_range[0]
    
    # Build query
    query = """
    SELECT t.id, t.transaction_date, i.name as item_name, i.category, 
           t.quantity, i.unit, t.transaction_type,
           d1.name as from_department, d2.name as to_department,
           u.full_name as created_by, t.notes
    FROM inventory_transactions t
    JOIN items i ON t.item_id = i.id
    JOIN users u ON t.created_by = u.id
    LEFT JOIN departments d1 ON t.from_department_id = d1.id
    LEFT JOIN departments d2 ON t.to_department_id = d2.id
    WHERE t.transaction_date BETWEEN ? AND ?
    """
    
    params = [start_date.strftime('%Y-%m-%d'), (end_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')]
    
    if transaction_filter:
        query += " AND t.transaction_type = ?"
        params.append(transaction_filter)
    
    if dept_id:
        query += " AND (t.from_department_id = ? OR t.to_department_id = ?)"
        params.extend([dept_id, dept_id])
    
    query += " ORDER BY t.transaction_date DESC"
    
    # Execute query
    conn = get_db_connection()
    transactions = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    # Display results
    if not transactions.empty:
        # Format transaction type
        transactions['transaction_type'] = transactions['transaction_type'].map({
            'receive': 'Penerimaan',
            'issue': 'Distribusi'
        })
        
        # Format date
        transactions['transaction_date'] = pd.to_datetime(transactions['transaction_date']).dt.strftime('%Y-%m-%d %H:%M')
        
        # Display as dataframe
        st.dataframe(transactions)
        
        # Export option
        if st.button("Ekspor ke CSV"):
            csv = transactions.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"transfer_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    else:
        st.info("Tidak ada data transaksi untuk periode dan filter yang dipilih.")

if __name__ == "__main__":
    app()