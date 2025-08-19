import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import sys

# Add parent directory to path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import get_db_connection

def run_forecast():
    """Run inventory forecasting analysis"""
    
    # Create directories for output
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reports')
    
    os.makedirs(static_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)
    
    # Get database connection
    conn = get_db_connection()
    
    try:
        # Get all items
        items_df = pd.read_sql_query("""
            SELECT id, name, category, current_stock, min_stock, unit 
            FROM items 
            ORDER BY name
        """, conn)
        
        if items_df.empty:
            print("No items found in database")
            return
        
        # Create inventory_forecast table if it doesn't exist
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory_forecast (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                forecast_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                annual_consumption_rate REAL,
                projected_annual_consumption REAL,
                monthly_projected_consumption REAL,
                months_to_min_stock REAL,
                reorder_date DATE,
                recommended_order_qty INTEGER,
                FOREIGN KEY (item_id) REFERENCES items (id)
            )
        ''')
        
        # Clear old forecast data
        cursor.execute("DELETE FROM inventory_forecast")
        
        # Process each item
        forecast_results = []
        
        for _, item in items_df.iterrows():
            item_id = item['id']
            item_name = item['name']
            current_stock = item['current_stock']
            min_stock = item['min_stock']
            unit = item['unit']
            
            # Get consumption history (last 12 months)
            one_year_ago = datetime.now() - timedelta(days=365)
            
            consumption_query = '''
                SELECT SUM(quantity) as total_consumption
                FROM inventory_transactions 
                WHERE item_id = ? 
                AND transaction_type = 'issue' 
                AND transaction_date >= ?
            '''
            
            consumption_result = pd.read_sql_query(
                consumption_query, 
                conn, 
                params=(item_id, one_year_ago.strftime('%Y-%m-%d'))
            )
            
            annual_consumption = float(consumption_result.iloc[0]['total_consumption'] or 0)
            
            # Calculate consumption rate based on current stock
            if current_stock > 0:
                consumption_rate = annual_consumption / max(current_stock, 1)
            else:
                consumption_rate = 0
            
            # Projected annual consumption
            if consumption_rate > 0:
                projected_annual = annual_consumption * 1.1  # 10% growth buffer
            else:
                projected_annual = min_stock * 2  # Default projection
            
            # Monthly projected consumption
            monthly_projected = projected_annual / 12
            
            # Calculate months until minimum stock
            if monthly_projected > 0:
                months_to_min = max((current_stock - min_stock) / monthly_projected, 0)
            else:
                months_to_min = 999  # No consumption, no reorder needed
            
            # Calculate reorder date
            if months_to_min <= 12:
                reorder_date = datetime.now() + timedelta(days=int(months_to_min * 30))
            else:
                reorder_date = None
            
            # Calculate recommended order quantity
            if months_to_min <= 3:  # If reorder needed within 3 months
                recommended_qty = max(int(projected_annual * 0.25), min_stock - current_stock)
            else:
                recommended_qty = 0
            
            # Store result
            forecast_result = {
                'item_id': item_id,
                'item_name': item_name,
                'category': item['category'],
                'current_stock': current_stock,
                'min_stock': min_stock,
                'unit': unit,
                'annual_consumption_rate': consumption_rate,
                'projected_annual_consumption': projected_annual,
                'monthly_projected_consumption': monthly_projected,
                'months_to_min_stock': months_to_min,
                'reorder_date': reorder_date.strftime('%Y-%m-%d') if reorder_date else None,
                'recommended_order_qty': recommended_qty
            }
            
            forecast_results.append(forecast_result)
            
            # Insert into database
            cursor.execute('''
                INSERT INTO inventory_forecast 
                (item_id, annual_consumption_rate, projected_annual_consumption, 
                 monthly_projected_consumption, months_to_min_stock, reorder_date, 
                 recommended_order_qty)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                item_id, consumption_rate, projected_annual, monthly_projected,
                months_to_min, reorder_date, recommended_qty
            ))
        
        # Commit changes
        conn.commit()
        
        # Create DataFrame for visualizations
        forecast_df = pd.DataFrame(forecast_results)
        
        if not forecast_df.empty:
            # Create visualizations
            plt.style.use('seaborn-v0_8')
            
            # Chart 1: Projected Annual Consumption
            top_consumption = forecast_df.nlargest(15, 'projected_annual_consumption')
            plt.figure(figsize=(15, 8))
            plt.bar(range(len(top_consumption)), top_consumption['projected_annual_consumption'])
            plt.xticks(range(len(top_consumption)), top_consumption['item_name'], rotation=45, ha='right')
            plt.title('Top 15 Items by Projected Annual Consumption')
            plt.ylabel('Projected Consumption')
            plt.tight_layout()
            plt.savefig(os.path.join(static_dir, 'forecast_chart.png'))
            plt.close()
            
            # Chart 2: Months to Reorder
            reorder_needed = forecast_df[forecast_df['months_to_min_stock'] <= 12]
            if not reorder_needed.empty:
                reorder_needed = reorder_needed.sort_values('months_to_min_stock')
                plt.figure(figsize=(15, 8))
                plt.bar(range(len(reorder_needed)), reorder_needed['months_to_min_stock'])
                plt.xticks(range(len(reorder_needed)), reorder_needed['item_name'], rotation=45, ha='right')
                plt.title('Items Requiring Reorder within 12 Months')
                plt.ylabel('Months to Minimum Stock')
                plt.tight_layout()
                plt.savefig(os.path.join(static_dir, 'reorder_chart.png'))
                plt.close()
            
            # Export to Excel
            forecast_df.to_excel(os.path.join(reports_dir, 'inventory_forecast.xlsx'), index=False)
            
            # Print summary
            print("Forecasting completed successfully!")
            print(f"Total items analyzed: {len(forecast_df)}")
            
            reorder_soon = forecast_df[forecast_df['months_to_min_stock'] <= 3]
            if not reorder_soon.empty:
                print("\nItems requiring reorder within 3 months:")
                for _, item in reorder_soon.iterrows():
                    print(f"- {item['item_name']}: {item['months_to_min_stock']:.1f} months, order {item['recommended_order_qty']} {item['unit']}")
            else:
                print("\nNo items require immediate reorder")
                
        else:
            print("No forecast data generated")
            
    except Exception as e:
        print(f"Error during forecasting: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    run_forecast()