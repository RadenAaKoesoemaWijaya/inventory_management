import streamlit as st
import pandas as pd
from datetime import datetime
from utils.auth import require_auth, require_role
from utils.database import MongoDBConnection
from bson.objectid import ObjectId

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
    db = MongoDBConnection.get_database()
    items_collection = db.items
    items_data = list(items_collection.find().sort([("category", 1), ("name", 1)]))
    items = pd.DataFrame(items_data)
    
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
        db = MongoDBConnection.get_database()
        items_collection = db.items
        item_details = items_collection.find_one({"_id": ObjectId(item_id)})
        item = pd.Series(item_details) if item_details else pd.Series()
        
        if item_details:
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
                    db = MongoDBConnection.get_database()
                    departments_collection = db.departments
                    requests_collection = db.item_requests
                    
                    try:
                        # Get department ID
                        dept_doc = departments_collection.find_one({"name": user_dept})
                        if dept_doc:
                            dept_id = dept_doc["_id"]
                            
                            # Insert request
                            request_data = {
                                "department_id": dept_id,
                                "item_id": ObjectId(item_id),
                                "quantity": quantity,
                                "status": "pending",
                                "requested_by": ObjectId(st.session_state['user']['id']),
                                "notes": notes,
                                "request_date": datetime.now(),
                                "priority": priority.lower()
                            }
                            
                            requests_collection.insert_one(request_data)
                            st.success("Permintaan berhasil dibuat!")
                            st.rerun()
                        else:
                            st.error("Departemen tidak ditemukan")
                    except Exception as e:
                        st.error(f"Error: {e}")

def manage_requests():
    st.subheader("Daftar Permintaan")
    
    # Check if user has permission to approve requests
    if st.session_state['user']['role'] not in ['admin', 'warehouse']:
        st.warning("Anda tidak memiliki akses untuk mengelola permintaan.")
        return
    
    # Get pending requests
    db = MongoDBConnection.get_database()
    requests_collection = db.item_requests
    items_collection = db.items
    departments_collection = db.departments
    users_collection = db.users
    
    # Aggregate data for pending requests
    pipeline = [
        {"$match": {"status": "pending"}},
        {"$lookup": {
            "from": "departments",
            "localField": "department_id",
            "foreignField": "_id",
            "as": "department"
        }},
        {"$lookup": {
            "from": "items",
            "localField": "item_id",
            "foreignField": "_id",
            "as": "item"
        }},
        {"$lookup": {
            "from": "users",
            "localField": "requested_by",
            "foreignField": "_id",
            "as": "user"
        }},
        {"$unwind": "$department"},
        {"$unwind": "$item"},
        {"$unwind": "$user"},
        {"$project": {
            "id": {"$toString": "$_id"},
            "request_date": 1,
            "department": "$department.name",
            "item_name": "$item.name",
            "category": "$item.category",
            "quantity": 1,
            "unit": "$item.unit",
            "requested_by": "$user.full_name",
            "notes": 1,
            "current_stock": "$item.current_stock"
        }},
        {"$sort": {"request_date": -1}}
    ]
    
    pending_requests_data = list(requests_collection.aggregate(pipeline))
    pending_requests = pd.DataFrame(pending_requests_data)
    
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
    db = MongoDBConnection.get_database()
    requests_collection = db.item_requests
    items_collection = db.items
    transactions_collection = db.inventory_transactions
    
    try:
        # Get request details
        request_obj = requests_collection.find_one({"_id": ObjectId(request_id)})
        if not request_obj:
            st.error("Permintaan tidak ditemukan")
            return
        
        # Get item details
        item = items_collection.find_one({"_id": request_obj["item_id"]})
        if not item:
            st.error("Item tidak ditemukan")
            return
        
        if status == 'approved':
            if request_obj['quantity'] > item['current_stock']:
                st.error("Stok tidak mencukupi untuk memenuhi permintaan ini!")
                return
            
            # Update item stock
            items_collection.update_one(
                {"_id": request_obj["item_id"]},
                {"$inc": {"current_stock": -request_obj["quantity"]}}
            )
            
            # Record transaction
            transaction_data = {
                "item_id": request_obj["item_id"],
                "transaction_type": "issue",
                "quantity": request_obj["quantity"],
                "from_department_id": ObjectId("6570f8a0f1a0b8c9d0e1f2a3"),  # Warehouse department ID
                "to_department_id": request_obj["department_id"],
                "notes": f"Permintaan #{request_id}",
                "created_by": ObjectId(st.session_state['user']['id']),
                "created_at": datetime.now()
            }
            transactions_collection.insert_one(transaction_data)
        
        # Update request status
        requests_collection.update_one(
            {"_id": ObjectId(request_id)},
            {
                "$set": {
                    "status": status,
                    "fulfilled_date": datetime.now(),
                    "fulfilled_by": ObjectId(st.session_state['user']['id'])
                }
            }
        )
        
        if status == 'approved':
            st.success(f"Permintaan #{request_id} telah disetujui dan barang telah didistribusikan.")
        else:
            st.success(f"Permintaan #{request_id} telah ditolak.")
        
        # Refresh page
        st.rerun()
        
    except Exception as e:
        st.error(f"Error: {e}")

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
        db = MongoDBConnection.get_database()
        departments_collection = db.departments
        departments_data = list(departments_collection.find().sort("name", 1))
        departments = pd.DataFrame(departments_data)
        
        dept_options = ["Semua"] + [row['name'] for _, row in departments.iterrows()]
        selected_dept = st.selectbox("Departemen", dept_options)
        
        if selected_dept != "Semua":
            dept_doc = departments_collection.find_one({"name": selected_dept})
            dept_id = dept_doc["_id"] if dept_doc else None
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
    
    # Build MongoDB aggregation pipeline
    match_stage = {
        "request_date": {
            "$gte": datetime.combine(start_date, datetime.min.time()),
            "$lte": datetime.combine(end_date, datetime.max.time())
        }
    }
    
    if status:
        match_stage["status"] = status
    
    if dept_id:
        match_stage["department_id"] = dept_id
    
    pipeline = [
        {"$match": match_stage},
        {"$lookup": {
            "from": "departments",
            "localField": "department_id",
            "foreignField": "_id",
            "as": "department"
        }},
        {"$lookup": {
            "from": "items",
            "localField": "item_id",
            "foreignField": "_id",
            "as": "item"
        }},
        {"$lookup": {
            "from": "users",
            "localField": "requested_by",
            "foreignField": "_id",
            "as": "user_request"
        }},
        {"$lookup": {
            "from": "users",
            "localField": "fulfilled_by",
            "foreignField": "_id",
            "as": "user_fulfill"
        }},
        {"$unwind": "$department"},
        {"$unwind": "$item"},
        {"$unwind": {"path": "$user_request", "preserveNullAndEmptyArrays": True}},
        {"$unwind": {"path": "$user_fulfill", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "id": {"$toString": "$_id"},
            "request_date": 1,
            "fulfilled_date": 1,
            "department": "$department.name",
            "item_name": "$item.name",
            "category": "$item.category",
            "quantity": 1,
            "unit": "$item.unit",
            "requested_by": "$user_request.full_name",
            "fulfilled_by": "$user_fulfill.full_name",
            "status": 1,
            "notes": 1
        }},
        {"$sort": {"request_date": -1}}
    ]
    
    # Execute aggregation
    db = MongoDBConnection.get_database()
    requests_collection = db.item_requests
    requests_data = list(requests_collection.aggregate(pipeline))
    requests = pd.DataFrame(requests_data)
    
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