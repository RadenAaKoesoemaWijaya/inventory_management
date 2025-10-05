import pymongo
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, OperationFailure
import pandas as pd
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Any
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MONGODB_SETTINGS, REALTIME_SETTINGS
import json
from bson import ObjectId

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MongoDBConnection:
    """MongoDB connection manager with connection pooling"""
    
    _client = None
    _database = None
    
    @classmethod
    def get_client(cls):
        """Get MongoDB client with connection pooling"""
        if cls._client is None:
            try:
                # Build connection string
                if MONGODB_SETTINGS['username'] and MONGODB_SETTINGS['password']:
                    connection_string = f"mongodb://{MONGODB_SETTINGS['username']}:{MONGODB_SETTINGS['password']}@{MONGODB_SETTINGS['host']}:{MONGODB_SETTINGS['port']}/{MONGODB_SETTINGS['auth_source']}"
                else:
                    connection_string = f"mongodb://{MONGODB_SETTINGS['host']}:{MONGODB_SETTINGS['port']}"
                
                # Create client with connection pooling
                cls._client = MongoClient(
                    connection_string,
                    maxPoolSize=MONGODB_SETTINGS['maxPoolSize'],
                    minPoolSize=MONGODB_SETTINGS['minPoolSize'],
                    maxIdleTimeMS=MONGODB_SETTINGS['maxIdleTimeMS'],
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=10000,
                    socketTimeoutMS=10000,
                    retryWrites=True,
                    retryReads=True
                )
                
                # Test connection
                cls._client.admin.command('ping')
                logger.info("MongoDB connection established successfully")
                
            except ConnectionFailure as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                raise
        
        return cls._client
    
    @classmethod
    def get_database(cls):
        """Get database instance"""
        if cls._database is None:
            client = cls.get_client()
            cls._database = client[MONGODB_SETTINGS['database']]
            
            # Create indexes for better performance
            cls._create_indexes(cls._database)
            
        return cls._database
    
    @classmethod
    def _create_indexes(cls, db):
        """Create indexes for optimal performance"""
        try:
            # Users collection indexes
            db.users.create_index([("username", ASCENDING)], unique=True)
            db.users.create_index([("role", ASCENDING)])
            db.users.create_index([("department", ASCENDING)])
            
            # Items collection indexes
            db.items.create_index([("name", ASCENDING)])
            db.items.create_index([("category", ASCENDING)])
            db.items.create_index([("current_stock", ASCENDING)])
            db.items.create_index([("min_stock", ASCENDING)])
            
            # Transactions collection indexes
            db.inventory_transactions.create_index([("item_id", ASCENDING)])
            db.inventory_transactions.create_index([("transaction_type", ASCENDING)])
            db.inventory_transactions.create_index([("transaction_date", DESCENDING)])
            db.inventory_transactions.create_index([("created_by", ASCENDING)])
            
            # Requests collection indexes
            db.item_requests.create_index([("status", ASCENDING)])
            db.item_requests.create_index([("request_date", DESCENDING)])
            db.item_requests.create_index([("department_id", ASCENDING)])
            
            logger.info("Database indexes created successfully")
            
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
    
    @classmethod
    def close_connection(cls):
        """Close MongoDB connection"""
        if cls._client:
            cls._client.close()
            cls._client = None
            cls._database = None
            logger.info("MongoDB connection closed")

# Helper function to convert ObjectId to string
def object_id_to_str(obj):
    """Convert ObjectId to string for JSON serialization"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: object_id_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [object_id_to_str(item) for item in obj]
    return obj

# Database initialization functions
def init_db():
    """Initialize MongoDB database with collections and default data"""
    try:
        db = MongoDBConnection.get_database()
        
        # Create collections if they don't exist
        collections = ['users', 'items', 'departments', 'inventory_transactions', 'item_requests', 'notifications']
        existing_collections = db.list_collection_names()
        
        for collection in collections:
            if collection not in existing_collections:
                db.create_collection(collection)
                logger.info(f"Created collection: {collection}")
        
        # Insert default departments
        default_departments = [
            {"name": "Klaster Manajemen", "description": "Manajemen dan administrasi"},
            {"name": "Klaster Ibu dan Anak", "description": "Layanan kesehatan ibu dan anak"},
            {"name": "Klaster Usia Produktif dan Lanjut Usia", "description": "Layanan untuk usia produktif dan lansia"},
            {"name": "Klaster Pencegahan Penyakit Menular", "description": "Pencegahan dan penanggulangan penyakit menular"},
            {"name": "Lintas Klaster - Apotek Farmasi", "description": "Pelayanan farmasi dan apotek"},
            {"name": "Lintas Klaster - Laboratorium", "description": "Pemeriksaan laboratorium"},
            {"name": "Lintas Klaster - Kesehatan Gigi", "description": "Pelayanan kesehatan gigi"},
            {"name": "Lintas Klaster - Layanan Kegawatdaruratan", "description": "Layanan gawat darurat"},
            {"name": "Warehouse", "description": "Main storage facility"},
            {"name": "Emergency Room", "description": "ER department"},
            {"name": "Surgery", "description": "Surgery department"},
            {"name": "Pharmacy", "description": "Pharmacy department"},
            {"name": "Laboratory", "description": "Laboratory department"}
        ]
        
        for dept in default_departments:
            db.departments.update_one(
                {"name": dept["name"]},
                {"$set": dept},
                upsert=True
            )
        
        # Insert admin user (password: admin123)
        from utils.auth import hash_password
        admin_user = {
            "username": "admin",
            "password": hash_password("admin123"),
            "full_name": "Administrator",
            "role": "admin",
            "department": "Klaster Manajemen",
            "created_at": datetime.utcnow(),
            "is_active": True,
            "last_login": None
        }
        
        db.users.update_one(
            {"username": "admin"},
            {"$set": admin_user},
            upsert=True
        )
        
        logger.info("Database initialization completed successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

# Real-time functions
def get_realtime_notifications(user_id: str, limit: int = 10):
    """Get real-time notifications for user"""
    try:
        db = MongoDBConnection.get_database()
        notifications = db.notifications.find(
            {"user_id": user_id, "is_read": False},
            sort=[("created_at", DESCENDING)]
        ).limit(limit)
        
        return list(notifications)
    except Exception as e:
        logger.error(f"Error getting notifications: {e}")
        return []

def create_notification(user_id: str, message: str, notification_type: str = "info"):
    """Create a notification for user"""
    try:
        db = MongoDBConnection.get_database()
        notification = {
            "user_id": user_id,
            "message": message,
            "type": notification_type,
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        
        result = db.notifications.insert_one(notification)
        return result.inserted_id
    except Exception as e:
        logger.error(f"Error creating notification: {e}")
        return None

# Dashboard functions
def get_stock_status():
    """Get overall stock status"""
    try:
        db = MongoDBConnection.get_database()
        
        # Get all items
        items = list(db.items.find({}))
        
        total_items = len(items)
        healthy_stock = len([item for item in items if item.get('current_stock', 0) > item.get('min_stock', 0)])
        low_stock = len([item for item in items if 0 < item.get('current_stock', 0) <= item.get('min_stock', 0)])
        out_of_stock = len([item for item in items if item.get('current_stock', 0) == 0])
        
        return {
            'total_items': total_items,
            'healthy_stock': healthy_stock,
            'low_stock': low_stock,
            'out_of_stock': out_of_stock
        }
    except Exception as e:
        logger.error(f"Error getting stock status: {e}")
        return {'total_items': 0, 'healthy_stock': 0, 'low_stock': 0, 'out_of_stock': 0}

def get_items_low_stock(limit: int = 10):
    """Get items with low stock"""
    try:
        db = MongoDBConnection.get_database()
        
        low_stock_items = list(db.items.find({
            "$expr": {"$lte": ["$current_stock", "$min_stock"]}
        }).limit(limit))
        
        # Convert to DataFrame for easier processing
        df = pd.DataFrame(low_stock_items)
        if not df.empty:
            df['_id'] = df['_id'].astype(str)
        
        return df
    except Exception as e:
        logger.error(f"Error getting low stock items: {e}")
        return pd.DataFrame()

def get_recent_transactions(limit: int = 10):
    """Get recent inventory transactions"""
    try:
        db = MongoDBConnection.get_database()
        
        pipeline = [
            {
                "$lookup": {
                    "from": "items",
                    "localField": "item_id",
                    "foreignField": "_id",
                    "as": "item"
                }
            },
            {"$unwind": "$item"},
            {
                "$lookup": {
                    "from": "departments",
                    "localField": "from_department_id",
                    "foreignField": "_id",
                    "as": "from_department"
                }
            },
            {"$unwind": {"path": "$from_department", "preserveNullAndEmptyArrays": True}},
            {
                "$lookup": {
                    "from": "departments",
                    "localField": "to_department_id",
                    "foreignField": "_id",
                    "as": "to_department"
                }
            },
            {"$unwind": {"path": "$to_department", "preserveNullAndEmptyArrays": True}},
            {"$sort": {"transaction_date": -1}},
            {"$limit": limit},
            {
                "$project": {
                    "item_name": "$item.name",
                    "quantity": 1,
                    "transaction_type": 1,
                    "from_department": "$from_department.name",
                    "to_department": "$to_department.name",
                    "transaction_date": 1,
                    "notes": 1
                }
            }
        ]
        
        transactions = list(db.inventory_transactions.aggregate(pipeline))
        
        # Convert to DataFrame
        df = pd.DataFrame(transactions)
        if not df.empty:
            df['_id'] = df['_id'].astype(str) if '_id' in df.columns else None
        
        return df
    except Exception as e:
        logger.error(f"Error getting recent transactions: {e}")
        return pd.DataFrame()

def get_department_consumption(days: int = 30):
    """Get department consumption for the last N days"""
    try:
        db = MongoDBConnection.get_database()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {
                "$match": {
                    "transaction_date": {"$gte": start_date},
                    "transaction_type": {"$in": ["consumption", "transfer_out"]}
                }
            },
            {
                "$lookup": {
                    "from": "departments",
                    "localField": "from_department_id",
                    "foreignField": "_id",
                    "as": "department"
                }
            },
            {"$unwind": "$department"},
            {
                "$group": {
                    "_id": "$department.name",
                    "total_consumption": {"$sum": "$quantity"}
                }
            },
            {
                "$project": {
                    "department": "$_id",
                    "total_consumption": 1,
                    "_id": 0
                }
            },
            {"$sort": {"total_consumption": -1}}
        ]
        
        consumption = list(db.inventory_transactions.aggregate(pipeline))
        
        # Convert to DataFrame
        df = pd.DataFrame(consumption)
        return df
    except Exception as e:
        logger.error(f"Error getting department consumption: {e}")
        return pd.DataFrame()

def get_top_consumed_items(limit: int = 5, days: int = 30):
    """Get top consumed items in the last N days"""
    try:
        db = MongoDBConnection.get_database()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {
                "$match": {
                    "transaction_date": {"$gte": start_date},
                    "transaction_type": {"$in": ["consumption", "transfer_out"]}
                }
            },
            {
                "$lookup": {
                    "from": "items",
                    "localField": "item_id",
                    "foreignField": "_id",
                    "as": "item"
                }
            },
            {"$unwind": "$item"},
            {
                "$group": {
                    "_id": "$item.name",
                    "total_consumption": {"$sum": "$quantity"}
                }
            },
            {
                "$project": {
                    "item_name": "$_id",
                    "total_consumption": 1,
                    "_id": 0
                }
            },
            {"$sort": {"total_consumption": -1}},
            {"$limit": limit}
        ]
        
        top_items = list(db.inventory_transactions.aggregate(pipeline))
        
        # Convert to DataFrame
        df = pd.DataFrame(top_items)
        return df
    except Exception as e:
        logger.error(f"Error getting top consumed items: {e}")
        return pd.DataFrame()

# Real-time change stream monitoring
class ChangeStreamMonitor:
    """Monitor MongoDB change streams for real-time updates"""
    
    def __init__(self):
        self.db = MongoDBConnection.get_database()
        self.is_running = False
        self.change_streams = {}
    
    def start_monitoring(self, collection_name, callback):
        """Start monitoring changes in a collection"""
        if not REALTIME_SETTINGS['CHANGE_STREAM_ENABLED']:
            return
        
        try:
            collection = self.db[collection_name]
            change_stream = collection.watch()
            
            self.change_streams[collection_name] = change_stream
            self.is_running = True
            
            # Process changes in a separate thread
            import threading
            monitor_thread = threading.Thread(
                target=self._process_changes,
                args=(change_stream, callback),
                daemon=True
            )
            monitor_thread.start()
            
            logger.info(f"Started monitoring {collection_name} changes")
            
        except Exception as e:
            logger.error(f"Error starting change stream for {collection_name}: {e}")
    
    def _process_changes(self, change_stream, callback):
        """Process changes from the change stream"""
        try:
            for change in change_stream:
                if not self.is_running:
                    break
                
                # Call the callback function with the change
                callback(change)
                
        except Exception as e:
            logger.error(f"Error processing change stream: {e}")
    
    def stop_monitoring(self, collection_name=None):
        """Stop monitoring changes"""
        self.is_running = False
        
        if collection_name and collection_name in self.change_streams:
            self.change_streams[collection_name].close()
            del self.change_streams[collection_name]
        else:
            # Close all change streams
            for stream in self.change_streams.values():
                stream.close()
            self.change_streams.clear()
        
        logger.info("Stopped change stream monitoring")