import streamlit as st
from datetime import datetime, timedelta
from utils.database import MongoDBConnection
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from typing import List, Dict, Optional

class NotificationManager:
    def __init__(self):
        self.db = MongoDBConnection()
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_username = os.getenv('SMTP_USERNAME')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@inventory.com')
    
    def check_stock_alerts(self) -> List[Dict]:
        """Check for items with low stock"""
        try:
            items_collection = self.db.get_collection('items')
            
            # Find items with stock below minimum
            low_stock_items = list(items_collection.find({
                "$expr": {"$lte": ["$current_stock", "$min_stock"]}
            }))
            
            # Calculate urgency level
            for item in low_stock_items:
                if item['min_stock'] > 0:
                    stock_percentage = (item['current_stock'] / item['min_stock']) * 100
                else:
                    stock_percentage = 0
                
                if stock_percentage <= 25:
                    item['urgency'] = 'critical'
                    item['urgency_color'] = '🔴'
                elif stock_percentage <= 50:
                    item['urgency'] = 'high'
                    item['urgency_color'] = '🟠'
                elif stock_percentage <= 100:
                    item['urgency'] = 'medium'
                    item['urgency_color'] = '🟡'
                else:
                    item['urgency'] = 'low'
                    item['urgency_color'] = '🟢'
                
                item['stock_percentage'] = stock_percentage
            
            return low_stock_items
            
        except Exception as e:
            print(f"Error checking stock alerts: {e}")
            return []
    
    def display_notification_dashboard(self):
        """Display notification dashboard in Streamlit"""
        st.header("🔔 Sistem Notifikasi")
        
        # Create tabs for different notification features
        tab1, tab2 = st.tabs(["Peringatan Stok", "Laporan"])
        
        with tab1:
            self.display_stock_alerts()
        
        with tab2:
            self.display_reports()
    
    def display_stock_alerts(self):
        """Display stock alerts"""
        st.subheader("📊 Peringatan Stok")
        
        # Get current alerts
        alerts = self.check_stock_alerts()
        
        if alerts:
            # Display summary
            col1, col2, col3 = st.columns(3)
            
            with col1:
                critical_count = len([a for a in alerts if a['urgency'] == 'critical'])
                st.metric("Kritis", critical_count, delta=None)
            
            with col2:
                high_count = len([a for a in alerts if a['urgency'] == 'high'])
                st.metric("Tinggi", high_count, delta=None)
            
            with col3:
                medium_count = len([a for a in alerts if a['urgency'] == 'medium'])
                st.metric("Sedang", medium_count, delta=None)
            
            # Display detailed alerts
            st.subheader("Detail Peringatan")
            
            for alert in alerts:
                urgency_color = alert['urgency_color']
                stock_percentage = alert['stock_percentage']
                
                with st.expander(f"{urgency_color} {alert['name']} - {stock_percentage:.0f}% dari stok minimum"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**Kategori:** {alert['category']}")
                        st.write(f"**Stok Saat Ini:** {alert['current_stock']} {alert['unit']}")
                        st.write(f"**Stok Minimum:** {alert['min_stock']} {alert['unit']}")
                    
                    with col2:
                        st.write(f"**Persentase Stok:** {stock_percentage:.1f}%")
                        st.write(f"**Tingkat Urgensi:** {alert['urgency'].title()}")
                        
                        # Calculate days until stock runs out (simple estimation)
                        if alert['current_stock'] > 0:
                            # Assume average daily usage based on minimum stock (30 days)
                            daily_usage = alert['min_stock'] / 30
                            days_remaining = alert['current_stock'] / daily_usage if daily_usage > 0 else 999
                            st.write(f"**Estimasi Habis:** {days_remaining:.0f} hari")
        else:
            st.success("✅ Tidak ada peringatan stok saat ini")
    
    def display_reports(self):
        """Display notification reports"""
        st.subheader("📈 Laporan Notifikasi")
        
        # Get inventory statistics
        items_collection = self.db.get_collection('items')
        total_items = items_collection.count_documents({})
        low_stock_count = len(self.check_stock_alerts())
        out_of_stock = items_collection.count_documents({'current_stock': 0})
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Item", total_items)
        
        with col2:
            st.metric("Stok Rendah", low_stock_count)
        
        with col3:
            st.metric("Habis Stok", out_of_stock)
    
    def generate_stock_alert_report(self) -> Dict:
        """Generate a comprehensive stock alert report"""
        try:
            alerts = self.check_stock_alerts()
            
            # Get inventory statistics
            items_collection = self.db.get_collection('items')
            total_items = items_collection.count_documents({})
            low_stock_count = len(alerts)
            out_of_stock = items_collection.count_documents({'current_stock': 0})
            
            # Calculate total value at risk (if cost data available)
            total_value_at_risk = 0
            for alert in alerts:
                # Assuming average cost of $50 per item (would be better to have actual cost data)
                estimated_value = alert['current_stock'] * 50
                total_value_at_risk += estimated_value
            
            report = {
                'generated_at': datetime.now(),
                'summary': {
                    'total_items': total_items,
                    'low_stock_items': low_stock_count,
                    'out_of_stock_items': out_of_stock,
                    'value_at_risk': total_value_at_risk
                },
                'alerts': alerts
            }
            
            return report
            
        except Exception as e:
            print(f"Error generating report: {e}")
            return {}

def display_notification_widget():
    """Display a compact notification widget"""
    manager = NotificationManager()
    
    alerts = manager.check_stock_alerts()
    
    if alerts:
        st.warning(f"🔔 {len(alerts)} peringatan stok aktif")
        
        # Show top 3 alerts
        for alert in alerts[:3]:
            stock_percentage = alert['stock_percentage']
            st.text(f"• {alert['name']}: {alert['current_stock']}/{alert['min_stock']} ({stock_percentage:.0f}%)")
        
        if len(alerts) > 3:
            st.text(f"... dan {len(alerts) - 3} item lainnya")
    else:
        st.success("✅ Tidak ada peringatan")