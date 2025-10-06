import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from sklearn.linear_model import LinearRegression
from .database import MongoDBConnection
from bson import ObjectId

def format_date(date_str):
    """Format date string for display"""
    if not date_str:
        return ""
    date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    return date_obj.strftime('%d %b %Y, %H:%M')

def get_stock_status():
    """Get overall stock status summary using MongoDB"""
    db = MongoDBConnection.get_database()
    
    # Get total items count
    total_items = db.items.count_documents({})
    
    # Get low stock items count
    low_stock = db.items.count_documents({
        "$expr": {"$lte": ["$current_stock", "$min_stock"]}
    })
    
    # Get out of stock items count
    out_of_stock = db.items.count_documents({'current_stock': 0})
    
    # Get healthy stock items
    healthy_stock = total_items - low_stock
    
    return {
        'total_items': total_items,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'healthy_stock': healthy_stock
    }

def get_department_consumption():
    """Get consumption by department for the last 30 days using MongoDB"""
    db = MongoDBConnection.get_database()
    
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    # Aggregate consumption by department
    pipeline = [
        {
            "$match": {
                "transaction_type": "issue",
                "transaction_date": {"$gte": thirty_days_ago}
            }
        },
        {
            "$group": {
                "_id": "$to_department_id",
                "total_consumption": {"$sum": "$quantity"}
            }
        },
        {
            "$lookup": {
                "from": "departments",
                "localField": "_id",
                "foreignField": "_id",
                "as": "department_info"
            }
        },
        {
            "$unwind": "$department_info"
        },
        {
            "$project": {
                "department": "$department_info.name",
                "total_consumption": 1,
                "_id": 0
            }
        },
        {
            "$sort": {"total_consumption": -1}
        }
    ]
    
    results = list(db.inventory_transactions.aggregate(pipeline))
    
    if results:
        return pd.DataFrame(results)
    else:
        return pd.DataFrame(columns=['department', 'total_consumption'])

def get_top_consumed_items(limit=10):
    """Get top consumed items for the last 30 days using MongoDB"""
    db = MongoDBConnection.get_database()
    
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    # Aggregate top consumed items
    pipeline = [
        {
            "$match": {
                "transaction_type": "issue",
                "transaction_date": {"$gte": thirty_days_ago}
            }
        },
        {
            "$group": {
                "_id": "$item_id",
                "total_consumption": {"$sum": "$quantity"}
            }
        },
        {
            "$lookup": {
                "from": "items",
                "localField": "_id",
                "foreignField": "_id",
                "as": "item_info"
            }
        },
        {
            "$unwind": "$item_info"
        },
        {
            "$project": {
                "item_name": "$item_info.name",
                "total_consumption": 1,
                "_id": 0
            }
        },
        {
            "$sort": {"total_consumption": -1}
        },
        {
            "$limit": limit
        }
    ]
    
    results = list(db.inventory_transactions.aggregate(pipeline))
    
    if results:
        return pd.DataFrame(results)
    else:
        return pd.DataFrame(columns=['item_name', 'total_consumption'])