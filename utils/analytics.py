import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from utils.database import MongoDBConnection
from typing import Dict, List, Optional
import numpy as np

class InventoryAnalytics:
    def __init__(self):
        self.db = MongoDBConnection()
    
    def get_inventory_turnover(self, days: int = 30) -> Dict:
        """Calculate inventory turnover rate"""
        try:
            items_collection = self.db.get_collection('items')
            transactions_collection = self.db.get_collection('inventory_transactions')
            
            start_date = datetime.now() - timedelta(days=days)
            
            # Get all items
            items = list(items_collection.find({}))
            
            turnover_data = []
            
            for item in items:
                # Get consumption data
                consumption_data = list(transactions_collection.find({
                    'item_id': item['_id'],
                    'transaction_type': 'issue',
                    'transaction_date': {'$gte': start_date}
                }))
                
                total_consumed = sum(t['quantity'] for t in consumption_data)
                avg_stock = (item['current_stock'] + item.get('opening_stock', item['current_stock'])) / 2
                
                # Calculate turnover rate
                if avg_stock > 0:
                    turnover_rate = (total_consumed / avg_stock) * (365 / days)
                else:
                    turnover_rate = 0
                
                turnover_data.append({
                    'item_name': item['name'],
                    'category': item['category'],
                    'turnover_rate': turnover_rate,
                    'total_consumed': total_consumed,
                    'avg_stock': avg_stock,
                    'current_stock': item['current_stock']
                })
            
            return {
                'turnover_data': turnover_data,
                'avg_turnover': np.mean([d['turnover_rate'] for d in turnover_data]) if turnover_data else 0,
                'total_items': len(turnover_data)
            }
            
        except Exception as e:
            print(f"Error calculating turnover: {e}")
            return {'turnover_data': [], 'avg_turnover': 0, 'total_items': 0}
    
    def get_stock_movement_analysis(self, days: int = 30) -> Dict:
        """Analyze stock movement patterns"""
        try:
            transactions_collection = self.db.get_collection('inventory_transactions')
            items_collection = self.db.get_collection('items')
            
            start_date = datetime.now() - timedelta(days=days)
            
            # Get all transactions in the period
            transactions = list(transactions_collection.find({
                'transaction_date': {'$gte': start_date}
            }))
            
            # Group by transaction type
            movement_summary = {}
            
            for transaction in transactions:
                transaction_type = transaction['transaction_type']
                quantity = transaction['quantity']
                
                if transaction_type not in movement_summary:
                    movement_summary[transaction_type] = {
                        'total_transactions': 0,
                        'total_quantity': 0,
                        'avg_quantity': 0
                    }
                
                movement_summary[transaction_type]['total_transactions'] += 1
                movement_summary[transaction_type]['total_quantity'] += quantity
            
            # Calculate averages
            for trans_type in movement_summary:
                summary = movement_summary[trans_type]
                if summary['total_transactions'] > 0:
                    summary['avg_quantity'] = summary['total_quantity'] / summary['total_transactions']
            
            # Daily movement trend
            daily_movement = {}
            for transaction in transactions:
                date_str = transaction['transaction_date'].strftime('%Y-%m-%d')
                trans_type = transaction['transaction_type']
                quantity = transaction['quantity']
                
                if date_str not in daily_movement:
                    daily_movement[date_str] = {}
                
                if trans_type not in daily_movement[date_str]:
                    daily_movement[date_str][trans_type] = 0
                
                daily_movement[date_str][trans_type] += quantity
            
            return {
                'movement_summary': movement_summary,
                'daily_movement': daily_movement,
                'total_transactions': len(transactions)
            }
            
        except Exception as e:
            print(f"Error analyzing stock movement: {e}")
            return {'movement_summary': {}, 'daily_movement': {}, 'total_transactions': 0}
    
    def get_department_efficiency_analysis(self, days: int = 30) -> Dict:
        """Analyze department consumption efficiency"""
        try:
            departments_collection = self.db.get_collection('departments')
            transactions_collection = self.db.get_collection('inventory_transactions')
            
            start_date = datetime.now() - timedelta(days=days)
            
            # Get all departments
            departments = list(departments_collection.find({}))
            
            department_analysis = {}
            
            for dept in departments:
                # Get department transactions
                dept_transactions = list(transactions_collection.find({
                    'department_id': dept['_id'],
                    'transaction_date': {'$gte': start_date}
                }))
                
                if dept_transactions:
                    # Calculate metrics
                    total_consumed = sum(t['quantity'] for t in dept_transactions if t['transaction_type'] == 'issue')
                    total_received = sum(t['quantity'] for t in dept_transactions if t['transaction_type'] == 'receipt')
                    
                    # Calculate efficiency (consumed vs received ratio)
                    if total_received > 0:
                        efficiency_ratio = total_consumed / total_received
                    else:
                        efficiency_ratio = 0
                    
                    # Calculate daily average consumption
                    daily_avg = total_consumed / days
                    
                    department_analysis[dept['name']] = {
                        'total_consumed': total_consumed,
                        'total_received': total_received,
                        'efficiency_ratio': efficiency_ratio,
                        'daily_avg_consumption': daily_avg,
                        'transaction_count': len(dept_transactions)
                    }
            
            return {
                'department_analysis': department_analysis,
                'avg_efficiency': np.mean([d['efficiency_ratio'] for d in department_analysis.values()]) if department_analysis else 0
            }
            
        except Exception as e:
            print(f"Error analyzing department efficiency: {e}")
            return {'department_analysis': {}, 'avg_efficiency': 0}
    
    def get_inventory_health_score(self) -> Dict:
        """Calculate overall inventory health score"""
        try:
            items_collection = self.db.get_collection('items')
            transactions_collection = self.db.get_collection('inventory_transactions')
            
            # Get all items
            items = list(items_collection.find({}))
            total_items = len(items)
            
            if total_items == 0:
                return {'score': 0, 'factors': {}}
            
            # Calculate health factors
            factors = {}
            
            # 1. Stock availability factor
            in_stock_items = len([item for item in items if item['current_stock'] > 0])
            factors['stock_availability'] = (in_stock_items / total_items) * 100
            
            # 2. Stock level factor (items with adequate stock)
            adequate_stock_items = len([item for item in items if item['current_stock'] > item['min_stock']])
            factors['stock_adequacy'] = (adequate_stock_items / total_items) * 100
            
            # 3. Turnover factor
            turnover_data = self.get_inventory_turnover(30)
            avg_turnover = turnover_data['avg_turnover']
            # Normalize turnover (ideal is 4-6 times per year)
            if avg_turnover >= 4 and avg_turnover <= 6:
                factors['turnover'] = 100
            elif avg_turnover < 4:
                factors['turnover'] = (avg_turnover / 4) * 100
            else:
                factors['turnover'] = max(0, 100 - ((avg_turnover - 6) * 10))
            
            # 4. Movement factor (recent activity)
            thirty_days_ago = datetime.now() - timedelta(days=30)
            recent_transactions = transactions_collection.count_documents({
                'transaction_date': {'$gte': thirty_days_ago}
            })
            
            # Assume 30 transactions per month is good
            factors['movement'] = min(100, (recent_transactions / 30) * 100)
            
            # Calculate weighted score
            weights = {
                'stock_availability': 0.25,
                'stock_adequacy': 0.25,
                'turnover': 0.30,
                'movement': 0.20
            }
            
            score = sum(factors[factor] * weights[factor] for factor in weights)
            
            return {
                'score': score,
                'factors': factors,
                'total_items': total_items
            }
            
        except Exception as e:
            print(f"Error calculating health score: {e}")
            return {'score': 0, 'factors': {}, 'total_items': 0}
    
    def display_analytics_dashboard(self):
        """Display comprehensive analytics dashboard"""
        st.header("📊 Analytics Dashboard")
        
        # Date range selector
        col1, col2 = st.columns(2)
        with col1:
            days_range = st.selectbox("Periode Analisis:", [7, 30, 90, 180], index=1)
        
        with col2:
            st.write("")  # Spacer
        
        # Create tabs for different analytics
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Ringkasan Kesehatan",
            "Perputaran Inventory", 
            "Analisis Pergerakan",
            "Efisiensi Departemen",
            "Tren & Prediksi"
        ])
        
        with tab1:
            self.display_health_summary()
        
        with tab2:
            self.display_turnover_analysis(days_range)
        
        with tab3:
            self.display_movement_analysis(days_range)
        
        with tab4:
            self.display_department_efficiency(days_range)
        
        with tab5:
            self.display_trends_and_predictions(days_range)
    
    def display_health_summary(self):
        """Display inventory health summary"""
        st.subheader("🏥 Ringkasan Kesehatan Inventory")
        
        health_data = self.get_inventory_health_score()
        
        # Overall health score
        score = health_data['score']
        factors = health_data['factors']
        
        # Display score with color coding
        if score >= 80:
            score_color = "🟢"
            status = "Sangat Baik"
        elif score >= 60:
            score_color = "🟡"
            status = "Baik"
        elif score >= 40:
            score_color = "🟠"
            status = "Perlu Perhatian"
        else:
            score_color = "🔴"
            status = "Buruk"
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric(f"Skor Kesehatan {score_color}", f"{score:.1f}/100", status)
            st.metric("Total Item", health_data['total_items'])
        
        with col2:
            # Display factor breakdown
            st.write("**Faktor Kesehatan:**")
            for factor, value in factors.items():
                factor_name = {
                    'stock_availability': 'Ketersediaan Stok',
                    'stock_adequacy': 'Kecukupan Stok',
                    'turnover': 'Perputaran',
                    'movement': 'Aktivitas'
                }.get(factor, factor)
                
                st.write(f"• {factor_name}: {value:.1f}%")
    
    def display_turnover_analysis(self, days: int):
        """Display turnover analysis"""
        st.subheader(f"🔄 Analisis Perputaran Inventory ({days} hari)")
        
        turnover_data = self.get_inventory_turnover(days)
        
        if turnover_data['turnover_data']:
            # Convert to DataFrame
            df = pd.DataFrame(turnover_data['turnover_data'])
            
            # Display summary
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Rata-rata Perputaran", f"{turnover_data['avg_turnover']:.1f}x/tahun")
            
            with col2:
                high_turnover = len([d for d in turnover_data['turnover_data'] if d['turnover_rate'] > 6])
                low_turnover = len([d for d in turnover_data['turnover_data'] if d['turnover_rate'] < 2])
                st.metric("Item dengan Perputaran Tinggi", high_turnover)
                st.metric("Item dengan Perputaran Rendah", low_turnover)
            
            # Display top items by turnover
            st.subheader("Item dengan Perputaran Tertinggi")
            top_turnover = df.nlargest(10, 'turnover_rate')[['item_name', 'category', 'turnover_rate']]
            st.dataframe(top_turnover)
            
            # Turnover distribution chart
            fig = px.histogram(df, x='turnover_rate', nbins=20, 
                             title='Distribusi Tingkat Perputaran')
            st.plotly_chart(fig)
        else:
            st.info("Tidak cukup data untuk analisis perputaran")
    
    def display_movement_analysis(self, days: int):
        """Display movement analysis"""
        st.subheader(f"📈 Analisis Pergerakan Stok ({days} hari)")
        
        movement_data = self.get_stock_movement_analysis(days)
        
        if movement_data['movement_summary']:
            # Display summary
            st.write("**Ringkasan Transaksi:**")
            for trans_type, summary in movement_data['movement_summary'].items():
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric(f"{trans_type.title()} - Transaksi", summary['total_transactions'])
                
                with col2:
                    st.metric(f"{trans_type.title()} - Total Kuantitas", summary['total_quantity'])
                
                with col3:
                    st.metric(f"{trans_type.title()} - Rata-rata", f"{summary['avg_quantity']:.1f}")
            
            # Daily movement trend
            if movement_data['daily_movement']:
                st.subheader("Tren Harian")
                
                # Convert to DataFrame
                daily_df = pd.DataFrame.from_dict(movement_data['daily_movement'], orient='index')
                daily_df = daily_df.fillna(0)
                
                # Line chart
                fig = px.line(daily_df, title='Tren Pergerakan Harian')
                st.plotly_chart(fig)
        else:
            st.info("Tidak cukup data untuk analisis pergerakan")
    
    def display_department_efficiency(self, days: int):
        """Display department efficiency analysis"""
        st.subheader(f"🏢 Analisis Efisiensi Departemen ({days} hari)")
        
        efficiency_data = self.get_department_efficiency_analysis(days)
        
        if efficiency_data['department_analysis']:
            # Convert to DataFrame
            df = pd.DataFrame.from_dict(efficiency_data['department_analysis'], orient='index')
            
            # Display summary
            st.metric("Rata-rata Efisiensi", f"{efficiency_data['avg_efficiency']:.2f}")
            
            # Department comparison
            st.subheader("Perbandingan Departemen")
            st.dataframe(df)
            
            # Efficiency chart
            fig = px.bar(df, y='efficiency_ratio', title='Rasio Efisiensi per Departemen')
            st.plotly_chart(fig)
            
            # Consumption vs Receipt chart
            fig = px.scatter(df, x='total_received', y='total_consumed', 
                           title='Konsumsi vs Penerimaan Departemen',
                           hover_data=['total_consumed', 'total_received'])
            st.plotly_chart(fig)
        else:
            st.info("Tidak cukup data untuk analisis departemen")
    
    def display_trends_and_predictions(self, days: int):
        """Display trends and simple predictions"""
        st.subheader(f"📊 Tren & Prediksi ({days} hari)")
        
        # This would integrate with forecasting data
        st.info("Fitur prediksi akan segera tersedia dengan integrasi data forecasting")
        
        # Placeholder for future integration
        st.write("Data tren dan prediksi akan ditampilkan di sini setelah integrasi dengan modul forecasting.")

def display_analytics_widget():
    """Display a compact analytics widget"""
    analytics = InventoryAnalytics()
    health_data = analytics.get_inventory_health_score()
    
    score = health_data['score']
    
    if score >= 80:
        status = "🟢 Sangat Baik"
    elif score >= 60:
        status = "🟡 Baik"
    elif score >= 40:
        status = "🟠 Perlu Perhatian"
    else:
        status = "🔴 Buruk"
    
    st.metric("Kesehatan Inventory", f"{score:.0f}/100", status)