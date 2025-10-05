import streamlit as st
import pandas as pd
from utils.auth import require_auth, require_role
from utils.database import MongoDBConnection
from datetime import datetime
from bson import ObjectId

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
        db = MongoDBConnection.get_db()
        categories = db.items.distinct("category")
        
        col1, col2 = st.columns(2)
        
        with col1:
            category_option = st.radio("Kategori", ["Pilih dari daftar", "Tambah baru"])
            
            if category_option == "Pilih dari daftar" and categories:
                category = st.selectbox("Pilih Kategori", categories)
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
                try:
                    db = MongoDBConnection.get_db()
                    
                    # Insert new item
                    item_data = {
                        "name": name,
                        "description": description,
                        "category": category,
                        "unit": unit,
                        "min_stock": min_stock,
                        "current_stock": current_stock,
                        "created_at": datetime.now(),
                        "updated_at": datetime.now()
                    }
                    
                    result = db.items.insert_one(item_data)
                    item_id = result.inserted_id
                    
                    st.success("Item berhasil ditambahkan!")
                    
                    # Add initial stock transaction if current_stock > 0
                    if current_stock > 0:
                        transaction_data = {
                            "item_id": item_id,
                            "transaction_type": "receive",
                            "quantity": current_stock,
                            "from_department_id": None,
                            "to_department_id": 1,
                            "created_by": ObjectId(st.session_state['user']['id']),
                            "notes": "Stok awal",
                            "created_at": datetime.now()
                        }
                        db.inventory_transactions.insert_one(transaction_data)
                        st.success("Transaksi stok awal berhasil ditambahkan!")
                        
                except Exception as e:
                    st.error(f"Error: {e}")

def display_inventory():
    st.subheader("Daftar Inventaris")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Get categories from database
        db = MongoDBConnection.get_db()
        categories = db.items.distinct("category")
        
        category_filter = st.selectbox(
            "Filter berdasarkan Kategori",
            ["Semua"] + categories
        )
    
    with col2:
        stock_filter = st.selectbox(
            "Filter berdasarkan Status Stok",
            ["Semua", "Stok Rendah", "Stok Habis", "Stok Sehat"]
        )
    
    with col3:
        search_term = st.text_input("Cari Item", "")
    
    # Get inventory data
    db = MongoDBConnection.get_db()
    query = {}
    
    # Apply filters
    if category_filter != "Semua":
        query["category"] = category_filter
    
    if stock_filter == "Stok Rendah":
        query["$expr"] = {"$and": [{"$lte": ["$current_stock", "$min_stock"]}, {"$gt": ["$current_stock", 0]}]}
    elif stock_filter == "Stok Habis":
        query["current_stock"] = 0
    elif stock_filter == "Stok Sehat":
        query["$expr"] = {"$gt": ["$current_stock", "$min_stock"]}
    
    if search_term:
        query["$or"] = [
            {"name": {"$regex": search_term, "$options": "i"}},
            {"description": {"$regex": search_term, "$options": "i"}}
        ]
    
    # Get items from database
    items = list(db.items.find(query).sort([("category", 1), ("name", 1)]))
    
    if items:
        # Convert to DataFrame for display
        inventory_df = pd.DataFrame(items)
        
        # Select columns to display
        display_columns = ['_id', 'name', 'category', 'unit', 'current_stock', 'min_stock']
        if 'description' in inventory_df.columns:
            display_columns.append('description')
        
        # Display the dataframe
        st.dataframe(inventory_df[display_columns])
        
        # Item details and edit
        st.subheader("Detail Item")
        
        # Create a selectbox for item selection instead of number input
        item_names = [f"{item['name']} ({item['category']})" for item in items]
        selected_item_index = st.selectbox("Pilih Item untuk diedit", range(len(items)), format_func=lambda x: item_names[x])
        
        if st.button("Tampilkan Detail"):
            selected_item = items[selected_item_index]
            
            with st.form("edit_item_form"):
                st.subheader(f"Edit Item: {selected_item['name']}")
                
                name = st.text_input("Nama Item", selected_item['name'])
                description = st.text_area("Deskripsi", selected_item.get('description', ''))
                category = st.text_input("Kategori", selected_item['category'])
                unit = st.text_input("Satuan", selected_item['unit'])
                min_stock = st.number_input("Stok Minimum", value=int(selected_item['min_stock']), min_value=0)
                current_stock = st.number_input("Stok Saat Ini", value=int(selected_item['current_stock']), min_value=0)
                
                submit = st.form_submit_button("Simpan Perubahan")
                
                if submit:
                    try:
                        # Update item in database
                        update_data = {
                            "name": name,
                            "description": description,
                            "category": category,
                            "unit": unit,
                            "min_stock": min_stock,
                            "current_stock": current_stock,
                            "updated_at": datetime.now()
                        }
                        
                        result = db.items.update_one(
                            {"_id": selected_item['_id']},
                            {"$set": update_data}
                        )
                        
                        if result.modified_count > 0:
                            st.success("Item berhasil diperbarui!")
                            st.rerun()
                        else:
                            st.error("Gagal memperbarui item")
                            
                    except Exception as e:
                        st.error(f"Error: {e}")
    else:
        st.info("Tidak ada item yang ditemukan.")


def manage_categories():
    st.subheader("Manajemen Kategori")
    
    # Get categories from database
    db = MongoDBConnection.get_db()
    
    # Get category counts
    categories = list(db.items.aggregate([
        {"$group": {"_id": "$category", "item_count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]))
    
    if categories:
        st.write("Kategori yang ada:")
        for category in categories:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**{category['_id']}**")
            with col2:
                st.write(f"{category['item_count']} item")
    else:
        st.info("Belum ada kategori yang ditambahkan.")
    
    # Add new category
    with st.form("add_category_form"):
        st.subheader("Tambah Kategori Baru")
        new_category = st.text_input("Nama Kategori")
        submit = st.form_submit_button("Tambah Kategori")
        
        if submit and new_category:
            # Check if category already exists
            existing_category = db.items.find_one({"category": new_category})
            
            if existing_category:
                st.error(f"Kategori '{new_category}' sudah ada!")
            else:
                # Add a dummy item to create the category
                try:
                    item_data = {
                        "name": f"Kategori {new_category}",
                        "description": f"Kategori baru: {new_category}",
                        "category": new_category,
                        "unit": "pcs",
                        "min_stock": 0,
                        "current_stock": 0,
                        "created_at": datetime.now(),
                        "updated_at": datetime.now()
                    }
                    db.items.insert_one(item_data)
                    st.success(f"Kategori '{new_category}' berhasil ditambahkan!")
                except Exception as e:
                    st.error(f"Error: {e}")
                        
if __name__ == "__main__":
    app()