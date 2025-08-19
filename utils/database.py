import sqlite3
import pandas as pd
import os
from datetime import datetime

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'inventory.db')

# Ensure data directory exists
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Perbaikan path database menggunakan path absolut
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'inventory.db')

def get_db_connection():
    """Get a connection to the database"""
    try:
        # Pastikan direktori database ada
        db_dir = os.path.dirname(DB_PATH)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
        # Buat koneksi dengan timeout yang lebih lama
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        
        # Aktifkan foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        
        return conn
    except sqlite3.Error as e:
        print(f"Database connection error: {e}")
        raise

# In the init_db function, we need to modify the departments table creation or data insertion

def init_db():
    """Initialize the database with required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL,
        department TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create items table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        category TEXT NOT NULL,
        unit TEXT NOT NULL,
        min_stock INTEGER NOT NULL,
        current_stock INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Create departments/units table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Check if departments table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='departments'")
    if not cursor.fetchone():
        # Create departments table
        cursor.execute('''
        CREATE TABLE departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        )
        ''')
        
        # Insert initial departments
        departments = [
            ('Farmasi', 'Departemen yang mengelola obat-obatan dan bahan medis'),
            ('Rawat Inap', 'Departemen untuk pasien yang memerlukan perawatan menginap'),
            ('Rawat Jalan', 'Departemen untuk pasien yang tidak memerlukan perawatan menginap'),
            ('IGD', 'Instalasi Gawat Darurat untuk penanganan kasus darurat'),
            ('Laboratorium', 'Departemen untuk pemeriksaan laboratorium'),
            ('Radiologi', 'Departemen untuk pemeriksaan radiologi'),
            ('Kamar Operasi', 'Departemen untuk tindakan operasi'),
            ('Administrasi', 'Departemen yang mengelola administrasi rumah sakit')
        ]
        
        cursor.executemany('INSERT INTO departments (name, description) VALUES (?, ?)', departments)
    else:
        # Check if description column exists in departments table
        cursor.execute("PRAGMA table_info(departments)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'description' not in columns:
            # Add description column if it doesn't exist
            cursor.execute('ALTER TABLE departments ADD COLUMN description TEXT')
    
    # Create inventory transactions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS inventory_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        transaction_type TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        from_department_id INTEGER,
        to_department_id INTEGER,
        transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        notes TEXT,
        created_by INTEGER NOT NULL,
        FOREIGN KEY (item_id) REFERENCES items (id),
        FOREIGN KEY (from_department_id) REFERENCES departments (id),
        FOREIGN KEY (to_department_id) REFERENCES departments (id),
        FOREIGN KEY (created_by) REFERENCES users (id)
    )
    ''')
    
    # Create item requests table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS item_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fulfilled_date TIMESTAMP,
        requested_by INTEGER NOT NULL,
        fulfilled_by INTEGER,
        notes TEXT,
        FOREIGN KEY (department_id) REFERENCES departments (id),
        FOREIGN KEY (item_id) REFERENCES items (id),
        FOREIGN KEY (requested_by) REFERENCES users (id),
        FOREIGN KEY (fulfilled_by) REFERENCES users (id)
    )
    ''')
    
    # Insert default departments
    departments = [
        ('Warehouse', 'Main storage facility'),
        ('Emergency Room', 'ER department'),
        ('Surgery', 'Surgery department'),
        ('Pediatrics', 'Pediatrics department'),
        ('Pharmacy', 'Pharmacy department'),
        ('Laboratory', 'Laboratory department'),
        ('Radiology', 'Radiology department'),
        ('Procurement', 'Procurement department')
    ]
    
    cursor.executemany(
        'INSERT OR IGNORE INTO departments (name, description) VALUES (?, ?)',
        departments
    )
    
    # Insert admin user (password: admin123)
    cursor.execute(
        'INSERT OR IGNORE INTO users (username, password, full_name, role) VALUES (?, ?, ?, ?)',
        ('admin', '$2b$12$tOj0tXHwCYfJWj3xD7UeWe9HrT8NwwpK.VqbKXPkTGBGBOT9Ky5rK', 'Administrator', 'admin')
    )
    
    conn.commit()
    conn.close()

def get_items_low_stock():
    """Get items with stock below minimum level"""
    conn = get_db_connection()
    low_stock_items = pd.read_sql_query(
        'SELECT * FROM items WHERE current_stock <= min_stock',
        conn
    )
    conn.close()
    return low_stock_items

def get_recent_transactions(limit=10):
    """Get recent inventory transactions"""
    conn = get_db_connection()
    query = '''
    SELECT t.id, i.name as item_name, t.quantity, t.transaction_type,
           d1.name as from_department, d2.name as to_department,
           u.full_name as created_by, t.transaction_date, t.notes
    FROM inventory_transactions t
    JOIN items i ON t.item_id = i.id
    JOIN users u ON t.created_by = u.id
    LEFT JOIN departments d1 ON t.from_department_id = d1.id
    LEFT JOIN departments d2 ON t.to_department_id = d2.id
    ORDER BY t.transaction_date DESC
    LIMIT ?
    '''
    transactions = pd.read_sql_query(query, conn, params=(limit,))
    conn.close()
    return transactions

def get_item_history(item_id, start_date=None, end_date=None):
    """Get transaction history for a specific item"""
    conn = get_db_connection()
    
    query_params = [item_id]
    query = '''
    SELECT t.id, i.name as item_name, t.quantity, t.transaction_type,
           d1.name as from_department, d2.name as to_department,
           u.full_name as created_by, t.transaction_date, t.notes
    FROM inventory_transactions t
    JOIN items i ON t.item_id = i.id
    JOIN users u ON t.created_by = u.id
    LEFT JOIN departments d1 ON t.from_department_id = d1.id
    LEFT JOIN departments d2 ON t.to_department_id = d2.id
    WHERE t.item_id = ?
    '''
    
    if start_date:
        query += ' AND t.transaction_date >= ?'
        query_params.append(start_date)
    
    if end_date:
        query += ' AND t.transaction_date <= ?'
        query_params.append(end_date)
    
    query += ' ORDER BY t.transaction_date DESC'
    
    history = pd.read_sql_query(query, conn, params=query_params)
    conn.close()
    return history

def get_monthly_consumption(item_id=None, department_id=None, year=None):
    """Get monthly consumption data for forecasting"""
    conn = get_db_connection()
    
    query_params = []
    query = '''
    SELECT 
        strftime('%Y-%m', transaction_date) as month,
        item_id,
        i.name as item_name,
        SUM(CASE WHEN transaction_type = 'issue' THEN quantity ELSE 0 END) as consumption
    FROM inventory_transactions t
    JOIN items i ON t.item_id = i.id
    WHERE transaction_type = 'issue'
    '''
    
    if item_id:
        query += ' AND item_id = ?'
        query_params.append(item_id)
    
    if department_id:
        query += ' AND to_department_id = ?'
        query_params.append(department_id)
    
    if year:
        query += ' AND strftime("%Y", transaction_date) = ?'
        query_params.append(str(year))
    
    query += ' GROUP BY strftime("%Y-%m", transaction_date), item_id'
    
    consumption_data = pd.read_sql_query(query, conn, params=query_params)
    conn.close()
    return consumption_data

# Initialize the database when this module is imported
init_db()