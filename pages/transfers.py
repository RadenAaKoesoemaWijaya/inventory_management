import streamlit as st
import pandas as pd
from datetime import datetime
from utils.auth import require_auth, require_role
from utils.database import MongoDBConnection
from bson.objectid import ObjectId

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
    db = MongoDBConnection.get_instance()
    items_collection = db.items
    items_data = list(items_collection.find().sort([("category", 1), ("name", 1)]))
    items = pd.DataFrame(items_data)
    
    if items.empty:
        st.warning("Belum ada item dalam database. Silakan tambahkan item terlebih dahulu.")
        return
    
    with st.form("receive_items_form"):
        # Select item
        item_options = [f"{row['id']} - {row['name']} ({row['category']})" for _, row in items.iterrows()]
        selected_item = st.selectbox("Pilih Item", item_options)
        item_id = int(selected_item.split(" - ")[0])
        
        # Get item details
        db = MongoDBConnection.get_instance()
        items_collection = db.items
        item_details = items_collection.find_one({"_id": ObjectId(item_id)})
        
        if item_details:
            item = pd.Series(item_details)
            st.write(f"Stok saat ini: **{item['current_stock']}** {item['unit']}")
        
        # Quantity
        quantity = st.number_input("Jumlah", min_value=1, value=1)
        
        departments_collection = db.departments
        departments_data = list(departments_collection.find().sort("name", 1))
        departments = pd.DataFrame(departments_data)
        
        dept_options = [f"{row['id']} - {row['name']}" for _, row in departments.iterrows()]
        from_dept = st.selectbox("Dari Departemen", dept_options, 
                                index=next((i for i, d in enumerate(dept_options) if "Pengadaan" in d), 0))
        from_dept_id = int(from_dept.split(" - ")[0])
        
        # Target department (usually Warehouse)
        to_dept = st.selectbox("Ke Departemen", dept_options,
                              index=next((i for i, d in enumerate(dept_options) if "Gudang" in d), 0))
        to_dept_id = int(to_dept.split(" - ")[0])
        
        # Notes
        notes = st.text_area("Catatan", placeholder="Masukkan nomor PO, nomor batch, atau informasi lainnya")
        
        # Submit button
        submit = st.form_submit_button("Proses Penerimaan")
        
        if submit:
            if from_dept_id == to_dept_id:
                st.error("Departemen asal dan tujuan tidak boleh sama!")
            else:
                db = MongoDBConnection.get_instance()
                items_collection = db.items
                transactions_collection = db.inventory_transactions
                
                try:
                    # Update item stock
                    items_collection.update_one(
                        {"_id": ObjectId(item_id)},
                        {
                            "$inc": {"current_stock": quantity},
                            "$set": {"updated_at": datetime.now()}
                        }
                    )
                    
                    # Record transaction
                    transaction_data = {
                        "item_id": ObjectId(item_id),
                        "transaction_type": "receive",
                        "quantity": quantity,
                        "from_department_id": ObjectId(from_dept_id),
                        "to_department_id": ObjectId(to_dept_id),
                        "notes": notes,
                        "created_by": ObjectId(st.session_state['user']['id']),
                        "created_at": datetime.now()
                    }
                    transactions_collection.insert_one(transaction_data)
                    
                    st.success(f"Penerimaan {quantity} {item['unit']} {item['name']} berhasil dicatat!")
                    
                except Exception as e:
                    st.error(f"Error: {e}")

def distribute_items():
    st.subheader("Distribusi Barang")
    st.write("Gunakan form ini untuk mencatat distribusi barang dari gudang ke unit-unit.")
    
    # Get items from database
    db = MongoDBConnection.get_instance()
    items_collection = db.items
    items_data = list(items_collection.find({"current_stock": {"$gt": 0}}).sort([("category", 1), ("name", 1)]))
    items = pd.DataFrame(items_data)
    
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
        db = MongoDBConnection.get_instance()
        items_collection = db.items
        item_details = items_collection.find_one({"_id": ObjectId(item_id)})
        
        if item_details:
            item = pd.Series(item_details)
            max_qty = item['current_stock']
            st.write(f"Stok tersedia: **{max_qty}** {item['unit']}")
            
            # Quantity
            quantity = st.number_input("Jumlah", min_value=1, max_value=int(max_qty), value=1)
            
            # Departments
            departments_collection = db.departments
            departments_data = list(departments_collection.find().sort("name", 1))
            departments = pd.DataFrame(departments_data)
            
            dept_options = [f"{row['id']} - {row['name']}" for _, row in departments.iterrows()]
            
            # Source department (usually Warehouse)
            from_dept = st.selectbox("Dari Departemen", dept_options,
                                    index=next((i for i, d in enumerate(dept_options) if "Gudang" in d), 0))
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
                db = MongoDBConnection.get_instance()
                items_collection = db.items
                transactions_collection = db.inventory_transactions
                
                try:
                    # Update item stock
                    items_collection.update_one(
                        {"_id": ObjectId(item_id)},
                        {
                            "$inc": {"current_stock": -quantity},
                            "$set": {"updated_at": datetime.now()}
                        }
                    )
                    
                    # Record transaction
                    transaction_data = {
                        "item_id": ObjectId(item_id),
                        "transaction_type": "issue",
                        "quantity": quantity,
                        "from_department_id": ObjectId(from_dept_id),
                        "to_department_id": ObjectId(to_dept_id),
                        "notes": notes,
                        "created_by": ObjectId(st.session_state['user']['id']),
                        "created_at": datetime.now()
                    }
                    transactions_collection.insert_one(transaction_data)
                    
                    st.success(f"Distribusi {quantity} {item['unit']} {item['name']} berhasil dicatat!")
                    
                except Exception as e:
                    st.error(f"Error: {e}")

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
        db = MongoDBConnection.get_instance()
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
    db = MongoDBConnection.get_instance()
    transactions_collection = db.inventory_transactions
    
    # Match stage with date range
    match_stage = {
        "created_at": {
            "$gte": datetime.combine(start_date, datetime.min.time()),
            "$lte": datetime.combine(end_date + pd.Timedelta(days=1), datetime.min.time())
        }
    }
    
    if transaction_filter:
        match_stage["transaction_type"] = transaction_filter
    
    if dept_id:
        match_stage["$or"] = [
            {"from_department_id": dept_id},
            {"to_department_id": dept_id}
        ]
    
    pipeline = [
        {"$match": match_stage},
        {
            "$lookup": {
                "from": "items",
                "localField": "item_id",
                "foreignField": "_id",
                "as": "item_info"
            }
        },
        {
            "$lookup": {
                "from": "departments",
                "localField": "from_department_id",
                "foreignField": "_id",
                "as": "from_dept_info"
            }
        },
        {
            "$lookup": {
                "from": "departments",
                "localField": "to_department_id",
                "foreignField": "_id",
                "as": "to_dept_info"
            }
        },
        {
            "$lookup": {
                "from": "users",
                "localField": "created_by",
                "foreignField": "_id",
                "as": "user_info"
            }
        },
        {"$unwind": "$item_info"},
        {"$unwind": "$user_info"},
        {
            "$project": {
                "id": {"$toString": "$_id"},
                "transaction_date": "$created_at",
                "item_name": "$item_info.name",
                "category": "$item_info.category",
                "quantity": 1,
                "unit": "$item_info.unit",
                "transaction_type": 1,
                "from_department": {"$arrayElemAt": ["$from_dept_info.name", 0]},
                "to_department": {"$arrayElemAt": ["$to_dept_info.name", 0]},
                "created_by": "$user_info.full_name",
                "notes": 1
            }
        },
        {"$sort": {"transaction_date": -1}}
    ]
    
    transactions_data = list(transactions_collection.aggregate(pipeline))
    transactions = pd.DataFrame(transactions_data)
    
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