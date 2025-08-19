import streamlit as st
import pandas as pd
from datetime import datetime
from utils.auth import require_auth, require_role
from utils.database import get_db_connection
import sqlite3

def app():
    require_auth()
    
    st.title("Permintaan Barang")
    
    # Tabs for different request functions
    tab1, tab2, tab3 = st.tabs(["Buat Permintaan", "Daftar Permintaan", "Riwayat Permintaan"])
    
    with tab1:
        create_request()
    
    with tab2:
        manage_requests()
    
    with tab3:
        request_history()

def create_request():
    st.subheader("Buat Permintaan Barang")
    
    # Get user's department
    user_dept = st.session_state['user'].get('department')
    
    if not user_dept:
        st.warning("Anda belum terdaftar di departemen manapun. Silakan hubungi administrator.")
        return
    
    # Get items from database
    conn = get_db_connection()
    items = pd.read_sql_query(
        "SELECT id, name, category, unit, current_stock FROM items ORDER BY category, name", 
        conn
    )
    conn.close()
    
    if items.empty:
        st.warning("Tidak ada item dalam database.")
        return
    
    with st.form("create_request_form"):
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
            st.write(f"Stok tersedia: **{item['current_stock']}** {item['unit']}")
            
            # Quantity
            quantity = st.number_input("Jumlah yang Diminta", min_value=1, value=1)
            
            # Priority
            priority = st.selectbox("Prioritas", ["Normal", "Mendesak"])
            
            # Notes
            notes = st.text_area("Catatan", placeholder="Masukkan alasan permintaan atau informasi tambahan")
            
            # Submit button
            submit = st.form_submit_button("Kirim Permintaan")
            
            if submit:
                conn = get_db_connection()
                cursor = conn.cursor()
                
                try:
                    # Get department ID
                    cursor.execute("SELECT id FROM departments WHERE name = ?", (user_dept,))
                    dept_id = cursor.fetchone()[0]
                    
                    # Insert request
                    cursor.execute(
                        """
                        INSERT INTO item_requests 
                        (department_id, item_id, quantity, status, requested_by, notes)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (dept_id, item_id, quantity, 'pending', st.session_state['user']['id'], notes)
                    )
                    conn.commit()
                    st.success("Permintaan barang berhasil dibuat!")
                    
                except sqlite3.Error as e:
                    st.error(f"Error: {e}")
                finally:
                    conn.close()

def manage_requests():
    st.subheader("Daftar Permintaan")
    
    # Check if user has permission to approve requests
    if st.session_state['user']['role'] not in ['admin', 'warehouse']:
        st.warning("Anda tidak memiliki akses untuk mengelola permintaan.")
        return
    
    # Get pending requests
    conn = get_db_connection()
    pending_requests = pd.read_sql_query(
        """
        SELECT r.id, r.request_date, d.name as department, i.name as item_name, 
               i.category, r.quantity, i.unit, u.full_name as requested_by,
               r.notes, i.current_stock
        FROM item_requests r
        JOIN departments d ON r.department_id = d.id
        JOIN items i ON r.item_id = i.id
        JOIN users u ON r.requested_by = u.id
        WHERE r.status = 'pending'
        ORDER BY r.request_date DESC
        """,
        conn
    )
    conn.close()
    
    if not pending_requests.empty:
        st.write("Permintaan yang Menunggu Persetujuan:")
        
        for _, request in pending_requests.iterrows():
            with st.expander(f"Permintaan #{request['id']} - {request['item_name']}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Departemen:** {request['department']}")
                    st.write(f"**Item:** {request['item_name']} ({request['category']})")
                    st.write(f"**Jumlah:** {request['quantity']} {request['unit']}")
                    st.write(f"**Stok Tersedia:** {request['current_stock']} {request['unit']}")
                
                with col2:
                    st.write(f"**Pemohon:** {request['requested_by']}")
                    st.write(f"**Tanggal:** {request['request_date']}")
                    st.write(f"**Catatan:** {request['notes']}")
                
                # Action buttons
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button(f"Setujui #{request['id']}", key=f"approve_{request['id']}"):
                        process_request(request['id'], 'approved')
                
                with col2:
                    if st.button(f"Tolak #{request['id']}", key=f"reject_{request['id']}"):
                        process_request(request['id'], 'rejected')
    else:
        st.info("Tidak ada permintaan yang menunggu persetujuan.")

def process_request(request_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Begin transaction
        cursor.execute("BEGIN TRANSACTION")
        
        # Get request details
        cursor.execute(
            """
            SELECT r.*, i.current_stock, i.name as item_name, i.unit
            FROM item_requests r
            JOIN items i ON r.item_id = i.id
            WHERE r.id = ?
            """,
            (request_id,)
        )
        request = cursor.fetchone()
        
        if status == 'approved':
            if request['quantity'] > request['current_stock']:
                st.error("Stok tidak mencukupi untuk memenuhi permintaan ini!")
                cursor.execute("ROLLBACK")
                return
            
            # Update item stock
            cursor.execute(
                "UPDATE items SET current_stock = current_stock - ? WHERE id = ?",
                (request['quantity'], request['item_id'])
            )
            
            # Record transaction
            cursor.execute(
                """
                INSERT INTO inventory_transactions 
                (item_id, transaction_type, quantity, from_department_id, to_department_id, notes, created_by)
                VALUES (?, 'issue', ?, ?, ?, ?, ?)
                """,
                (
                    request['item_id'], 
                    request['quantity'],
                    1,  # Warehouse department ID
                    request['department_id'],
                    f"Permintaan #{request_id}",
                    st.session_state['user']['id']
                )
            )
        
        # Update request status
        cursor.execute(
            """
            UPDATE item_requests 
            SET status = ?, fulfilled_date = CURRENT_TIMESTAMP, fulfilled_by = ?
            WHERE id = ?
            """,
            (status, st.session_state['user']['id'], request_id)
        )
        
        # Commit transaction
        cursor.execute("COMMIT")
        
        if status == 'approved':
            st.success(f"Permintaan #{request_id} telah disetujui dan barang telah didistribusikan.")
        else:
            st.success(f"Permintaan #{request_id} telah ditolak.")
        
        # Refresh page
        st.experimental_rerun()
        
    except sqlite3.Error as e:
        cursor.execute("ROLLBACK")
        st.error(f"Error: {e}")
    finally:
        conn.close()

def request_history():
    st.subheader("Riwayat Permintaan")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Status filter
        status_filter = st.selectbox(
            "Status",
            ["Semua", "Menunggu", "Disetujui", "Ditolak"]
        )
        
        # Map to database values
        if status_filter == "Menunggu":
            status = "pending"
        elif status_filter == "Disetujui":
            status = "approved"
        elif status_filter == "Ditolak":
            status = "rejected"
        else:
            status = None
    
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
    SELECT r.id, r.request_date, r.fulfilled_date, d.name as department,
           i.name as item_name, i.category, r.quantity, i.unit,
           u1.full_name as requested_by, u2.full_name as fulfilled_by,
           r.status, r.notes
    FROM item_requests r
    JOIN departments d ON r.department_id = d.id
    JOIN items i ON r.item_id = i.id
    JOIN users u1 ON r.requested_by = u1.id
    LEFT JOIN users u2 ON r.fulfilled_by = u2.id
    WHERE r.request_date BETWEEN ? AND ?
    """
    
    params = [start_date.strftime('%Y-%m-%d'), (end_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')]
    
    if status:
        query += " AND r.status = ?"
        params.append(status)
    
    if dept_id:
        query += " AND r.department_id = ?"
        params.append(dept_id)
    
    query += " ORDER BY r.request_date DESC"
    
    # Execute query
    conn = get_db_connection()
    requests = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    # Display results
    if not requests.empty:
        # Format status
        requests['status'] = requests['status'].map({
            'pending': 'Menunggu',
            'approved': 'Disetujui',
            'rejected': 'Ditolak'
        })
        
        # Format dates
        requests['request_date'] = pd.to_datetime(requests['request_date']).dt.strftime('%Y-%m-%d %H:%M')
        requests['fulfilled_date'] = pd.to_datetime(requests['fulfilled_date']).dt.strftime('%Y-%m-%d %H:%M')
        
        # Display as dataframe
        st.dataframe(requests)
        
        # Export option
        if st.button("Ekspor ke CSV"):
            csv = requests.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name=f"request_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    else:
        st.info("Tidak ada data permintaan untuk periode dan filter yang dipilih.")

if __name__ == "__main__":
    app()