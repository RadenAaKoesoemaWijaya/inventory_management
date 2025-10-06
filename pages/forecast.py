import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import io
import numpy as np
from utils.auth import require_auth
from utils.database import MongoDBConnection

def app():
    require_auth()
    
    st.title("Prediksi Kebutuhan Inventaris")
    
    # Get forecast data
    db = MongoDBConnection.get_database()
    items_collection = db['items']
    items_data = list(items_collection.find({}, {'_id': 1, 'name': 1, 'category': 1, 'current_stock': 1, 'min_stock': 1, 'unit': 1}).sort([('category', 1), ('name', 1)]))
    df = pd.DataFrame(items_data)
    
    # Check if forecast data exists
    forecast_collection = db['inventory_forecast']
    forecast_exists = forecast_collection.find_one() is not None
    
    if not forecast_exists:
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
                st.rerun()
            except Exception as e:
                st.error(f"Error saat menjalankan prediksi: {e}")
        
        st.stop()
    
    # Get the latest forecast date
    forecast_collection = db['inventory_forecast']
    latest_forecast_doc = forecast_collection.find_one(sort=[('forecast_date', -1)])
    latest_forecast = latest_forecast_doc['forecast_date'] if latest_forecast_doc else None
    
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

    # Get forecast data with MongoDB aggregation
    forecast_collection = db['inventory_forecast']
    items_collection = db['items']
    
    # Get latest forecast date
    latest_forecast_doc = forecast_collection.find_one(sort=[('forecast_date', -1)])
    if latest_forecast_doc:
        latest_forecast_date = latest_forecast_doc['forecast_date']
        
        # Get forecast data with item details
        forecast_data = list(forecast_collection.find({'forecast_date': latest_forecast_date}))
        
        # Get item details and merge data
        forecast_list = []
        for forecast in forecast_data:
            item = items_collection.find_one({'_id': forecast['item_id']})
            if item:
                forecast_list.append({
                    'id': str(forecast['_id']),
                    'item_id': str(forecast['item_id']),
                    'item_name': item['name'],
                    'category': item['category'],
                    'current_stock': item['current_stock'],
                    'min_stock': item['min_stock'],
                    'unit': item['unit'],
                    'annual_consumption_rate': forecast.get('annual_consumption_rate', 0),
                    'projected_annual_consumption': forecast.get('projected_annual_consumption', 0),
                    'monthly_projected_consumption': forecast.get('monthly_projected_consumption', 0),
                    'months_to_min_stock': forecast.get('months_to_min_stock', 0),
                    'reorder_date': forecast.get('reorder_date'),
                    'recommended_order_qty': forecast.get('recommended_order_qty', 0),
                    'confidence_level': forecast.get('confidence_level', 0),
                    'forecast_method': forecast.get('forecast_method', '')
                })
        
        forecast_data = pd.DataFrame(forecast_list).sort_values('months_to_min_stock')
    else:
        forecast_data = pd.DataFrame()
    
    # Check if forecast data is empty
    if forecast_data.empty:
        st.warning("Belum ada data prediksi. Silakan jalankan prediksi terlebih dahulu.")
        
        # Show items table to verify data exists
        items_data = pd.DataFrame(items_data)
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
    
    # Ensure we have valid data
    if forecast_data.empty:
        st.warning("Tidak ada data forecast yang tersedia")
        return
    
    # Clean and validate data
    forecast_display = forecast_data.copy()
    
    # Handle NaN values and infinities
    numeric_columns = ['annual_consumption_rate', 'projected_annual_consumption', 'confidence_level']
    for col in numeric_columns:
        forecast_display[col] = pd.to_numeric(forecast_display[col], errors='coerce')
        forecast_display[col] = forecast_display[col].replace([np.inf, -np.inf], np.nan)
        forecast_display[col] = forecast_display[col].fillna(0)
    
    # Format dates
    if 'reorder_date' in forecast_display.columns:
        forecast_display['reorder_date'] = pd.to_datetime(forecast_display['reorder_date'], errors='coerce')
        forecast_display['reorder_date'] = forecast_display['reorder_date'].dt.strftime('%d/%m/%Y')
    
    # Convert rates to percentages (as floats, not strings)
    forecast_display['annual_consumption_rate'] = (forecast_display['annual_consumption_rate'] * 100).round(1)
    forecast_display['projected_annual_consumption'] = (forecast_display['projected_annual_consumption'] * 100).round(1)
    forecast_display['confidence_level_pct'] = (forecast_display['confidence_level'] * 100).round(1)
    
    # Create display version with percentage strings
    forecast_display['confidence_level_str'] = forecast_display['confidence_level_pct'].astype(str) + '%'
    
    # Color coding for confidence levels
    def color_confidence(val):
        try:
            if isinstance(val, (int, float)):
                confidence = val
            elif isinstance(val, str) and val.endswith('%'):
                confidence = float(val.replace('%', ''))
            else:
                return ''
                
            if confidence >= 80:
                return 'background-color: #90EE90'  # Green
            elif confidence >= 60:
                return 'background-color: #FFFFE0'  # Yellow
            elif confidence >= 40:
                return 'background-color: #FFE4B5'  # Orange
            else:
                return 'background-color: #FFB6C1'  # Red
        except (ValueError, TypeError):
            return ''
    
    # Create display dataframe for styling
    display_cols = ['item_name', 'category', 'current_stock', 'min_stock', 'annual_consumption_rate', 
                   'projected_annual_consumption', 'months_to_min_stock', 'recommended_order_qty', 
                   'reorder_date', 'confidence_level_str']
    
    # Only include columns that exist
    available_cols = [col for col in display_cols if col in forecast_display.columns]
    display_df = forecast_display[available_cols].copy()
    
    styled_display = display_df.style.applymap(
        color_confidence, 
        subset=['confidence_level_str']
    )
    
    st.dataframe(styled_display, use_container_width=True)
    
    # Add tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["Tabel Data", "Grafik Konsumsi", "Grafik Waktu Pemesanan", "Analisis Kualitas"])
    
    with tab1:
        st.dataframe(display_df)
        
        # Export options
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Ekspor ke CSV"):
                csv = display_df.to_csv(index=False)
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
                    display_df.to_excel(writer, sheet_name='Prediksi', index=False)
                    
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
                    for col_num, value in enumerate(display_df.columns.values):
                        worksheet.write(0, col_num, value, header_format)
                        
                    # Adjust columns width
                    worksheet.set_column(0, len(display_df.columns) - 1, 15)
                
                excel_data = output.getvalue()
                
                st.download_button(
                    label="Download Excel",
                    data=excel_data,
                    file_name=f"inventory_forecast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.ms-excel"
                )
    
    with tab2:
        # Sort by projected consumption
        consumption_chart = forecast_display.sort_values('projected_annual_consumption', ascending=False).head(15)
        
        # Ensure data is clean and valid
        consumption_chart = consumption_chart.dropna(subset=['projected_annual_consumption', 'item_name'])
        if len(consumption_chart) > 0:
            fig = px.bar(
                consumption_chart, 
                x='item_name', 
                y='projected_annual_consumption',
                title='15 Item dengan Proyeksi Konsumsi Tertinggi',
                labels={'item_name': 'Nama Item', 'projected_annual_consumption': 'Proyeksi Konsumsi Tahunan (%)'},
                color='category'
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Tidak cukup data untuk menampilkan grafik proyeksi konsumsi")
        
        # Show consumption rate - handle potential empty data
        rate_data = forecast_display.sort_values('annual_consumption_rate', ascending=False).head(15)
        if len(rate_data) > 0:
            # Ensure data is clean and valid
            rate_data = rate_data.dropna(subset=['annual_consumption_rate', 'item_name'])
            if len(rate_data) > 0:
                fig2 = px.bar(
                    rate_data, 
                    x='item_name', 
                    y='annual_consumption_rate',
                    title='15 Item dengan Tingkat Konsumsi Tertinggi',
                    labels={'item_name': 'Nama Item', 'annual_consumption_rate': 'Tingkat Konsumsi Tahunan (%)'},
                    color='category'
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("Tidak cukup data yang valid untuk menampilkan grafik")
        else:
            st.info("Tidak cukup data untuk menampilkan grafik tingkat konsumsi")
    
    with tab3:
        # Sort by months to min stock
        reorder_chart = forecast_display.sort_values('months_to_min_stock').head(15)
        
        # Ensure data is clean and valid
        reorder_chart = reorder_chart.dropna(subset=['months_to_min_stock', 'item_name'])
        if len(reorder_chart) > 0:
            fig = px.bar(
                reorder_chart, 
                x='item_name', 
                y='months_to_min_stock',
                title='15 Item dengan Waktu Pemesanan Terdekat',
                labels={'item_name': 'Nama Item', 'months_to_min_stock': 'Bulan Hingga Stok Minimum'},
                color='months_to_min_stock',
                color_continuous_scale='RdYlGn'
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Show recommended order quantities
            fig2 = px.bar(
                reorder_chart, 
                x='item_name', 
                y='recommended_order_qty',
                title='Jumlah Pemesanan yang Direkomendasikan',
                labels={'item_name': 'Nama Item', 'recommended_order_qty': 'Jumlah Pemesanan'},
                color='category'
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Tidak cukup data untuk menampilkan grafik waktu pemesanan")
    
    with tab4:
        st.subheader("Analisis Kualitas Prediksi")
        
        # Ensure we have the forecast_method column
        if 'forecast_method' not in forecast_display.columns:
            forecast_display['forecast_method'] = 'Seasonal Average'
        
        # Confidence level distribution
        col1, col2 = st.columns(2)
        
        with col1:
            if len(forecast_display) > 0:
                confidence_dist = pd.cut(forecast_display['confidence_level_pct'], bins=5, labels=['Rendah', 'Cukup', 'Sedang', 'Tinggi', 'Sangat Tinggi'])
                confidence_counts = confidence_dist.value_counts()
                fig_conf = px.bar(
                    x=confidence_counts.index,
                    y=confidence_counts.values,
                    title="Distribusi Tingkat Kepercayaan Prediksi",
                    labels={'x': 'Tingkat Kepercayaan', 'y': 'Jumlah Item'}
                )
                st.plotly_chart(fig_conf, use_container_width=True)
        
        with col2:
            method_counts = forecast_display['forecast_method'].value_counts()
            if len(method_counts) > 0:
                fig_method = px.pie(
                    values=method_counts.values,
                    names=method_counts.index,
                    title="Metode Prediksi yang Digunakan"
                )
                st.plotly_chart(fig_method, use_container_width=True)
        
        # Show items with low confidence
        low_confidence = forecast_display[forecast_display['confidence_level_pct'] < 50]
        if len(low_confidence) > 0:
            st.warning("⚠️ Item dengan Prediksi Rendah (< 50% kepercayaan)")
            low_conf_cols = ['item_name', 'category', 'current_stock', 'months_to_min_stock', 'confidence_level_str', 'forecast_method']
            low_conf_available = [col for col in low_conf_cols if col in low_confidence.columns]
            low_conf_display = low_confidence[low_conf_available].copy()
            st.dataframe(low_conf_display)
        
        # Show high confidence predictions
        high_confidence = forecast_display[forecast_display['confidence_level_pct'] >= 80]
        if len(high_confidence) > 0:
            st.success("✅ Item dengan Prediksi Tinggi (≥ 80% kepercayaan)")
            high_conf_cols = ['item_name', 'category', 'current_stock', 'months_to_min_stock', 'recommended_order_qty', 'confidence_level_str']
            high_conf_available = [col for col in high_conf_cols if col in high_confidence.columns]
            high_conf_display = high_confidence[high_conf_available].copy()
            st.dataframe(high_conf_display)
        
        st.success("Data berhasil diperbarui!")
        st.rerun()

if __name__ == "__main__":
    app()