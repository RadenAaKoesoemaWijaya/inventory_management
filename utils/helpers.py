import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from sklearn.linear_model import LinearRegression
from .database import get_db_connection

def format_date(date_str):
    """Format date string for display"""
    if not date_str:
        return ""
    date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    return date_obj.strftime('%d %b %Y, %H:%M')

def get_stock_status():
    """Get overall stock status summary"""
    conn = get_db_connection()
    
    # Get total items
    total_items = pd.read_sql_query('SELECT COUNT(*) as count FROM items', conn).iloc[0]['count']
    
    # Get low stock items
    low_stock = pd.read_sql_query(
        'SELECT COUNT(*) as count FROM items WHERE current_stock <= min_stock', 
        conn
    ).iloc[0]['count']
    
    # Get out of stock items
    out_of_stock = pd.read_sql_query(
        'SELECT COUNT(*) as count FROM items WHERE current_stock = 0', 
        conn
    ).iloc[0]['count']
    
    # Get healthy stock items
    healthy_stock = total_items - low_stock
    
    conn.close()
    
    return {
        'total_items': total_items,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'healthy_stock': healthy_stock
    }

def get_department_consumption():
    """Get consumption by department for the last 30 days"""
    conn = get_db_connection()
    
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    query = '''
    SELECT d.name as department, SUM(t.quantity) as total_consumption
    FROM inventory_transactions t
    JOIN departments d ON t.to_department_id = d.id
    WHERE t.transaction_type = 'issue'
    AND t.transaction_date >= ?
    GROUP BY t.to_department_id
    ORDER BY total_consumption DESC
    '''
    
    consumption = pd.read_sql_query(query, conn, params=(thirty_days_ago,))
    conn.close()
    
    return consumption

def get_top_consumed_items(limit=10):
    """Get top consumed items for the last 30 days"""
    conn = get_db_connection()
    
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    query = '''
    SELECT i.name as item_name, SUM(t.quantity) as total_consumption
    FROM inventory_transactions t
    JOIN items i ON t.item_id = i.id
    WHERE t.transaction_type = 'issue'
    AND t.transaction_date >= ?
    GROUP BY t.item_id
    ORDER BY total_consumption DESC
    LIMIT ?
    '''
    
    top_items = pd.read_sql_query(query, conn, params=(thirty_days_ago, limit))
    conn.close()
    
    return top_items