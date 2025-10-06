import streamlit as st
from utils.database import MongoDBConnection
import threading
import queue
import time
from datetime import datetime
import pandas as pd

class InventoryChangeStream:
    def __init__(self):
        self.db = MongoDBConnection()
        self.change_queue = queue.Queue()
        self.running = False
        self.thread = None
    
    def start_listening(self):
        """Start listening to MongoDB change streams"""
        self.running = True
        self.thread = threading.Thread(target=self._listen_changes, daemon=True)
        self.thread.start()
    
    def stop_listening(self):
        """Stop listening to changes"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
    
    def _listen_changes(self):
        """Listen to MongoDB change streams"""
        try:
            # Watch for changes in inventory_transactions
            with self.db.inventory_transactions.watch() as stream:
                while self.running:
                    try:
                        change = stream.try_next()
                        if change is not None:
                            self.change_queue.put(change)
                        else:
                            time.sleep(0.1)  # Small delay to prevent busy waiting
                    except Exception as e:
                        print(f"Error in change stream: {e}")
                        time.sleep(1)  # Wait before retrying
        except Exception as e:
            print(f"Failed to start change stream: {e}")
    
    def get_recent_changes(self, limit=10):
        """Get recent changes from the queue"""
        changes = []
        try:
            while len(changes) < limit:
                change = self.change_queue.get_nowait()
                changes.append(change)
        except queue.Empty:
            pass
        return changes
    
    def get_stock_alerts(self):
        """Get current stock alerts"""
        try:
            # Find items with low stock
            low_stock_items = list(self.db.items.find({
                "$expr": {"$lte": ["$current_stock", "$min_stock"]}
            }).limit(10))
            
            return low_stock_items
        except Exception as e:
            print(f"Error getting stock alerts: {e}")
            return []

class RealtimeDashboard:
    def __init__(self):
        self.change_stream = InventoryChangeStream()
        self.last_update = datetime.now()
    
    def display_realtime_alerts(self):
        """Display real-time stock alerts"""
        st.subheader("🚨 Peringatan Stok Real-time")
        
        # Get current stock alerts
        alerts = self.change_stream.get_stock_alerts()
        
        if alerts:
            for alert in alerts:
                stock_percentage = (alert['current_stock'] / alert['min_stock']) * 100 if alert['min_stock'] > 0 else 0
                
                if stock_percentage <= 50:
                    severity = "🔴"
                    message = "Stok sangat rendah!"
                elif stock_percentage <= 100:
                    severity = "🟡"
                    message = "Stok rendah"
                else:
                    severity = "🟢"
                    message = "Stok normal"
                
                st.warning(f"{severity} **{alert['name']}** - {message} "
                          f"({alert['current_stock']} {alert['unit']} dari {alert['min_stock']} minimum)")
        else:
            st.info("Tidak ada peringatan stok saat ini")
    
    def display_recent_transactions(self):
        """Display recent transactions with real-time updates"""
        st.subheader("📊 Transaksi Terkini")
        
        # Get recent transactions
        db = self.change_stream.db
        
        # Get last 10 transactions with details
        recent_transactions = list(db.inventory_transactions.find().sort('created_at', -1).limit(10))
        
        if recent_transactions:
            # Enrich transaction data
            enriched_transactions = []
            for trans in recent_transactions:
                # Get item details
                item = db.items.find_one({'_id': trans['item_id']})
                item_name = item['name'] if item else "Unknown Item"
                
                # Get user details
                user = db.users.find_one({'_id': trans['created_by']})
                user_name = user['username'] if user else "Unknown User"
                
                # Get department details if available
                dept_info = ""
                if trans.get('to_department_id'):
                    dept = db.departments.find_one({'_id': trans['to_department_id']})
                    if dept:
                        dept_info = f" → {dept['name']}"
                
                enriched_transactions.append({
                    'Waktu': trans['created_at'].strftime('%d/%m/%Y %H:%M'),
                    'Item': item_name,
                    'Jenis': trans['transaction_type'],
                    'Jumlah': f"{trans['quantity']} {item['unit'] if item else ''}",
                    'Oleh': user_name,
                    'Tujuan': dept_info,
                    'Catatan': trans.get('notes', '')
                })
            
            # Display as dataframe
            df = pd.DataFrame(enriched_transactions)
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Belum ada transaksi")
    
    def display_activity_summary(self):
        """Display activity summary with real-time data"""
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Count today's transactions
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            db = self.change_stream.db
            today_count = db.inventory_transactions.count_documents({
                'created_at': {'$gte': today}
            })
            st.metric("Transaksi Hari Ini", today_count)
        
        with col2:
            # Count low stock items
            low_stock_count = db.items.count_documents({
                "$expr": {"$lte": ["$current_stock", "$min_stock"]}
            })
            st.metric("Item Stok Rendah", low_stock_count)
        
        with col3:
            # Count total items
            total_items = db.items.count_documents({})
            st.metric("Total Item", total_items)
    
    def run_realtime_updates(self):
        """Run the real-time update system"""
        # Start listening to changes
        if 'change_stream_started' not in st.session_state:
            self.change_stream.start_listening()
            st.session_state.change_stream_started = True
        
        # Display sections
        self.display_activity_summary()
        
        col1, col2 = st.columns(2)
        
        with col1:
            self.display_realtime_alerts()
        
        with col2:
            self.display_recent_transactions()
        
        # Auto-refresh indicator
        st.caption(f"🔄 Pembaruan otomatis aktif - Terakhir diperbarui: {datetime.now().strftime('%H:%M:%S')}")
        
        # Add refresh button for manual update
        if st.button("🔄 Segarkan Data"):
            st.rerun()

def display_realtime_widget():
    """Display a compact real-time widget for dashboards"""
    realtime = RealtimeDashboard()
    
    # Get current alerts
    alerts = realtime.change_stream.get_stock_alerts()
    
    if alerts:
        st.warning(f"⚠️ {len(alerts)} item memerlukan perhatian stok")
        
        # Show top 3 alerts
        for alert in alerts[:3]:
            stock_percentage = (alert['current_stock'] / alert['min_stock']) * 100 if alert['min_stock'] > 0 else 0
            st.text(f"• {alert['name']}: {alert['current_stock']}/{alert['min_stock']} ({stock_percentage:.0f}%)")
        
        if len(alerts) > 3:
            st.text(f"... dan {len(alerts) - 3} item lainnya")
    else:
        st.success("✅ Semua stok dalam kondisi baik")