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
            items_collection = self.db.get_collection('items')
            transactions_collection = self.db.get_collection('inventory_transactions')
            
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
            items_collection = self.db.get_collection('items')
            transactions_collection = self.db.get_collection('inventory_transactions')
            
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
            items_collection = self.db.get_collection('items')
            transactions_collection = self.db.get_collection('inventory_transactions')
            
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
    
    def display_recommendation_dashboard(self):
        """Display recommendation dashboard"""
        st.header("🤖 Rekomendasi Inventory")
        
        # Create tabs for different types of recommendations
        tab1, tab2, tab3, tab4 = st.tabs([
            "Rekomendasi Pemesanan", 
            "Item Lambat Bergerak", 
            "Analisis Kategori",
            "Ringkasan"
        ])
        
        with tab1:
            self.display_reorder_recommendations()
        
        with tab2:
            self.display_slow_moving_items()
        
        with tab3:
            self.display_category_analysis()
        
        with tab4:
            self.display_summary()
    
    def display_reorder_recommendations(self):
        """Display reorder recommendations"""
        st.subheader("📦 Rekomendasi Pemesanan")
        
        recommendations = self.get_reorder_recommendations()
        
        if recommendations:
            # Display summary
            col1, col2, col3 = st.columns(3)
            
            with col1:
                critical_count = len([r for r in recommendations if r['urgency'] == 'critical'])
                st.metric("Kritis (≤7 hari)", critical_count)
            
            with col2:
                high_count = len([r for r in recommendations if r['urgency'] == 'high'])
                st.metric("Tinggi (8-14 hari)", high_count)
            
            with col3:
                total_reorder_value = sum(r['recommended_quantity'] * r['item'].get('unit_price', 50) for r in recommendations)
                st.metric("Estimasi Nilai Pemesanan", f"${total_reorder_value:,.0f}")
            
            # Display detailed recommendations
            st.subheader("Detail Rekomendasi")
            
            for rec in recommendations:
                urgency_color = self._get_urgency_color(rec['urgency'])
                
                with st.expander(f"{urgency_color} {rec['item']['name']} - {rec['days_until_empty']:.0f} hari tersisa"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Kategori:** {rec['item']['category']}")
                        st.write(f"**Stok Saat Ini:** {rec['current_stock']} {rec['item']['unit']}")
                        st.write(f"**Stok Minimum:** {rec['min_stock']} {rec['item']['unit']}")
                        st.write(f"**Konsumsi Rata-rata:** {rec['avg_daily_consumption']:.1f} {rec['item']['unit']}/hari")
                    
                    with col2:
                        st.write(f"**Hari Habis:** {rec['days_until_empty']:.0f}")
                        st.write(f"**Rekomendasi Jumlah:** {rec['recommended_quantity']} {rec['item']['unit']}")
                        st.write(f"**Estimasi Biaya:** ${rec['recommended_quantity'] * rec['item'].get('unit_price', 50):,.0f}")
        else:
            st.success("✅ Tidak ada item yang perlu dipesan saat ini")
    
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