import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
from utils.auth import require_auth
from utils.database import MongoDBConnection
from utils.realtime import RealtimeDashboard, display_realtime_widget
from utils.notifications import NotificationManager, display_notification_widget, display_realtime_notification_widget
from utils.recommendations import InventoryRecommendation, display_recommendation_widget
from utils.analytics import InventoryAnalytics, display_analytics_widget
from utils.recommendations import InventoryRecommendation
from utils.helpers import get_stock_status, get_department_consumption, get_top_consumed_items

def app():
    require_auth()
    
    st.title("📊 Dashboard Inventory")
    
    # Display notification widget
    display_notification_widget()
    
    # Display recommendation widget
    display_recommendation_widget()
    
    # Display analytics widget
    display_analytics_widget()
    
    # AI Recommendations widget
    st.header("🤖 Rekomendasi AI")
    
    # Create columns for recommendations
    col_rec1, col_rec2 = st.columns(2)
    
    with col_rec1:
        # Quick recommendations
        st.subheader("📊 Ringkasan Rekomendasi")
        
        # Get recommendation data
        recommendation_engine = InventoryRecommendation()
        reorder_recs = recommendation_engine.get_reorder_recommendations()
        optimization_recs = recommendation_engine.get_optimization_recommendations()
        
        # Display metrics
        if reorder_recs:
            critical_reorder = len([r for r in reorder_recs if r['urgency'] == 'critical'])
            st.metric("Item Kritis", critical_reorder, delta=None)
        else:
            st.metric("Item Kritis", 0)
        
        if optimization_recs:
            reorder_opt = len([r for r in optimization_recs if r['recommendation_type'] == 'reorder'])
            st.metric("Perlu Dipesan (AI)", reorder_opt, delta=None)
        else:
            st.metric("Perlu Dipesan (AI)", 0)
        
        # Link to full recommendations
        if st.button("Lihat Semua Rekomendasi"):
            st.switch_page("pages/recommendations.py")
    
    with col_rec2:
        # Quick actions
        st.subheader("⚡ Tindakan Cepat")
        
        if st.button("🔄 Refresh Semua Data"):
            st.rerun()
        
        if st.button("📧 Kirim Laporan"):
            st.info("Fitur laporan akan segera tersedia!")
    
    # Real-time notification widget
    st.header("🚨 Notifikasi Real-time")
    display_realtime_notification_widget()
    
    # Add real-time section with auto-refresh
    st.header("📊 Monitoring Real-time")
    
    # Auto-refresh configuration
    if 'auto_refresh' not in st.session_state:
        st.session_state.auto_refresh = True
    
    col_refresh1, col_refresh2 = st.columns([1, 4])
    with col_refresh1:
        auto_refresh = st.checkbox("Auto-refresh", value=st.session_state.auto_refresh)
        st.session_state.auto_refresh = auto_refresh
    
    with col_refresh2:
        if auto_refresh:
            refresh_interval = st.slider("Interval refresh (detik)", 5, 60, 30)
            if auto_refresh:
                time.sleep(refresh_interval)
                st.rerun()
    
    realtime_dashboard = RealtimeDashboard()
    realtime_dashboard.run_realtime_updates()
    
    st.divider()
    
    # Get stock status
    stock_status = get_stock_status()
    
    # Display KPIs in a row
    st.subheader("Ringkasan Inventaris")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "Total Item", 
            stock_status['total_items'],
            delta=None
        )
    
    with col2:
        st.metric(
            "Stok Sehat", 
            stock_status['healthy_stock'],
            delta=None,
            delta_color="normal"
        )
    
    with col3:
        st.metric(
            "Stok Rendah", 
            stock_status['low_stock'],
            delta=None,
            delta_color="inverse"
        )
    
    with col4:
        st.metric(
            "Stok Habis", 
            stock_status['out_of_stock'],
            delta=None,
            delta_color="inverse"
        )
    
    # Create two columns for charts
    col1, col2 = st.columns(2)
    
    with col1:
        # Display low stock items
        st.subheader("Item dengan Stok Rendah")
        
        # Get low stock items from MongoDB
        db = MongoDBConnection.get_database()
        items_collection = db.items
        
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
                    "unit": 1
                }
            }
        ]
        
        low_stock_data = list(items_collection.aggregate(low_stock_pipeline))
        low_stock_items = pd.DataFrame(low_stock_data)
        
        if not low_stock_items.empty:
            # Add progress bar for stock level
            low_stock_items['stock_percentage'] = (low_stock_items['current_stock'] / low_stock_items['min_stock']) * 100
            low_stock_items['stock_percentage'] = low_stock_items['stock_percentage'].clip(upper=100)
            
            # Create a bar chart for low stock items
            fig = px.bar(
                low_stock_items,
                x='name',
                y='current_stock',
                color='stock_percentage',
                color_continuous_scale=['red', 'yellow', 'green'],
                labels={'name': 'Nama Item', 'current_stock': 'Stok Saat Ini'},
                title='Item dengan Stok Rendah'
            )
            
            # Add min stock line
            fig.add_trace(
                go.Scatter(
                    x=low_stock_items['name'],
                    y=low_stock_items['min_stock'],
                    mode='lines',
                    name='Stok Minimum',
                    line=dict(color='red', width=2, dash='dash')
                )
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Display as list with progress bars
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
    
    with col2:
        # Department consumption
        st.subheader("Konsumsi per Departemen (30 Hari Terakhir)")
        dept_consumption = get_department_consumption()
        
        if not dept_consumption.empty:
            fig = px.pie(
                dept_consumption,
                values='total_consumption',
                names='department',
                title='Konsumsi per Departemen'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Belum ada data konsumsi departemen.")
    
    # Recent transactions
    st.subheader("Transaksi Terbaru")
    
    # Get recent transactions from MongoDB
    db = MongoDBConnection.get_database()
    transactions_collection = db.inventory_transactions
    
    recent_pipeline = [
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
                "created_by": "$user_info.full_name"
            }
        },
        {"$sort": {"transaction_date": -1}},
        {"$limit": 10}
    ]
    
    recent_transactions_data = list(transactions_collection.aggregate(recent_pipeline))
    recent_transactions = pd.DataFrame(recent_transactions_data)
    
    if not recent_transactions.empty:
        # Format transaction type
        recent_transactions['transaction_type'] = recent_transactions['transaction_type'].map({
            'receive': 'Penerimaan',
            'issue': 'Distribusi'
        })
        
        # Format date
        recent_transactions['transaction_date'] = pd.to_datetime(recent_transactions['transaction_date']).dt.strftime('%Y-%m-%d %H:%M')
        
        # Display as dataframe
        st.dataframe(recent_transactions)
    else:
        st.info("Belum ada transaksi.")
    
    # Top consumed items
    st.subheader("Item Paling Banyak Digunakan (30 Hari Terakhir)")
    top_items = get_top_consumed_items(limit=10)
    
    if not top_items.empty:
        fig = px.bar(
            top_items,
            x='item_name',
            y='total_consumption',
            title='Top 10 Item Paling Banyak Digunakan',
            labels={'item_name': 'Nama Item', 'total_consumption': 'Total Konsumsi'}
        )
        st.plotly_chart(fig)
    else:
        st.info("Belum ada data konsumsi item.")
    
    # Monthly consumption trend
    st.subheader("Tren Konsumsi Bulanan")
    
    # Get monthly consumption data from MongoDB
    db = MongoDBConnection.get_database()
    transactions_collection = db.inventory_transactions
    
    # Calculate date 12 months ago
    twelve_months_ago = datetime.now() - timedelta(days=365)
    
    monthly_pipeline = [
        {
            "$match": {
                "created_at": {"$gte": twelve_months_ago}
            }
        },
        {
            "$group": {
                "_id": {
                    "$dateToString": {"format": "%Y-%m", "date": "$created_at"}
                },
                "consumption": {
                    "$sum": {
                        "$cond": [{"$eq": ["$transaction_type", "issue"]}, "$quantity", 0]
                    }
                },
                "receipt": {
                    "$sum": {
                        "$cond": [{"$eq": ["$transaction_type", "receive"]}, "$quantity", 0]
                    }
                }
            }
        },
        {"$sort": {"_id": 1}}
    ]
    
    monthly_data = list(transactions_collection.aggregate(monthly_pipeline))
    monthly_trend = pd.DataFrame(monthly_data)
    if not monthly_trend.empty:
        monthly_trend.columns = ['month', 'consumption', 'receipt']
    
    if not monthly_trend.empty and len(monthly_trend) > 1:
        # Convert to datetime for better display
        monthly_trend['month'] = pd.to_datetime(monthly_trend['month'] + '-01')
        
        # Create line chart
        fig = go.Figure()
        
        fig.add_trace(
            go.Scatter(
                x=monthly_trend['month'],
                y=monthly_trend['consumption'],
                mode='lines+markers',
                name='Konsumsi',
                line=dict(color='red', width=2)
            )
        )
        
        fig.add_trace(
            go.Scatter(
                x=monthly_trend['month'],
                y=monthly_trend['receipt'],
                mode='lines+markers',
                name='Penerimaan',
                line=dict(color='green', width=2)
            )
        )
        
        fig.update_layout(
            title='Tren Konsumsi vs Penerimaan Bulanan',
            xaxis_title='Bulan',
            yaxis_title='Jumlah Item',
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        st.plotly_chart(fig)
    else:
        st.info("Data tidak cukup untuk menampilkan tren bulanan.")

if __name__ == "__main__":
    app()