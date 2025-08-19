import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import io
from utils.auth import require_auth
from utils.database import get_db_connection

def app():
    require_auth()
    
    st.title("Prediksi Kebutuhan Inventaris")
    
    # Get forecast data
    conn = get_db_connection()
    df = pd.read_sql_query("""
    SELECT id, name, category, current_stock, min_stock, unit 
    FROM items ORDER BY category, name """, conn)
    
    # Check if forecast data exists
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_forecast'")
    if not cursor.fetchone():
        st.warning("Belum ada data prediksi. Silakan jalankan proses prediksi terlebih dahulu.")
        
        if st.button("Jalankan Prediksi"):
            st.info("Memulai proses prediksi...")
            try:
                # Import and run the forecast script
                import sys
                import os
                # Add scripts directory to path using relative path from current file
                current_dir = os.path.dirname(os.path.abspath(__file__))
                scripts_dir = os.path.join(current_dir, '..', 'scripts')
                sys.path.append(scripts_dir)
                import forecast_inventory
                st.success("Prediksi berhasil dijalankan!")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Error saat menjalankan prediksi: {e}")
        
        st.stop()
    
    # Get the latest forecast date
    latest_forecast = pd.read_sql_query(
        """
        SELECT MAX(forecast_date) as latest_date
        FROM inventory_forecast
        """,
        conn
    ).iloc[0]['latest_date']
    
    st.info(f"Data prediksi terakhir: {latest_forecast}")

    forecast_data = pd.read_sql_query(
        """
        SELECT 
            f.id, f.item_id, i.name as item_name, i.category, i.current_stock, 
            i.min_stock, i.unit, f.annual_consumption_rate, 
            f.projected_annual_consumption, f.monthly_projected_consumption,
            f.months_to_min_stock, f.reorder_date, f.recommended_order_qty
        FROM inventory_forecast f
        JOIN items i ON f.item_id = i.id
        WHERE f.forecast_date = (SELECT MAX(forecast_date) FROM inventory_forecast)
        ORDER BY f.months_to_min_stock
        """,
        conn
    )
    
    conn.close()
    
    # Check if forecast data is empty
    if forecast_data.empty:
        st.warning("Belum ada data prediksi. Silakan jalankan prediksi terlebih dahulu.")
        
        # Show items table to verify data exists
        items_data = pd.read_sql_query("SELECT id, name, category, current_stock, min_stock, unit FROM items", sqlite3.connect('inventory.db'))
        if not items_data.empty:
            st.info("Data item tersedia. Klik tombol 'Jalankan Prediksi' untuk membuat data prediksi.")
        else:
            st.error("Tidak ada data item. Silakan tambahkan data item terlebih dahulu.")
        
        return
    
    # Display summary
    st.subheader("Ringkasan Prediksi")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Item", len(forecast_data))
    
    with col2:
        items_to_reorder = len(forecast_data[forecast_data['months_to_min_stock'] <= 3])
        st.metric("Perlu Dipesan (3 Bulan)", items_to_reorder)
    
    with col3:
        avg_consumption = forecast_data['annual_consumption_rate'].mean() * 100
        st.metric("Rata-rata Konsumsi Tahunan", f"{avg_consumption:.1f}%")
    
    # Display items that need to be reordered soon
    st.subheader("Item yang Perlu Segera Dipesan")
    
    reorder_soon = forecast_data[forecast_data['months_to_min_stock'] <= 3].copy()
    
    if not reorder_soon.empty:
        # Format the data for display
        reorder_soon['annual_consumption_rate'] = (reorder_soon['annual_consumption_rate'] * 100).round(1).astype(str) + '%'
        
        # Display as table
        st.dataframe(
            reorder_soon[['item_name', 'category', 'current_stock', 'min_stock', 'unit', 
                         'months_to_min_stock', 'reorder_date', 'recommended_order_qty']]
        )
        
        # Visualization
        fig = px.bar(
            reorder_soon, 
            x='item_name', 
            y='months_to_min_stock',
            title='Bulan Hingga Mencapai Stok Minimum',
            labels={'item_name': 'Nama Item', 'months_to_min_stock': 'Bulan'},
            color='months_to_min_stock',
            color_continuous_scale='RdYlGn'
        )
        st.plotly_chart(fig)
    else:
        st.success("Tidak ada item yang perlu segera dipesan.")
    
    # Display all forecast data
    st.subheader("Prediksi Kebutuhan Semua Item")
    
    # Format the data for display
    forecast_display = forecast_data.copy()
    forecast_display['annual_consumption_rate'] = (forecast_display['annual_consumption_rate'] * 100).round(1).astype(str) + '%'
    
    # Add tabs for different views
    tab1, tab2, tab3 = st.tabs(["Tabel Data", "Grafik Konsumsi", "Grafik Waktu Pemesanan"])
    
    with tab1:
        st.dataframe(forecast_display)
        
        # Export options
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Ekspor ke CSV"):
                csv = forecast_display.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"inventory_forecast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("Ekspor ke Excel"):
                # Create Excel file in memory
                    # Create Excel binary data
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df.to_excel(writer, sheet_name='Sheet1', index=False)
                    output.seek(0)
                    
                    # Get the workbook and add formats
                    workbook = writer.book
                    worksheet = writer.sheets['Prediksi']
                    
                    # Add header format
                    header_format = workbook.add_format({
                        'bold': True,
                        'text_wrap': True,
                        'valign': 'top',
                        'bg_color': '#D7E4BC',
                        'border': 1
                    })
                    
                    # Write the column headers with the defined format
                    for col_num, value in enumerate(forecast_display.columns.values):
                        worksheet.write(0, col_num, value, header_format)
                        
                    # Adjust columns width
                    worksheet.set_column(0, len(forecast_display.columns) - 1, 15)
                

                    excel_data = output.getvalue()
                
                    st.download_button(
                        label="Download Excel",
                        data=excel_data,
                        file_name=f"inventory_forecast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                        mime="application/vnd.ms-excel"
                    )
    
    with tab2:
        # Sort by projected consumption
        consumption_chart = forecast_data.sort_values('projected_annual_consumption', ascending=False).head(15)
        
        fig = px.bar(
            consumption_chart, 
            x='item_name', 
            y='projected_annual_consumption',
            title='15 Item dengan Proyeksi Konsumsi Tertinggi',
            labels={'item_name': 'Nama Item', 'projected_annual_consumption': 'Proyeksi Konsumsi Tahunan'},
            color='category'
        )
        st.plotly_chart(fig)
        
        # Show consumption rate
        fig2 = px.bar(
            forecast_data.sort_values('annual_consumption_rate', ascending=False).head(15), 
            x='item_name', 
            y='annual_consumption_rate',
            title='15 Item dengan Tingkat Konsumsi Tertinggi (%)',
            labels={'item_name': 'Nama Item', 'annual_consumption_rate': 'Tingkat Konsumsi Tahunan'},
            color='category'
        )
        fig2.update_layout(yaxis_tickformat='.0%')
        st.plotly_chart(fig2)
    
    with tab3:
        # Sort by months to min stock
        reorder_chart = forecast_data.sort_values('months_to_min_stock').head(15)
        
        fig = px.bar(
            reorder_chart, 
            x='item_name', 
            y='months_to_min_stock',
            title='15 Item dengan Waktu Pemesanan Terdekat',
            labels={'item_name': 'Nama Item', 'months_to_min_stock': 'Bulan Hingga Stok Minimum'},
            color='months_to_min_stock',
            color_continuous_scale='RdYlGn'
        )
        st.plotly_chart(fig)
        
        # Show recommended order quantities
        fig2 = px.bar(
            reorder_chart, 
            x='item_name', 
            y='recommended_order_qty',
            title='Jumlah Pemesanan yang Direkomendasikan',
            labels={'item_name': 'Nama Item', 'recommended_order_qty': 'Jumlah Pemesanan'},
            color='category'
        )
        st.plotly_chart(fig2)

if __name__ == "__main__":
    app()