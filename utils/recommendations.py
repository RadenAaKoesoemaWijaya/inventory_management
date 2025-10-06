import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.database import MongoDBConnection
from typing import List, Dict, Optional
import numpy as np

class InventoryRecommendation:
    def __init__(self):
        self.db = MongoDBConnection()
    
    def get_reorder_recommendations(self) -> List[Dict]:
        """Get items that need reordering based on consumption patterns"""
        try:
            items_collection = self.db['items']
            transactions_collection = self.db['inventory_transactions']
            
            recommendations = []
            
            # Get all items with low stock
            low_stock_items = list(items_collection.find({
                "$expr": {"$lte": ["$current_stock", "$min_stock"]}
            }))
            
            for item in low_stock_items:
                # Get consumption history for last 30 days
                thirty_days_ago = datetime.now() - timedelta(days=30)
                
                consumption_data = list(transactions_collection.find({
                    'item_id': item['_id'],
                    'transaction_type': 'issue',
                    'transaction_date': {'$gte': thirty_days_ago}
                }))
                
                # Calculate average daily consumption
                if consumption_data:
                    total_consumed = sum(t['quantity'] for t in consumption_data)
                    avg_daily_consumption = total_consumed / 30
                else:
                    avg_daily_consumption = 0
                
                # Calculate days until stock runs out
                if avg_daily_consumption > 0:
                    days_until_empty = item['current_stock'] / avg_daily_consumption
                else:
                    days_until_empty = 999
                
                # Calculate recommended order quantity
                if avg_daily_consumption > 0:
                    # Order for 60 days of stock
                    recommended_quantity = int(avg_daily_consumption * 60)
                else:
                    # Default to minimum stock if no consumption data
                    recommended_quantity = item['min_stock']
                
                recommendation = {
                    'item': item,
                    'avg_daily_consumption': avg_daily_consumption,
                    'days_until_empty': days_until_empty,
                    'recommended_quantity': recommended_quantity,
                    'urgency': self._calculate_urgency(days_until_empty),
                    'current_stock': item['current_stock'],
                    'min_stock': item['min_stock']
                }
                
                recommendations.append(recommendation)
            
            # Sort by urgency (most urgent first)
            recommendations.sort(key=lambda x: x['days_until_empty'])
            
            return recommendations
            
        except Exception as e:
            print(f"Error getting reorder recommendations: {e}")
            return []
    
    def get_slow_moving_items(self) -> List[Dict]:
        """Identify slow-moving items that might be overstocked"""
        try:
            items_collection = self.db['items']
            transactions_collection = self.db['inventory_transactions']
            
            slow_moving = []
            
            # Get all items
            items = list(items_collection.find({}))
            
            for item in items:
                # Get consumption for last 90 days
                ninety_days_ago = datetime.now() - timedelta(days=90)
                
                consumption_data = list(transactions_collection.find({
                    'item_id': item['_id'],
                    'transaction_type': 'issue',
                    'transaction_date': {'$gte': ninety_days_ago}
                }))
                
                # Calculate consumption metrics
                total_consumed = sum(t['quantity'] for t in consumption_data)
                avg_daily_consumption = total_consumed / 90 if consumption_data else 0
                
                # Calculate days of stock remaining
                if avg_daily_consumption > 0:
                    days_of_stock = item['current_stock'] / avg_daily_consumption
                else:
                    days_of_stock = 999
                
                # Identify slow-moving (more than 180 days of stock)
                if days_of_stock > 180 and item['current_stock'] > item['min_stock']:
                    slow_moving.append({
                        'item': item,
                        'avg_daily_consumption': avg_daily_consumption,
                        'days_of_stock': days_of_stock,
                        'total_consumed_90d': total_consumed,
                        'excess_stock': item['current_stock'] - item['min_stock']
                    })
            
            # Sort by days of stock (most excessive first)
            slow_moving.sort(key=lambda x: x['days_of_stock'], reverse=True)
            
            return slow_moving
            
        except Exception as e:
            print(f"Error getting slow moving items: {e}")
            return []
    
    def get_category_analysis(self) -> Dict:
        """Analyze inventory by category"""
        try:
            items_collection = self.db['items']
            transactions_collection = self.db['inventory_transactions']
            
            # Get all categories
            categories = items_collection.distinct('category')
            
            category_analysis = {}
            
            for category in categories:
                # Get items in this category
                category_items = list(items_collection.find({'category': category}))
                
                if category_items:
                    # Calculate metrics
                    total_items = len(category_items)
                    low_stock_items = len([item for item in category_items if item['current_stock'] <= item['min_stock']])
                    total_stock_value = sum(item.get('unit_price', 0) * item['current_stock'] for item in category_items)
                    
                    # Get consumption for last 30 days
                    thirty_days_ago = datetime.now() - timedelta(days=30)
                    item_ids = [item['_id'] for item in category_items]
                    
                    consumption_data = list(transactions_collection.find({
                        'item_id': {'$in': item_ids},
                        'transaction_type': 'issue',
                        'transaction_date': {'$gte': thirty_days_ago}
                    }))
                    
                    total_consumed = sum(t['quantity'] for t in consumption_data)
                    
                    category_analysis[category] = {
                        'total_items': total_items,
                        'low_stock_items': low_stock_items,
                        'low_stock_percentage': (low_stock_items / total_items * 100) if total_items > 0 else 0,
                        'total_stock_value': total_stock_value,
                        'total_consumed_30d': total_consumed,
                        'avg_daily_consumption': total_consumed / 30 if consumption_data else 0
                    }
            
            return category_analysis
            
        except Exception as e:
            print(f"Error getting category analysis: {e}")
            return {}
    
    def _calculate_urgency(self, days_until_empty: float) -> str:
        """Calculate urgency level based on days until stock runs out"""
        if days_until_empty <= 7:
            return 'critical'
        elif days_until_empty <= 14:
            return 'high'
        elif days_until_empty <= 30:
            return 'medium'
        else:
            return 'low'
    
    def get_demand_forecasting(self, item_id: str, days: int = 30) -> Dict:
        """Predict future demand for an item using simple forecasting"""
        try:
            transactions_collection = self.db['inventory_transactions']
            
            # Get historical consumption data
            cutoff_date = datetime.now() - timedelta(days=90)  # Last 90 days
            
            consumption_data = list(transactions_collection.find({
                'item_id': item_id,
                'transaction_type': 'issue',
                'transaction_date': {'$gte': cutoff_date}
            }).sort('transaction_date', 1))
            
            if not consumption_data:
                return {'error': 'No historical data available'}
            
            # Calculate daily consumption
            daily_consumption = {}
            for trans in consumption_data:
                date_key = trans['transaction_date'].date()
                if date_key not in daily_consumption:
                    daily_consumption[date_key] = 0
                daily_consumption[date_key] += trans['quantity']
            
            # Calculate trend and seasonality (simple moving average)
            consumption_values = list(daily_consumption.values())
            
            # Calculate 7-day moving average
            if len(consumption_values) >= 7:
                recent_avg = np.mean(consumption_values[-7:])
                older_avg = np.mean(consumption_values[-14:-7]) if len(consumption_values) >= 14 else np.mean(consumption_values[:7])
                trend = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
            else:
                recent_avg = np.mean(consumption_values)
                trend = 0
            
            # Predict future demand
            predicted_daily_demand = recent_avg * (1 + trend)
            predicted_total_demand = predicted_daily_demand * days
            
            # Calculate confidence level based on data consistency
            if len(consumption_values) > 1:
                std_dev = np.std(consumption_values)
                mean_consumption = np.mean(consumption_values)
                coefficient_of_variation = std_dev / mean_consumption if mean_consumption > 0 else 1
                confidence_level = max(0, 1 - coefficient_of_variation)
            else:
                confidence_level = 0.5
            
            return {
                'predicted_daily_demand': predicted_daily_demand,
                'predicted_total_demand': predicted_total_demand,
                'trend': trend,
                'confidence_level': confidence_level,
                'historical_avg': recent_avg,
                'data_points': len(consumption_data),
                'forecast_period': days
            }
            
        except Exception as e:
            print(f"Error in demand forecasting: {e}")
            return {'error': str(e)}
    
    def get_optimization_recommendations(self) -> List[Dict]:
        """Get inventory optimization recommendations"""
        try:
            items_collection = self.db['items']
            transactions_collection = self.db['inventory_transactions']
            
            recommendations = []
            
            # Get all items
            items = list(items_collection.find({}))
            
            for item in items:
                # Get demand forecast
                forecast = self.get_demand_forecasting(str(item['_id']))
                
                if 'error' in forecast:
                    continue
                
                predicted_daily_demand = forecast['predicted_daily_demand']
                confidence_level = forecast['confidence_level']
                
                # Calculate optimal stock levels
                if predicted_daily_demand > 0:
                    # Economic Order Quantity (EOQ) - simplified
                    annual_demand = predicted_daily_demand * 365
                    ordering_cost = 50  # Assumed ordering cost
                    holding_cost = 2    # Assumed holding cost per unit per year
                    
                    if holding_cost > 0:
                        eoq = np.sqrt((2 * annual_demand * ordering_cost) / holding_cost)
                    else:
                        eoq = item['min_stock']
                    
                    # Safety stock (for 7 days + 50% buffer)
                    safety_stock = predicted_daily_demand * 7 * 1.5
                    
                    # Reorder point
                    lead_time_days = 7  # Assumed lead time
                    reorder_point = (predicted_daily_demand * lead_time_days) + safety_stock
                    
                    # Current stock analysis
                    current_stock = item['current_stock']
                    min_stock = item['min_stock']
                    
                    # Determine if optimization is needed
                    optimization_needed = False
                    recommendation_type = ""
                    reason = ""
                    
                    if current_stock < reorder_point:
                        optimization_needed = True
                        recommendation_type = "reorder"
                        reason = f"Stok saat ini ({current_stock}) di bawah titik pesan ulang ({reorder_point:.0f})"
                    elif current_stock > (reorder_point + eoq):
                        optimization_needed = True
                        recommendation_type = "reduce"
                        reason = f"Stok berlebih. Consider reducing by {current_stock - (reorder_point + eoq):.0f} units"
                    elif min_stock > safety_stock:
                        optimization_needed = True
                        recommendation_type = "adjust_min_stock"
                        reason = f"Stok minimum dapat diturunkan dari {min_stock} ke {safety_stock:.0f}"
                    
                    if optimization_needed:
                        recommendations.append({
                            'item': item,
                            'recommendation_type': recommendation_type,
                            'reason': reason,
                            'predicted_daily_demand': predicted_daily_demand,
                            'confidence_level': confidence_level,
                            'optimal_reorder_point': reorder_point,
                            'economic_order_quantity': eoq,
                            'safety_stock': safety_stock,
                            'current_stock': current_stock,
                            'current_min_stock': min_stock
                        })
            
            # Sort by confidence level (highest first)
            recommendations.sort(key=lambda x: x['confidence_level'], reverse=True)
            
            return recommendations
            
        except Exception as e:
            print(f"Error getting optimization recommendations: {e}")
            return []
    
    def display_recommendation_dashboard(self):
        """Display recommendation dashboard"""
        st.header("🤖 Rekomendasi Inventory")
        
        # Create tabs for different types of recommendations
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Rekomendasi Pemesanan", 
            "Item Lambat Bergerak", 
            "Analisis Kategori",
            "Optimasi AI",
            "Ringkasan"
        ])
        
        with tab1:
            self.display_reorder_recommendations()
        
        with tab4:
            self.display_optimization_recommendations()
        
        with tab2:
            self.display_slow_moving_items()
        
        with tab3:
            self.display_category_analysis()
        
        with tab4:
            self.display_summary()
    
    def display_reorder_recommendations(self):
        """Display reorder recommendations"""
        st.subheader("📦 Rekomendasi Pemesanan Ulang")
        
        recommendations = self.get_reorder_recommendations()
        
        if recommendations:
            # Display summary
            critical_count = len([r for r in recommendations if r['urgency'] == 'critical'])
            high_count = len([r for r in recommendations if r['urgency'] == 'high'])
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total Rekomendasi", len(recommendations))
            
            with col2:
                if critical_count > 0:
                    st.metric("Kritis", critical_count, delta=None)
                else:
                    st.metric("Kritis", 0)
            
            with col3:
                if high_count > 0:
                    st.metric("Tinggi", high_count, delta=None)
                else:
                    st.metric("Tinggi", 0)
            
            # Display detailed recommendations
            st.subheader("Detail Rekomendasi")
            
            for rec in recommendations:
                item = rec['item']
                urgency_color = {
                    'critical': '🔴',
                    'high': '🟠',
                    'medium': '🟡',
                    'low': '🟢'
                }.get(rec['urgency'], '⚪')
                
                with st.expander(f"{urgency_color} {item['name']} - {rec['days_until_empty']:.0f} hari tersisa"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Kategori:** {item['category']}")
                        st.write(f"**Stok Saat Ini:** {item['current_stock']} {item['unit']}")
                        st.write(f"**Konsumsi Harian Rata-rata:** {rec['avg_daily_consumption']:.1f} {item['unit']}")
                        st.write(f"**Stok Minimum:** {item['min_stock']} {item['unit']}")
                    
                    with col2:
                        st.write(f"**Hari Habis:** {rec['days_until_empty']:.0f} hari")
                        st.write(f"**Rekomendasi Jumlah:** {rec['recommended_quantity']} {item['unit']}")
                        st.write(f"**Tingkat Urgensi:** {rec['urgency'].title()}")
                        
                        # Calculate estimated cost (assuming $50 per unit)
                        estimated_cost = rec['recommended_quantity'] * 50
                        st.write(f"**Estimasi Biaya:** ${estimated_cost:,.0f}")
        else:
            st.success("✅ Tidak ada rekomendasi pemesanan saat ini")
    
    def display_optimization_recommendations(self):
        """Display AI-powered optimization recommendations"""
        st.subheader("🤖 Rekomendasi Optimasi AI")
        st.info("Rekomendasi ini dihasilkan menggunakan analisis prediktif dan algoritma optimasi inventory")
        
        recommendations = self.get_optimization_recommendations()
        
        if recommendations:
            # Display summary metrics
            reorder_count = len([r for r in recommendations if r['recommendation_type'] == 'reorder'])
            reduce_count = len([r for r in recommendations if r['recommendation_type'] == 'reduce'])
            adjust_count = len([r for r in recommendations if r['recommendation_type'] == 'adjust_min_stock'])
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Rekomendasi", len(recommendations))
            
            with col2:
                if reorder_count > 0:
                    st.metric("Perlu Dipesan", reorder_count, delta=None)
                else:
                    st.metric("Perlu Dipesan", 0)
            
            with col3:
                if reduce_count > 0:
                    st.metric("Perlu Dikurangi", reduce_count, delta=None)
                else:
                    st.metric("Perlu Dikurangi", 0)
            
            with col4:
                if adjust_count > 0:
                    st.metric("Sesuaikan Min Stock", adjust_count, delta=None)
                else:
                    st.metric("Sesuaikan Min Stock", 0)
            
            # Display detailed recommendations
            st.subheader("Detail Rekomendasi Optimasi")
            
            for rec in recommendations:
                item = rec['item']
                confidence_pct = rec['confidence_level'] * 100
                
                # Color code based on recommendation type
                if rec['recommendation_type'] == 'reorder':
                    header_color = '🔴'
                elif rec['recommendation_type'] == 'reduce':
                    header_color = '🟠'
                else:
                    header_color = '🟡'
                
                with st.expander(f"{header_color} {item['name']} - Confidence: {confidence_pct:.0f}%"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Kategori:** {item['category']}")
                        st.write(f"**Stok Saat Ini:** {rec['current_stock']} {item['unit']}")
                        st.write(f"**Permintaan Harian Prediksi:** {rec['predicted_daily_demand']:.1f} {item['unit']}")
                        st.write(f"**Confidence Level:** {confidence_pct:.0f}%")
                    
                    with col2:
                        st.write(f"**Rekomendasi:** {rec['recommendation_type'].replace('_', ' ').title()}")
                        st.write(f"**Alasan:** {rec['reason']}")
                        st.write(f"**Titik Pesan Ulang Optimal:** {rec['optimal_reorder_point']:.0f} {item['unit']}")
                        st.write(f"**Kuantitas Order Ekonomis:** {rec['economic_order_quantity']:.0f} {item['unit']}")
                    
                    # Show demand forecast if available
                    if 'predicted_daily_demand' in rec:
                        with st.expander("📊 Detail Forecasting"):
                            forecast = self.get_demand_forecasting(str(item['_id']))
                            if 'error' not in forecast:
                                col_f1, col_f2, col_f3 = st.columns(3)
                                with col_f1:
                                    st.metric("Trend", f"{forecast['trend']*100:.1f}%")
                                with col_f2:
                                    st.metric("Data Points", forecast['data_points'])
                                with col_f3:
                                    st.metric("Historical Avg", f"{forecast['historical_avg']:.1f}")
        else:
            st.success("✅ Tidak ada rekomendasi optimasi saat ini. Inventory Anda sudah optimal!")
    
    def display_slow_moving_items(self):
        """Display slow-moving items"""
        st.subheader("🐌 Item Lambat Bergerak")
        
        slow_items = self.get_slow_moving_items()
        
        if slow_items:
            st.info(f"Menemukan {len(slow_items)} item dengan stok berlebih (>180 hari)")
            
            for item in slow_items:
                with st.expander(f"{item['item']['name']} - {item['days_of_stock']:.0f} hari stok"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Kategori:** {item['item']['category']}")
                        st.write(f"**Stok Saat Ini:** {item['item']['current_stock']} {item['item']['unit']}")
                        st.write(f"**Stok Minimum:** {item['item']['min_stock']} {item['item']['unit']}")
                    
                    with col2:
                        st.write(f"**Konsumsi 90 Hari:** {item['total_consumed_90d']} {item['item']['unit']}")
                        st.write(f"**Rata-rata Harian:** {item['avg_daily_consumption']:.1f} {item['item']['unit']}/hari")
                        st.write(f"**Stok Berlebih:** {item['excess_stock']} {item['item']['unit']}")
        else:
            st.success("✅ Tidak ada item lambat bergerak yang terdeteksi")
    
    def display_category_analysis(self):
        """Display category analysis"""
        st.subheader("📊 Analisis Kategori")
        
        analysis = self.get_category_analysis()
        
        if analysis:
            # Convert to DataFrame for better display
            df = pd.DataFrame.from_dict(analysis, orient='index')
            df = df.sort_values('low_stock_percentage', ascending=False)
            
            st.dataframe(df)
            
            # Display charts
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Persentase Stok Rendah per Kategori")
                st.bar_chart(df['low_stock_percentage'])
            
            with col2:
                st.subheader("Konsumsi Harian Rata-rata per Kategori")
                st.bar_chart(df['avg_daily_consumption'])
        else:
            st.info("Tidak cukup data untuk analisis kategori")
    
    def display_summary(self):
        """Display summary of all recommendations"""
        st.subheader("📋 Ringkasan Rekomendasi")
        
        reorder_rec = self.get_reorder_recommendations()
        slow_moving = self.get_slow_moving_items()
        category_analysis = self.get_category_analysis()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            critical_count = len([r for r in reorder_rec if r['urgency'] == 'critical'])
            st.metric("Pemesanan Kritis", critical_count)
        
        with col2:
            st.metric("Item Lambat Bergerak", len(slow_moving))
        
        with col3:
            st.metric("Kategori Dianalisis", len(category_analysis))
        
        # Action items
        st.subheader("🎯 Tindakan yang Disarankan")
        
        actions = []
        
        if critical_count > 0:
            actions.append(f"🚨 Segera pesan {critical_count} item kritis")
        
        if len(slow_moving) > 0:
            actions.append(f"📉 Tinjau ulang {len(slow_moving)} item lambat bergerak")
        
        if len(category_analysis) > 0:
            avg_low_stock = sum(data['low_stock_percentage'] for data in category_analysis.values()) / len(category_analysis)
            if avg_low_stock > 20:
                actions.append(f"⚠️ Tingkatkan manajemen stok (rata-rata {avg_low_stock:.1f}% stok rendah)")
        
        if actions:
            for action in actions:
                st.write(f"• {action}")
        else:
            st.success("✅ Tidak ada tindakan mendesak yang diperlukan")
    
    def _get_urgency_color(self, urgency: str) -> str:
        """Get emoji color for urgency level"""
        colors = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡',
            'low': '🟢'
        }
        return colors.get(urgency, '⚪')

def display_recommendation_widget():
    """Display a compact recommendation widget"""
    recommender = InventoryRecommendation()
    
    reorder_rec = recommender.get_reorder_recommendations()
    critical_count = len([r for r in reorder_rec if r['urgency'] == 'critical'])
    
    if critical_count > 0:
        st.warning(f"🚨 {critical_count} item perlu dipesan segera")
    else:
        st.success("✅ Tidak ada pemesanan mendesak")