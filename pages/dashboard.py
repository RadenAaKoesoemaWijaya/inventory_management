import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from utils.auth import require_auth, require_role
from utils.database import get_db_connection, get_items_low_stock
from utils.helpers import get_stock_status, get_department_consumption, get_top_consumed_items

def app():
    require_auth()
    
    st.title("Dashboard SIMASYANTO")
    
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
        low_stock_items = get_items_low_stock()
        
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
    
    # Get recent transactions
    conn = get_db_connection()
    recent_transactions = pd.read_sql_query(
        """
        SELECT t.id, t.transaction_date, i.name as item_name, i.category, 
               t.quantity, i.unit, t.transaction_type,
               d1.name as from_department, d2.name as to_department,
               u.full_name as created_by
        FROM inventory_transactions t
        JOIN items i ON t.item_id = i.id
        JOIN users u ON t.created_by = u.id
        LEFT JOIN departments d1 ON t.from_department_id = d1.id
        LEFT JOIN departments d2 ON t.to_department_id = d2.id
        ORDER BY t.transaction_date DESC
        LIMIT 10
        """,
        conn
    )
    conn.close()
    
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
    
    # Get monthly consumption data
    conn = get_db_connection()
    monthly_trend = pd.read_sql_query(
        """
        SELECT strftime('%Y-%m', t.transaction_date) as month, 
               SUM(CASE WHEN t.transaction_type = 'issue' THEN t.quantity ELSE 0 END) as consumption,
               SUM(CASE WHEN t.transaction_type = 'receive' THEN t.quantity ELSE 0 END) as receipt
        FROM inventory_transactions t
        WHERE t.transaction_date >= date('now', '-12 months')
        GROUP BY strftime('%Y-%m', t.transaction_date)
        ORDER BY month
        """,
        conn
    )
    conn.close()
    
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