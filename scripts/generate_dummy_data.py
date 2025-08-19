import sqlite3
import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta
import os

# Create data directory if it doesn't exist
data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
os.makedirs(data_dir, exist_ok=True)

# Connect to the database using relative path
db_path = os.path.join(data_dir, 'inventory.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Define healthcare consumable items
items = [
    {"name": "Masker Bedah 3-Ply", "category": "Alat Pelindung Diri", "unit": "pcs"},
    {"name": "Masker N95", "category": "Alat Pelindung Diri", "unit": "pcs"},
    {"name": "Sarung Tangan Latex (S)", "category": "Alat Pelindung Diri", "unit": "pcs"},
    {"name": "Sarung Tangan Latex (M)", "category": "Alat Pelindung Diri", "unit": "pcs"},
    {"name": "Sarung Tangan Latex (L)", "category": "Alat Pelindung Diri", "unit": "pcs"},
    {"name": "Sarung Tangan Steril (S)", "category": "Alat Pelindung Diri", "unit": "pcs"},
    {"name": "Sarung Tangan Steril (M)", "category": "Alat Pelindung Diri", "unit": "pcs"},
    {"name": "Sarung Tangan Steril (L)", "category": "Alat Pelindung Diri", "unit": "pcs"},
    {"name": "Spuit 1 ml", "category": "Alat Suntik", "unit": "pcs"},
    {"name": "Spuit 3 ml", "category": "Alat Suntik", "unit": "pcs"},
    {"name": "Spuit 5 ml", "category": "Alat Suntik", "unit": "pcs"},
    {"name": "Spuit 10 ml", "category": "Alat Suntik", "unit": "pcs"},
    {"name": "Spuit 20 ml", "category": "Alat Suntik", "unit": "pcs"},
    {"name": "Kassa Steril 10x10 cm", "category": "Pembalut", "unit": "pcs"},
    {"name": "Kassa Steril 5x5 cm", "category": "Pembalut", "unit": "pcs"},
    {"name": "Plester Kertas 2.5 cm", "category": "Pembalut", "unit": "roll"},
    {"name": "Plester Kertas 5 cm", "category": "Pembalut", "unit": "roll"},
    {"name": "Plester Transparan", "category": "Pembalut", "unit": "roll"},
    {"name": "Kapas 250 gr", "category": "Pembalut", "unit": "pack"},
    {"name": "Alkohol Swab", "category": "Antiseptik", "unit": "pcs"},
    {"name": "Povidone Iodine 60 ml", "category": "Antiseptik", "unit": "botol"},
    {"name": "Alkohol 70% 100 ml", "category": "Antiseptik", "unit": "botol"},
    {"name": "Alkohol 70% 1 L", "category": "Antiseptik", "unit": "botol"},
    {"name": "Rapid Test Antigen", "category": "Diagnostik", "unit": "pcs"},
    {"name": "Rapid Test Antibodi", "category": "Diagnostik", "unit": "pcs"},
    {"name": "Lancet", "category": "Diagnostik", "unit": "pcs"},
    {"name": "Strip Gula Darah", "category": "Diagnostik", "unit": "pcs"},
    {"name": "Infus Set", "category": "Alat Infus", "unit": "pcs"},
    {"name": "Cairan Infus NaCl 0.9% 500 ml", "category": "Alat Infus", "unit": "botol"},
    {"name": "Cairan Infus RL 500 ml", "category": "Alat Infus", "unit": "botol"},
    {"name": "Cairan Infus D5 500 ml", "category": "Alat Infus", "unit": "botol"},
    {"name": "Branul 18G", "category": "Alat Infus", "unit": "pcs"},
    {"name": "Branul 20G", "category": "Alat Infus", "unit": "pcs"},
    {"name": "Branul 22G", "category": "Alat Infus", "unit": "pcs"},
    {"name": "Branul 24G", "category": "Alat Infus", "unit": "pcs"}
]

# Generate random stock levels between 200 and 3500
for item in items:
    item["current_stock"] = random.randint(200, 3500)
    item["min_stock"] = int(item["current_stock"] * 0.15)  # Set minimum stock at 15% of current stock

# Insert departments if they don't exist - Updated to cluster-based departments
departments = [
    {"name": "Management"},
    {"name": "Mother and Child"},
    {"name": "Productive and Elderly Age"},
    {"name": "Infectious Disease Prevention"},
    {"name": "Cross-Cluster (Pharmacy)"},
    {"name": "Cross-Cluster (Laboratory)"},
    {"name": "Cross-Cluster (Dental Health)"},
    {"name": "Cross-Cluster (Emergency Services)"}
]

# Check if departments table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='departments'")
if not cursor.fetchone():
    cursor.execute('''
    CREATE TABLE departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    )
    ''')

# Insert departments
for dept in departments:
    try:
        cursor.execute("INSERT INTO departments (name) VALUES (?)", (dept["name"],))
    except sqlite3.IntegrityError:
        pass  # Department already exists

# Check if items table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
if not cursor.fetchone():
    cursor.execute('''
    CREATE TABLE items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        category TEXT NOT NULL,
        current_stock INTEGER NOT NULL,
        min_stock INTEGER NOT NULL,
        unit TEXT NOT NULL
    )
    ''')

# Insert items
for item in items:
    try:
        cursor.execute(
            "INSERT INTO items (name, category, current_stock, min_stock, unit) VALUES (?, ?, ?, ?, ?)",
            (item["name"], item["category"], item["current_stock"], item["min_stock"], item["unit"])
        )
    except sqlite3.IntegrityError:
        # Update if item already exists
        cursor.execute(
            "UPDATE items SET category=?, current_stock=?, min_stock=?, unit=? WHERE name=?",
            (item["category"], item["current_stock"], item["min_stock"], item["unit"], item["name"])
        )

# Check if inventory_transactions table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_transactions'")
if not cursor.fetchone():
    cursor.execute('''
    CREATE TABLE inventory_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        transaction_date TIMESTAMP NOT NULL,
        quantity INTEGER NOT NULL,
        transaction_type TEXT NOT NULL,
        from_department_id INTEGER,
        to_department_id INTEGER,
        created_by INTEGER,
        notes TEXT,
        FOREIGN KEY (item_id) REFERENCES items (id),
        FOREIGN KEY (from_department_id) REFERENCES departments (id),
        FOREIGN KEY (to_department_id) REFERENCES departments (id)
    )
    ''')

# Generate transaction history for the past year
start_date = datetime.now() - timedelta(days=365)
end_date = datetime.now()

# Get item IDs
cursor.execute("SELECT id FROM items")
item_ids = [row[0] for row in cursor.fetchall()]

# Get department IDs
cursor.execute("SELECT id FROM departments")
dept_ids = [row[0] for row in cursor.fetchall()]

# Generate transactions
transactions = []
current_date = start_date

while current_date <= end_date:
    # Number of transactions for this day (random between 5-15)
    num_transactions = random.randint(5, 15)
    
    for _ in range(num_transactions):
        item_id = random.choice(item_ids)
        
        # Get item details
        cursor.execute("SELECT current_stock, name FROM items WHERE id = ?", (item_id,))
        item_stock, item_name = cursor.fetchone()
        
        # Determine transaction type (80% issues, 20% receives)
        transaction_type = "issue" if random.random() < 0.8 else "receive"
        
        if transaction_type == "issue":
            # Issue quantity between 1% and 5% of current stock
            quantity = int(item_stock * random.uniform(0.01, 0.05))
            from_dept = 1  # Management (updated from Farmasi)
            to_dept = random.choice([dept for dept in dept_ids if dept != 1])
            notes = f"Distribusi rutin {item_name}"
        else:
            # Receive quantity between 10% and 30% of current stock
            quantity = int(item_stock * random.uniform(0.1, 0.3))
            from_dept = None
            to_dept = 1  # Management (updated from Farmasi)
            notes = f"Penerimaan stok {item_name}"
        
        # Ensure quantity is at least 1
        quantity = max(1, quantity)
        
        # Add transaction
        transaction_date = current_date + timedelta(hours=random.randint(8, 17), minutes=random.randint(0, 59))
        
        transactions.append({
            "item_id": item_id,
            "transaction_date": transaction_date.strftime("%Y-%m-%d %H:%M:%S"),
            "quantity": quantity,
            "transaction_type": transaction_type,
            "from_department_id": from_dept,
            "to_department_id": to_dept,
            "created_by": 1,  # Assuming user ID 1 exists
            "notes": notes
        })
    
    # Move to next day
    current_date += timedelta(days=1)

# Insert transactions
for transaction in transactions:
    cursor.execute(
        """
        INSERT INTO inventory_transactions 
        (item_id, transaction_date, quantity, transaction_type, from_department_id, to_department_id, created_by, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction["item_id"], 
            transaction["transaction_date"], 
            transaction["quantity"], 
            transaction["transaction_type"],
            transaction["from_department_id"], 
            transaction["to_department_id"], 
            transaction["created_by"],
            transaction["notes"]
        )
    )

# Commit changes and close connection
conn.commit()
conn.close()

print("Dummy data has been successfully generated and inserted into the database.")