import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from utils.auth import require_auth, require_role
from utils.database import MongoDBConnection
from utils.helpers import format_date
import io
import base64

def app():
    require_auth()
    
    st.title("Laporan Inventaris")
    
    # Tabs for different report types
    tab1, tab2, tab3, tab4 = st.tabs([
        "Ringkasan Inventaris", 
        "Analisis Konsumsi", 
        "Laporan Transaksi",
        "Laporan Kustom"
    ])
    
    with tab1:
        inventory_summary()
    
    with tab2:
        consumption_analysis()
    
    with tab3:
        transaction_report()
    
    with tab4:
        custom_report()

# In the inventory_summary function, we need to handle None values in stock_percentage
def inventory_summary():
    st.subheader("Ringkasan Inventaris")
    
    # Get inventory data from MongoDB
    db = MongoDBConnection.get_database()
    items_collection = db.items
    
    # Get category summary using MongoDB aggregation
    category_pipeline = [
        {
            "$group": {
                "_id": "$category",
                "item_count": {"$sum": 1},
                "total_stock": {"$sum": "$current_stock"},
                "low_stock_count": {
                    "$sum": {
                        "$cond": [{"$lte": ["$current_stock", "$min_stock"]}, 1, 0]
                    }
                }
            }
        },
        {
            "$project": {
                "category": "$_id",
                "item_count": 1,
                "total_stock": 1,
                "low_stock_count": 1,
                "_id": 0
            }
        },
        {"$sort": {"category": 1}}
    ]
    
    category_summary_data = list(items_collection.aggregate(category_pipeline))
    category_summary = pd.DataFrame(category_summary_data)
    
    # Get top 10 items by stock value
    top_items_cursor = items_collection.find().sort("current_stock", -1).limit(10)
    top_items_data = list(top_items_cursor)
    top_items_value = pd.DataFrame(top_items_data)
    
    # Get low stock items
    low_stock_pipeline = [
        {
            "$match": {
                "$expr": {"$lte": ["$current_stock", "$min_stock"]}
            }
        },
        {
            "$project": {
                "name": 1,
                "category": 1,
                "current_stock": 1,
                "min_stock": 1,
                "unit": 1,
                "stock_percentage": {
                    "$cond": [
                        {"$gt": ["$min_stock", 0]},
                        {"$multiply": [{"$divide": ["$current_stock", "$min_stock"]}, 100]},
                        0
                    ]
                }
            }
        },
        {"$sort": {"stock_percentage": 1}}
    ]
    
    low_stock_data = list(items_collection.aggregate(low_stock_pipeline))
    low_stock_items = pd.DataFrame(low_stock_data)
    
    # Display category summary
    st.write("### Ringkasan Kategori")
    
    if not category_summary.empty:
        # Create a bar chart for category summary
        fig = px.bar(
            category_summary, 
            x='category', 
            y='item_count',
            title='Jumlah Item per Kategori',
            labels={'category': 'Kategori', 'item_count': 'Jumlah Item'},
            color='low_stock_count',
            color_continuous_scale='Reds'
        )
        st.plotly_chart(fig)
        
        # Display as table
        st.dataframe(category_summary)
    else:
        st.info("Tidak ada data kategori.")
    
    # Display top items by stock
    st.write("### Top 10 Item dengan Stok Terbanyak")
    
    if not top_items_value.empty:
        fig = px.bar(
            top_items_value, 
            x='name', 
            y='current_stock',
            title='Top 10 Item dengan Stok Terbanyak',
            labels={'name': 'Nama Item', 'current_stock': 'Stok Saat Ini'},
            color='category'
        )
        st.plotly_chart(fig)
    else:
        st.info("Tidak ada data item.")
    
    # Display low stock items
    st.write("### Item dengan Stok Rendah")
    
    if not low_stock_items.empty:
        # Add progress bars for stock level
        for _, item in low_stock_items.iterrows():
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                st.write(f"**{item['name']}** ({item['category']})")
                # Handle None values in stock_percentage
                stock_percent = 0
                if item['stock_percentage'] is not None:
                    stock_percent = min(int(item['stock_percentage']), 100)
                st.progress(stock_percent)
                
            with col2:
                st.write(f"Stok: **{item['current_stock']}** {item['unit']}")
                
            with col3:
                st.write(f"Min: **{item['min_stock']}** {item['unit']}")
    else:
        st.success("Tidak ada item dengan stok rendah.")

def consumption_analysis():
    st.subheader("Analisis Konsumsi")
    
    # Date range selector
    col1, col2 = st.columns(2)
    
    with col1:
        period = st.selectbox(
            "Periode Analisis",
            ["30 Hari Terakhir", "3 Bulan Terakhir", "6 Bulan Terakhir", "1 Tahun Terakhir", "Kustom"]
        )
    
    with col2:
        if period == "Kustom":
            date_range = st.date_input(
                "Rentang Tanggal",
                value=(datetime.now() - timedelta(days=30), datetime.now()),
                max_value=datetime.now()
            )
            
            if len(date_range) == 2:
                start_date = date_range[0]
                end_date = date_range[1]
            else:
                start_date = date_range[0]
                end_date = date_range[0]
        else:
            if period == "30 Hari Terakhir":
                days = 30
            elif period == "3 Bulan Terakhir":
                days = 90
            elif period == "6 Bulan Terakhir":
                days = 180
            else:  # 1 Tahun Terakhir
                days = 365
                
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
    
    # Get consumption data from MongoDB
    db = MongoDBConnection.get_database()
    transactions_collection = db.inventory_transactions
    
    # Build match stage for date range and transaction type
    match_stage = {
        "transaction_type": "issue",
        "created_at": {
            "$gte": datetime.combine(start_date, datetime.min.time()),
            "$lte": datetime.combine(end_date, datetime.max.time())
        }
    }
    
    # Consumption by department
    dept_pipeline = [
        {"$match": match_stage},
        {
            "$lookup": {
                "from": "departments",
                "localField": "to_department_id",
                "foreignField": "_id",
                "as": "department_info"
            }
        },
        {"$unwind": "$department_info"},
        {
            "$group": {
                "_id": "$to_department_id",
                "department": {"$first": "$department_info.name"},
                "total_consumption": {"$sum": "$quantity"}
            }
        },
        {"$sort": {"total_consumption": -1}}
    ]
    
    dept_consumption_data = list(transactions_collection.aggregate(dept_pipeline))
    dept_consumption = pd.DataFrame(dept_consumption_data)
    
    # Consumption by item
    item_pipeline = [
        {"$match": match_stage},
        {
            "$lookup": {
                "from": "items",
                "localField": "item_id",
                "foreignField": "_id",
                "as": "item_info"
            }
        },
        {"$unwind": "$item_info"},
        {
            "$group": {
                "_id": "$item_id",
                "item_name": {"$first": "$item_info.name"},
                "category": {"$first": "$item_info.category"},
                "unit": {"$first": "$item_info.unit"},
                "total_consumption": {"$sum": "$quantity"}
            }
        },
        {"$sort": {"total_consumption": -1}},
        {"$limit": 10}
    ]
    
    item_consumption_data = list(transactions_collection.aggregate(item_pipeline))
    item_consumption = pd.DataFrame(item_consumption_data)
    
    # Monthly consumption trend
    monthly_pipeline = [
        {"$match": match_stage},
        {
            "$group": {
                "_id": {
                    "$dateToString": {"format": "%Y-%m", "date": "$created_at"}
                },
                "total_consumption": {"$sum": "$quantity"}
            }
        },
        {"$sort": {"_id": 1}}
    ]
    
    monthly_data = list(transactions_collection.aggregate(monthly_pipeline))
    monthly_trend = pd.DataFrame(monthly_data)
    if not monthly_trend.empty:
        monthly_trend.columns = ['month', 'total_consumption']
    
    # Display department consumption
    st.write("### Konsumsi per Departemen")
    
    if not dept_consumption.empty:
        fig = px.pie(
            dept_consumption, 
            values='total_consumption', 
            names='department',
            title='Distribusi Konsumsi per Departemen'
        )
        st.plotly_chart(fig)
        
        # Display as table
        st.dataframe(dept_consumption)
    else:
        st.info("Tidak ada data konsumsi departemen untuk periode yang dipilih.")
    
    # Display item consumption
    st.write("### Top 10 Item Paling Banyak Digunakan")
    
    if not item_consumption.empty:
        fig = px.bar(
            item_consumption, 
            x='item_name', 
            y='total_consumption',
            title='Top 10 Item Paling Banyak Digunakan',
            labels={'item_name': 'Nama Item', 'total_consumption': 'Total Konsumsi'},
            color='category'
        )
        st.plotly_chart(fig)
        
        # Display as table with units
        st.dataframe(item_consumption)
    else:
        st.info("Tidak ada data konsumsi item untuk periode yang dipilih.")
    
    # Display monthly trend
    st.write("### Tren Konsumsi Bulanan")
    
    if not monthly_trend.empty and len(monthly_trend) > 1:
        # Convert to datetime for better display
        monthly_trend['month'] = pd.to_datetime(monthly_trend['month'] + '-01')
        
        fig = px.line(
            monthly_trend, 
            x='month', 
            y='total_consumption',
            title='Tren Konsumsi Bulanan',
            labels={'month': 'Bulan', 'total_consumption': 'Total Konsumsi'}
        )
        st.plotly_chart(fig)
    else:
        st.info("Data tidak cukup untuk menampilkan tren bulanan.")

def transaction_report():
    st.subheader("Laporan Transaksi")
    
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
    db = MongoDBConnection.get_database()
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
                "from": "users",
                "localField": "created_by",
                "foreignField": "_id",
                "as": "user_info"
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
        
        # Summary statistics
        st.write("### Ringkasan Transaksi")
        
        total_transactions = len(transactions)
        total_items = transactions['quantity'].sum()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Total Transaksi", total_transactions)
        
        with col2:
            st.metric("Total Item", total_items)
        
        # Transaction type breakdown
        transaction_counts = transactions['transaction_type'].value_counts().reset_index()
        transaction_counts.columns = ['Jenis Transaksi', 'Jumlah']
        
        fig = px.pie(
            transaction_counts, 
            values='Jumlah', 
            names='Jenis Transaksi',
            title='Distribusi Jenis Transaksi'
        )
        st.plotly_chart(fig)
        
        # Display full data
        st.write("### Data Transaksi Lengkap")
        st.dataframe(transactions)
        
        # Export options
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Ekspor ke CSV"):
                csv = transactions.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"transaction_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("Ekspor ke Excel"):

                    df = pd.DataFrame(transactions)
                    # Membuat data Excel biner
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, sheet_name='Sheet1', index=False)
                    output.seek(0)
                        
                        # Get the workbook and add formats
                    workbook = writer.book
                    worksheet = writer.sheets['Transaksi']
                        
                        # Add header format
                    header_format = workbook.add_format({
                            'bold': True,
                            'text_wrap': True,
                            'valign': 'top',
                            'bg_color': '#D7E4BC',
                            'border': 1
                        })
                    
                    # Write the column headers with the defined format
                    for col_num, value in enumerate(transactions.columns.values):
                        worksheet.write(0, col_num, value, header_format)
                        
                    # Adjust columns width
                    worksheet.set_column(0, len(transactions.columns) - 1, 15)
                               
                    excel_data = output.getvalue()
                
                    st.download_button(
                        label="Download Excel",
                        data=excel_data,
                        file_name=f"transaction_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.ms-excel"
                    )
    else:
        st.info("Tidak ada data transaksi untuk periode dan filter yang dipilih.")
# In the custom_report function, we need to ensure excel_data is defined before it's used

def custom_report():
    st.subheader("Laporan Kustom")
    
    # Inisialisasi excel_data di awal fungsi
    excel_data = None
    
    st.write("Buat laporan kustom berdasarkan kebutuhan spesifik Anda.")

    # Get all tables and columns
    conn = get_db_connection()
    
    # Get tables
    tables = pd.read_sql_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
        conn
    )
    
    # Create dictionary to store table columns
    table_columns = {}
    
    for _, table in tables.iterrows():
        table_name = table['name']
        columns = pd.read_sql_query(f"PRAGMA table_info({table_name})", conn)
        table_columns[table_name] = columns['name'].tolist()
    
    conn.close()
    
    # Report builder interface
    st.write("### Pilih Tabel dan Kolom")
    
    selected_table = st.selectbox("Pilih Tabel", tables['name'].tolist())
    
    if selected_table:
        available_columns = table_columns[selected_table]
        selected_columns = st.multiselect("Pilih Kolom", available_columns, default=available_columns[:5])
        
        # Add filters
        st.write("### Tambahkan Filter (Opsional)")
        
        add_filter = st.checkbox("Tambahkan Filter")
        
        filter_conditions = []
        filter_params = []
        
        if add_filter:
            filter_column = st.selectbox("Kolom Filter", available_columns)
            filter_operator = st.selectbox("Operator", ["=", ">", "<", ">=", "<=", "LIKE", "IN"])
            
            if filter_operator == "IN":
                filter_value = st.text_input("Nilai (pisahkan dengan koma)")
                if filter_value:
                    values = [v.strip() for v in filter_value.split(",")]
                    placeholders = ", ".join(["?" for _ in values])
                    filter_conditions.append(f"{filter_column} IN ({placeholders})")
                    filter_params.extend(values)
            elif filter_operator == "LIKE":
                filter_value = st.text_input("Nilai")
                if filter_value:
                    filter_conditions.append(f"{filter_column} LIKE ?")
                    filter_params.append(f"%{filter_value}%")
            else:
                filter_value = st.text_input("Nilai")
                if filter_value:
                    filter_conditions.append(f"{filter_column} {filter_operator} ?")
                    filter_params.append(filter_value)
        
        # Add sorting
        st.write("### Tambahkan Pengurutan (Opsional)")
        
        add_sort = st.checkbox("Tambahkan Pengurutan")
        
        sort_clause = ""
        
        if add_sort:
            sort_column = st.selectbox("Kolom Pengurutan", available_columns)
            sort_direction = st.selectbox("Arah", ["Ascending", "Descending"])
            
            sort_dir = "ASC" if sort_direction == "Ascending" else "DESC"
            sort_clause = f"ORDER BY {sort_column} {sort_dir}"
        
        # Generate and run query
        if st.button("Jalankan Laporan"):
            if selected_columns:
                # Build query
                columns_str = ", ".join(selected_columns)
                query = f"SELECT {columns_str} FROM {selected_table}"
                
                if filter_conditions:
                    query += " WHERE " + " AND ".join(filter_conditions)
                
                if sort_clause:
                    query += f" {sort_clause}"
                
                # Execute query
                conn = get_db_connection()
                try:
                    result = pd.read_sql_query(query, conn, params=filter_params)
                    conn.close()
                    
                    if not result.empty:
                        st.write("### Hasil Laporan")
                        st.dataframe(result)
                        
                        # Export options
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if st.button("Ekspor ke CSV", key="custom_csv"):
                                csv = result.to_csv(index=False)
                                st.download_button(
                                    label="Download CSV",
                                    data=csv,
                                    file_name=f"custom_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                                    mime="text/csv"
                                )
                        
                        with col2:
                            df = pd.DataFrame(transactions)
                            # Create Excel binary data
                            output = io.BytesIO()
                            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                                df.to_excel(writer, sheet_name='Sheet1', index=False)
                            output.seek(0)
                            excel_data = output.getvalue()
                            # Sebelum menggunakan excel_data dalam download button, periksa apakah nilainya valid
                            if excel_data is not None:
                                st.download_button(
                                    label="Download Excel",
                                    data=excel_data,
                                    file_name="custom_report.xlsx",
                                    mime="application/vnd.ms-excel"
                                )
                            else:
                                st.warning("Data belum tersedia untuk diunduh. Silakan pilih dan proses data terlebih dahulu.")
                                st.download_button(
                                    label="Download Excel",
                                    data=excel_data,
                                    file_name=f"custom_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                    mime="application/vnd.ms-excel"
                                )
                    else:
                        st.info("Tidak ada data yang ditemukan untuk kriteria yang dipilih.")
                except Exception as e:
                    st.error(f"Error menjalankan query: {e}")
                    conn.close()
    
if __name__ == "__main__":
    app()