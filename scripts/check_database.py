import os
import sqlite3
import sys

# Tambahkan path root project ke sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_db_connection, DB_PATH

def check_database():
    """Check if database exists and is accessible"""
    print(f"Checking database at: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database file not found at {DB_PATH}")
        return False
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if essential tables exist
        tables = ['users', 'items', 'departments', 'inventory_transactions']
        missing_tables = []
        
        for table in tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not cursor.fetchone():
                missing_tables.append(table)
        
        if missing_tables:
            print(f"ERROR: Missing tables: {', '.join(missing_tables)}")
            return False
            
        print("Database connection successful!")
        print("Essential tables found.")
        
        # Get table counts
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"Table '{table}' has {count} records")
            
        conn.close()
        return True
        
    except sqlite3.Error as e:
        print(f"ERROR: Database connection failed: {e}")
        return False

if __name__ == "__main__":
    check_database()