import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import io
import numpy as np
from utils.auth import require_auth
from utils.database import get_db_connection
import functools
import time

@st.cache_data(ttl=300)
def get_forecast_data_cached():
    """Cache forecast data untuk performa lebih cepat"""
    conn = get_db_connection()
    try:
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
        
        # Get latest forecast date
        latest_forecast = pd.read_sql_query(
            "SELECT MAX(forecast_date) as latest_date FROM inventory_forecast",
            conn
        ).iloc[0]['latest_date']
        
        return forecast_data, latest_forecast
    finally:
        conn.close()

@st.cache_data(ttl=300)
def get_items_data_cached():
    """Cache items data untuk performa lebih cepat"""
    conn = get_db_connection()
    try:
        return pd.read_sql_query(
            "SELECT id, name, category, current_stock, min_stock, unit FROM items ORDER BY category, name",
            conn
        )
    finally:
        conn.close()

@st.cache_data(ttl=60)
def check_forecast_table_exists():
    """Cache check untuk forecast table existence"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_forecast'")
        return cursor.fetchone() is not None
    finally:
        conn.close()

def app():
    require_auth()
    
    st.title("Prediksi Kebutuhan Inventaris")
    
    # Load forecast data dengan optimasi
    try:
        with st.spinner("Memuat data prediksi..."):
            if not check_forecast_table_exists():
                st.warning("Tabel prediksi belum tersedia. Silakan jalankan proses forecasting terlebih dahulu.")
                
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
            
            # Gunakan cached data untuk performa lebih cepat
            forecast_data, latest_forecast = get_forecast_data_cached()
            
            if forecast_data.empty:
                st.warning("Data prediksi kosong. Silakan jalankan proses forecasting.")
                st.stop()
                
    except Exception as e:
        st.error(f"Error memuat data: {str(e)}")
        st.stop()

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
    
    # Check if forecast data is empty
    if forecast_data.empty:
        st.warning("Belum ada data prediksi. Silakan jalankan prediksi terlebih dahulu.")
        
        # Show items table to verify data exists
        import sqlite3
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
    
    # Optimized data validation and cleaning
    @st.cache_data(ttl=300)
    def process_forecast_data(data):
        """Process and clean forecast data dengan caching"""
        if data.empty:
            return data, data.copy()
        
        # Create working copy untuk avoid SettingWithCopyWarning
        processed_data = data.copy()
        
        # Vectorized numeric conversion (lebih cepat dari loop)
        numeric_cols = ['annual_consumption_rate', 'projected_annual_consumption', 'confidence_level']
        for col in numeric_cols:
            if col in processed_data.columns:
                processed_data[col] = pd.to_numeric(processed_data[col], errors='coerce')
        
        # Handle infinity values dengan vectorized operation
        processed_data = processed_data.replace([np.inf, -np.inf], np.nan)
        
        # Fill NaN values
        for col in numeric_cols:
            if col in processed_data.columns:
                processed_data[col] = processed_data[col].fillna(0)
        
        # Format dates secara efisien
        if 'reorder_date' in processed_data.columns:
            processed_data['reorder_date'] = pd.to_datetime(processed_data['reorder_date'], errors='coerce')
            processed_data['reorder_date'] = processed_data['reorder_date'].dt.strftime('%d/%m/%Y')
        
        # Create display columns
        display_data = processed_data.copy()
        display_data['annual_consumption_rate'] = (display_data['annual_consumption_rate'] * 100).round(1)
        display_data['projected_annual_consumption'] = (display_data['projected_annual_consumption'] * 100).round(1)
        display_data['confidence_level_pct'] = (display_data['confidence_level'] * 100).round(1)
        display_data['confidence_level_str'] = display_data['confidence_level_pct'].astype(str) + '%'
        
        return processed_data, display_data
    
    # Process data dengan caching
    forecast_display, display_df = process_forecast_data(forecast_data)
    
    # Optimized color coding dengan caching
    @st.cache_data(ttl=300)
    def get_color_styles():
        """Cache color styling untuk performa"""
        return {
            'high': 'background-color: #90EE90',
            'medium': 'background-color: #FFFFE0',
            'low': 'background-color: #FFB6C1',
            'very_low': 'background-color: #FFB6C1'
        }
    
    def color_confidence(val):
        """Fungsi color coding yang lebih efisien"""
        if pd.isna(val):
            return ''
        
        try:
            if isinstance(val, str) and val.endswith('%'):
                val = float(val.replace('%', ''))
            val = float(val)
            
            styles = get_color_styles()
            if val >= 80:
                return styles['high']
            elif val >= 60:
                return styles['medium']
            elif val >= 40:
                return styles['low']
            else:
                return styles['very_low']
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
    
    # Tab 1: Ringkasan Prediksi dengan optimasi
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Ringkasan", "📈 Analisis", "⚡ Aksi Cepat", "🔍 Detail"])
    
    @st.cache_data(ttl=300)
    def calculate_metrics(data):
        """Cache perhitungan metrics untuk performa"""
        return {
            'total_items': len(data),
            'items_need_reorder': len(data[data['months_to_min_stock'] <= 3]),
            'avg_confidence': data['confidence_level'].mean() * 100,
            'total_reorder_qty': data['recommended_order_qty'].sum()
        }
    
    @st.cache_data(ttl=300)
    def create_confidence_chart(data):
        """Cache chart creation untuk performa"""
        confidence_dist = data['confidence_level'].value_counts(bins=5)
        fig = px.bar(
            x=[f"{bin.left:.2f}-{bin.right:.2f}" for bin in confidence_dist.index],
            y=confidence_dist.values,
            labels={'x': 'Confidence Level', 'y': 'Count'},
            color=confidence_dist.values,
            color_continuous_scale="Viridis"
        )
        fig.update_layout(showlegend=False, height=300)
        return fig
    
    @st.cache_data(ttl=300)
    def create_reorder_chart(data):
        """Cache chart creation untuk performa"""
        reorder_time = data['months_to_min_stock'].value_counts(bins=5)
        fig = px.bar(
            x=[f"{bin.left:.1f}-{bin.right:.1f}" for bin in reorder_time.index],
            y=reorder_time.values,
            labels={'x': 'Months to Reorder', 'y': 'Count'},
            color=reorder_time.values,
            color_continuous_scale="Reds"
        )
        fig.update_layout(showlegend=False, height=300)
        return fig
    
    with tab1:
        st.header("📊 Ringkasan Prediksi")
        
        # Calculate metrics dengan caching
        metrics = calculate_metrics(forecast_display)
        
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Item", metrics['total_items'])
        with col2:
            st.metric("Butuh Reorder", metrics['items_need_reorder'])
        with col3:
            st.metric("Rata-rata Confidence", f"{metrics['avg_confidence']:.1f}%")
        with col4:
            st.metric("Total Reorder Qty", f"{metrics['total_reorder_qty']:.0f}")
        
        # Charts dengan caching
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader("Distribusi Tingkat Kepercayaan")
            fig_confidence = create_confidence_chart(forecast_display)
            st.plotly_chart(fig_confidence, use_container_width=True)
        
        with col_chart2:
            st.subheader("Waktu Reorder")
            fig_reorder = create_reorder_chart(forecast_display)
            st.plotly_chart(fig_reorder, use_container_width=True)
    
    with tab2:
        st.header("📈 Analisis Konsumsi")
        
        @st.cache_data(ttl=300)
        def create_consumption_charts(data):
            """Cache chart creation untuk performa"""
            charts = {}
            
            # Filter data untuk valid consumption rates
            rate_data = data[
                data['annual_consumption_rate'].notna() & 
                (data['annual_consumption_rate'] > 0)
            ]
            
            if not rate_data.empty:
                # Top 15 items by consumption rate
                top_15_rate = rate_data.nlargest(15, 'annual_consumption_rate')
                
                fig_rate = px.bar(
                    top_15_rate,
                    x='item_name',
                    y='annual_consumption_rate',
                    title="15 Item dengan Tingkat Konsumsi Tertinggi (%)",
                    labels={'annual_consumption_rate': 'Tingkat Konsumsi (%)', 'item_name': 'Nama Item'},
                    color='annual_consumption_rate',
                    color_continuous_scale="Reds"
                )
                fig_rate.update_layout(
                    xaxis_tickangle=-45,
                    height=400,
                    showlegend=False
                )
                charts['rate'] = fig_rate
            
            # Projected consumption chart
            proj_data = data[
                data['projected_annual_consumption'].notna() & 
                (data['projected_annual_consumption'] > 0)
            ]
            
            if not proj_data.empty:
                top_15_proj = proj_data.nlargest(15, 'projected_annual_consumption')
                
                fig_proj = px.bar(
                    top_15_proj,
                    x='item_name',
                    y='projected_annual_consumption',
                    title="15 Item dengan Proyeksi Konsumsi Tertinggi (%)",
                    labels={'projected_annual_consumption': 'Proyeksi Konsumsi Tahunan (%)', 'item_name': 'Nama Item'},
                    color='projected_annual_consumption',
                    color_continuous_scale="Blues"
                )
                fig_proj.update_layout(
                    xaxis_tickangle=-45,
                    height=400,
                    showlegend=False
                )
                charts['proj'] = fig_proj
            
            return charts
        
        # Create charts dengan caching
        charts = create_consumption_charts(forecast_display)
        
        if 'rate' in charts:
            st.plotly_chart(charts['rate'], use_container_width=True)
        else:
            st.info("Tidak cukup data untuk menampilkan grafik tingkat konsumsi")
        
        if 'proj' in charts:
            st.plotly_chart(charts['proj'], use_container_width=True)
        else:
            st.info("Tidak cukup data untuk menampilkan grafik proyeksi konsumsi")
    
    with tab3:
        st.header("⚡ Aksi Cepat")
        
        @st.cache_data(ttl=300)
        def create_timeline_chart(data):
            """Cache timeline chart creation"""
            timeline_data = data[data['months_to_min_stock'] <= 12].copy()
            
            if timeline_data.empty:
                return None
            
            fig = px.scatter(
                timeline_data,
                x='reorder_date',
                y='item_name',
                size='recommended_order_qty',
                color='category',
                title="Timeline Reorder Item",
                labels={'reorder_date': 'Tanggal Reorder', 'item_name': 'Nama Item'}
            )
            fig.update_layout(height=600, xaxis_tickformat='%d/%m/%Y')
            return fig
        
        @st.cache_data(ttl=300)
        def calculate_category_summary(data):
            """Cache category summary"""
            reorder_items = data[data['months_to_min_stock'] <= 3]
            if reorder_items.empty:
                return None
            
            return reorder_items.groupby('category').agg({
                'item_name': 'count',
                'recommended_order_qty': 'sum'
            }).rename(columns={'item_name': 'jumlah_item', 'recommended_order_qty': 'total_qty'})
        
        # Items needing immediate action
        urgent_items = forecast_display[forecast_display['months_to_min_stock'] <= 1]
        
        if not urgent_items.empty:
            st.warning(f"🚨 {len(urgent_items)} item perlu tindakan segera!")
            
            urgent_display = urgent_items[['item_name', 'category', 'current_stock', 'min_stock', 
                                         'months_to_min_stock', 'reorder_date', 'recommended_order_qty']].copy()
            
            # Optimized styling dengan applymap
            def highlight_urgent(val):
                if isinstance(val, (int, float)) and val <= 0.5:
                    return 'background-color: #ffcccc'
                return ''
            
            styled_urgent = urgent_display.style.applymap(highlight_urgent, subset=['months_to_min_stock'])
            st.dataframe(styled_urgent, use_container_width=True)
        else:
            st.success("✅ Tidak ada item yang membutuhkan tindakan segera")
        
        # Items needing reorder within 3 months
        reorder_items = forecast_display[forecast_display['months_to_min_stock'] <= 3]
        
        if not reorder_items.empty:
            st.info(f"📋 {len(reorder_items)} item perlu direorder dalam 3 bulan")
            
            reorder_display = reorder_items.sort_values('months_to_min_stock')[
                ['item_name', 'category', 'current_stock', 'min_stock', 'months_to_min_stock', 
                 'reorder_date', 'recommended_order_qty']
            ]
            
            st.dataframe(reorder_display, use_container_width=True)
            
            # Summary by category dengan caching
            category_summary = calculate_category_summary(forecast_display)
            if category_summary is not None:
                st.subheader("Ringkasan per Kategori")
                st.dataframe(category_summary, use_container_width=True)
        
        # Timeline visualization dengan caching
        fig_timeline = create_timeline_chart(forecast_display)
        if fig_timeline is not None:
            st.subheader("Timeline Reorder (12 bulan ke depan)")
            st.plotly_chart(fig_timeline, use_container_width=True)
    
    with tab4:
        st.header("🔍 Detail Prediksi")
        
        @st.cache_data(ttl=300)
        def apply_filters(data, category, confidence, reorder):
            """Cache filtering untuk performa"""
            filtered = data.copy()
            
            if category != "Semua":
                filtered = filtered[filtered['category'] == category]
            
            if confidence != "Semua":
                if confidence == "Tinggi (≥80%)":
                    filtered = filtered[filtered['confidence_level'] >= 0.8]
                elif confidence == "Menengah (60-79%)":
                    filtered = filtered[(filtered['confidence_level'] >= 0.6) & (filtered['confidence_level'] < 0.8)]
                else:
                    filtered = filtered[filtered['confidence_level'] < 0.6]
            
            if reorder != "Semua":
                if reorder == "≤1 Bulan":
                    filtered = filtered[filtered['months_to_min_stock'] <= 1]
                elif reorder == "1-3 Bulan":
                    filtered = filtered[(filtered['months_to_min_stock'] > 1) & (filtered['months_to_min_stock'] <= 3)]
                elif reorder == "3-6 Bulan":
                    filtered = filtered[(filtered['months_to_min_stock'] > 3) & (filtered['months_to_min_stock'] <= 6)]
                else:
                    filtered = filtered[filtered['months_to_min_stock'] > 6]
            
            return filtered
        
        @st.cache_data(ttl=300)
        def create_filter_charts(data):
            """Cache chart creation untuk filtering"""
            charts = {}
            
            if not data.empty:
                # Confidence distribution
                confidence_dist = data['confidence_level'].value_counts(bins=5)
                fig_conf = px.pie(
                    values=confidence_dist.values,
                    names=[f"{bin.left:.2f}-{bin.right:.2f}" for bin in confidence_dist.index],
                    title="Distribusi Confidence Level"
                )
                charts['confidence'] = fig_conf
                
                # Method distribution
                if 'forecast_method' in data.columns:
                    method_dist = data['forecast_method'].value_counts()
                    fig_method = px.pie(
                        values=method_dist.values,
                        names=method_dist.index,
                        title="Metode Forecast yang Digunakan"
                    )
                    charts['method'] = fig_method
            
            return charts
        
        # Filter options
        col1, col2, col3 = st.columns(3)
        
        with col1:
            selected_category = st.selectbox("Filter Kategori", ["Semua"] + list(forecast_display['category'].unique()))
        
        with col2:
            confidence_filter = st.selectbox("Filter Confidence", ["Semua", "Tinggi (≥80%)", "Menengah (60-79%)", "Rendah (<60%)"])
        
        with col3:
            reorder_filter = st.selectbox("Filter Waktu Reorder", ["Semua", "≤1 Bulan", "1-3 Bulan", "3-6 Bulan", "6+ Bulan"])
        
        # Apply filters dengan caching
        filtered_data = apply_filters(forecast_display, selected_category, confidence_filter, reorder_filter)
        
        # Display filtered data
        st.subheader(f"Data Prediksi ({len(filtered_data)} item)")
        
        if len(filtered_data) > 0:
            display_columns = ['item_name', 'category', 'current_stock', 'min_stock', 'unit', 
                             'annual_consumption_rate', 'projected_annual_consumption', 
                             'months_to_min_stock', 'reorder_date', 'recommended_order_qty', 
                             'confidence_level_str', 'forecast_method']
            
            display_filtered = filtered_data[display_columns].copy()
            display_filtered.columns = ['Nama Item', 'Kategori', 'Stok Saat Ini', 'Stok Minimum', 
                                      'Satuan', 'Tingkat Konsumsi (%)', 'Proyeksi Konsumsi (%)',
                                      'Bulan Hingga Minimum', 'Tanggal Reorder', 'Qty Rekomendasi',
                                      'Confidence', 'Metode']
            
            styled_filtered = display_filtered.style.applymap(color_confidence, subset=['Confidence'])
            st.dataframe(styled_filtered, use_container_width=True)
            
            # Charts dengan caching
            charts = create_filter_charts(filtered_data)
            
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                if 'confidence' in charts:
                    st.plotly_chart(charts['confidence'], use_container_width=True)
            
            with col_chart2:
                if 'method' in charts:
                    st.plotly_chart(charts['method'], use_container_width=True)
            
            # Optimized export
            col_exp1, col_exp2 = st.columns(2)
            
            with col_exp1:
                csv = display_filtered.to_csv(index=False)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name=f"inventory_forecast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            with col_exp2:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    display_filtered.to_excel(writer, sheet_name='Prediksi', index=False)
                    
                    workbook = writer.book
                    worksheet = writer.sheets['Prediksi']
                    
                    header_format = workbook.add_format({
                        'bold': True,
                        'text_wrap': True,
                        'valign': 'top',
                        'bg_color': '#D7E4BC',
                        'border': 1
                    })
                    
                    for col_num, value in enumerate(display_filtered.columns.values):
                        worksheet.write(0, col_num, value, header_format)
                    
                    worksheet.set_column(0, len(display_filtered.columns) - 1, 15)
                
                excel_data = output.getvalue()
                
                st.download_button(
                    label="📥 Download Excel",
                    data=excel_data,
                    file_name=f"inventory_forecast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.ms-excel"
                )
        
        else:
            st.info("Tidak ada data yang sesuai dengan filter yang dipilih")

if __name__ == "__main__":
    app()