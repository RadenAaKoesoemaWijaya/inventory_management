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
    
    # Create columns for forecast info and refresh button
    col_info, col_refresh = st.columns([3, 1])
    
    with col_info:
        st.info(f"Data prediksi terakhir: {latest_forecast}")
    
    with col_refresh:
        if st.button("🔄 Jalankan Prediksi Baru", type="primary"):
            with st.spinner("Menjalankan prediksi baru..."):
                try:
                    # Import and run the forecast script
                    import sys
                    import os
                    # Add scripts directory to path using relative path from current file
                    current_dir = os.path.dirname(os.path.abspath(__file__))
                    scripts_dir = os.path.join(current_dir, '..', 'scripts')
                    sys.path.append(scripts_dir)
                    
                    # Run the forecast
                    import forecast_inventory
                    forecast_inventory.run_forecast()
                    
                    st.success("Prediksi baru berhasil dijalankan!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saat menjalankan prediksi: {e}")
                    st.info("Silakan cek koneksi database dan pastikan data transaksi tersedia.")

    forecast_data = pd.read_sql_query(
        """
        SELECT 
            f.id, f.item_id, i.name as item_name, i.category, i.current_stock, 
            i.min_stock, i.unit, f.annual_consumption_rate, 
            f.projected_annual_consumption, f.monthly_projected_consumption,
            f.months_to_min_stock, f.reorder_date, f.recommended_order_qty,
            f.confidence_level, f.forecast_method
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
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Item", len(forecast_data))
    
    with col2:
        items_to_reorder = len(forecast_data[forecast_data['months_to_min_stock'] <= 3])
        st.metric("Perlu Dipesan (3 Bulan)", items_to_reorder)
    
    with col3:
        avg_confidence = forecast_data['confidence_level'].mean() * 100
        st.metric("Rata-rata Kepercayaan", f"{avg_confidence:.0f}%")
    
    with col4:
        high_confidence = len(forecast_data[forecast_data['confidence_level'] >= 0.7])
        st.metric("Prediksi Tinggi", f"{high_confidence}")
    
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
    
    # Format display data
    forecast_display = forecast_data.copy()
    forecast_display['reorder_date'] = pd.to_datetime(forecast_display['reorder_date']).dt.strftime('%d/%m/%Y')
    forecast_display['annual_consumption_rate'] = (forecast_display['annual_consumption_rate'] * 100).round(1)
    forecast_display['projected_annual_consumption'] = (forecast_display['projected_annual_consumption'] * 100).round(1)
    forecast_display['confidence_level'] = (forecast_display['confidence_level'] * 100).round(1).astype(str) + '%'
    
    # Color coding for confidence levels
    def color_confidence(val):
        if isinstance(val, str) and val.endswith('%'):
            confidence = float(val.replace('%', ''))
            if confidence >= 80:
                return 'background-color: #90EE90'  # Green
            elif confidence >= 60:
                return 'background-color: #FFFFE0'  # Yellow
            elif confidence >= 40:
                return 'background-color: #FFE4B5'  # Orange
            else:
                return 'background-color: #FFB6C1'  # Red
        return ''
    
    styled_display = forecast_display.style.applymap(
        color_confidence, 
        subset=['confidence_level']
    )
    
    st.dataframe(styled_display, use_container_width=True)
    
    # Add tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["Tabel Data", "Grafik Konsumsi", "Grafik Waktu Pemesanan", "Analisis Kualitas"])
    
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
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    forecast_display.to_excel(writer, sheet_name='Prediksi', index=False)
                    
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
    
    with tab4:
        st.subheader("Analisis Kualitas Prediksi")
        
        # Confidence level distribution
        col1, col2 = st.columns(2)
        
        with col1:
            confidence_dist = forecast_data['confidence_level'].value_counts(bins=5)
            fig_conf = px.bar(
                x=['Rendah', 'Cukup', 'Sedang', 'Tinggi', 'Sangat Tinggi'],
                y=confidence_dist.values,
                title="Distribusi Tingkat Kepercayaan Prediksi",
                labels={'x': 'Tingkat Kepercayaan', 'y': 'Jumlah Item'}
            )
            st.plotly_chart(fig_conf)
        
        with col2:
            method_counts = forecast_data['forecast_method'].value_counts()
            fig_method = px.pie(
                values=method_counts.values,
                names=method_counts.index,
                title="Metode Prediksi yang Digunakan"
            )
            st.plotly_chart(fig_method)
        
        # Show items with low confidence
        low_confidence = forecast_data[forecast_data['confidence_level'] < 0.5]
        if not low_confidence.empty:
            st.warning("⚠️ Item dengan Prediksi Rendah (< 50% kepercayaan)")
            low_conf_display = low_confidence[['item_name', 'category', 'current_stock', 
                                            'months_to_min_stock', 'confidence_level', 
                                            'forecast_method']].copy()
            low_conf_display['confidence_level'] = (low_conf_display['confidence_level'] * 100).round(1).astype(str) + '%'
            st.dataframe(low_conf_display)
        
        # Show high confidence predictions
        high_confidence = forecast_data[forecast_data['confidence_level'] >= 0.8]
        if not high_confidence.empty:
            st.success("✅ Item dengan Prediksi Tinggi (≥ 80% kepercayaan)")
            high_conf_display = high_confidence[['item_name', 'category', 'current_stock', 
                                               'months_to_min_stock', 'recommended_order_qty',
                                               'confidence_level']].copy()
            high_conf_display['confidence_level'] = (high_conf_display['confidence_level'] * 100).round(1).astype(str) + '%'
            st.dataframe(high_conf_display)
        
        st.success("Data berhasil diperbarui!")
        st.experimental_rerun()

if __name__ == "__main__":
    app()