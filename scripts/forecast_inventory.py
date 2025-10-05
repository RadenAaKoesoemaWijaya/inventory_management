import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys
import warnings
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import PolynomialFeatures
import statsmodels.api as sm

# Suppress warnings for cleaner output
warnings.filterwarnings('ignore')

# Add parent directory to path to import utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import MongoDBConnection

def calculate_trend_forecast(historical_data, periods=12):
    """Calculate trend-based forecast using linear regression"""
    try:
        if len(historical_data) < 3:
            return None
            
        # Prepare data for regression
        X = np.arange(len(historical_data)).reshape(-1, 1)
        y = historical_data.values
        
        # Fit linear regression
        model = LinearRegression()
        model.fit(X, y)
        
        # Predict future values
        future_X = np.arange(len(historical_data), len(historical_data) + periods).reshape(-1, 1)
        predictions = model.predict(future_X)
        
        # Ensure non-negative predictions
        predictions = np.maximum(predictions, 0)
        
        return np.sum(predictions)
    except Exception:
        return None

def calculate_seasonal_forecast(historical_data, periods=12):
    """Calculate seasonal forecast using moving averages"""
    try:
        if len(historical_data) < 12:
            return None
            
        # Calculate monthly averages
        monthly_data = historical_data.groupby(historical_data.index.month).mean()
        
        # Calculate trend
        if len(historical_data) >= 24:
            recent_avg = historical_data.tail(12).mean()
            older_avg = historical_data.head(12).mean()
            trend_factor = recent_avg / max(older_avg, 1)
        else:
            trend_factor = 1.1  # Default growth
            
        # Project future consumption
        projected_monthly = monthly_data * trend_factor
        
        return np.sum(projected_monthly)
    except Exception:
        return None

def calculate_exponential_smoothing_forecast(historical_data, alpha=0.3, periods=12):
    """Calculate forecast using exponential smoothing"""
    try:
        if len(historical_data) < 2:
            return None
            
        # Simple exponential smoothing
        smoothed = [historical_data.iloc[0]]
        for value in historical_data.iloc[1:]:
            smoothed.append(alpha * value + (1 - alpha) * smoothed[-1])
        
        # Project future values
        last_smoothed = smoothed[-1]
        return last_smoothed * periods
    except Exception:
        return None

def run_forecast():
    """Run optimized inventory forecasting analysis with multiple prediction methods"""
    
    # Create directories for output
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reports')
    
    os.makedirs(static_dir, exist_ok=True)
    os.makedirs(reports_dir, exist_ok=True)
    
    # Get database connection
    db = MongoDBConnection()
    
    try:
        # Get all items with transaction history
        items_collection = db.get_collection('items')
        transactions_collection = db.get_collection('inventory_transactions')
        
        # Get all items
        items_data = list(items_collection.find({}))
        
        # Count transactions for each item
        for item in items_data:
            transaction_count = transactions_collection.count_documents({
                'item_id': item['_id'],
                'transaction_type': 'issue'
            })
            item['transaction_count'] = transaction_count
        
        items_df = pd.DataFrame(items_data)
        
        if items_df.empty:
            print("No items found in database")
            return
        
        if items_df.empty:
            print("No items found in database")
            return
        
        # Get forecast collection
        forecast_collection = db.get_collection('inventory_forecast')
        
        # Clear old forecast data
        forecast_collection.delete_many({})
        
        # Process each item with optimized forecasting
        forecast_results = []
        processed_count = 0
        
        for _, item in items_df.iterrows():
            item_id = item['id']
            item_name = item['name']
            current_stock = item['current_stock']
            min_stock = item['min_stock']
            unit = item['unit']
            transaction_count = item['transaction_count']
            
            # Skip items with no transaction history
            if transaction_count == 0:
                # Use minimum stock as baseline for new items
                projected_annual = max(min_stock * 2, 10)  # Default for new items
                forecast_method = "minimum_baseline"
                confidence_level = 0.3
            else:
                # Get detailed consumption history
                two_years_ago = datetime.now() - timedelta(days=730)
                
                # Get consumption data from MongoDB
                consumption_data = list(transactions_collection.find({
                    'item_id': item_id,
                    'transaction_type': 'issue',
                    'transaction_date': {'$gte': two_years_ago}
                }, {'transaction_date': 1, 'quantity': 1}).sort('transaction_date', 1))
                
                consumption_data = pd.DataFrame(consumption_data)
                
                if consumption_data.empty:
                    projected_annual = max(min_stock * 2, 10)
                    forecast_method = "minimum_baseline"
                    confidence_level = 0.3
                else:
                    # Create monthly consumption series
                    consumption_data['transaction_date'] = pd.to_datetime(consumption_data['transaction_date'])
                    monthly_consumption = consumption_data.groupby(
                        pd.Grouper(key='transaction_date', freq='M')
                    )['quantity'].sum().fillna(0)
                    
                    # Calculate actual annual consumption
                    annual_consumption = monthly_consumption.sum()
                    
                    # Apply multiple forecasting methods
                    methods = []
                    
                    # Method 1: Linear trend
                    trend_forecast = calculate_trend_forecast(monthly_consumption)
                    if trend_forecast:
                        methods.append(('trend', trend_forecast))
                    
                    # Method 2: Seasonal pattern
                    seasonal_forecast = calculate_seasonal_forecast(monthly_consumption)
                    if seasonal_forecast:
                        methods.append(('seasonal', seasonal_forecast))
                    
                    # Method 3: Exponential smoothing
                    exp_smooth_forecast = calculate_exponential_smoothing_forecast(monthly_consumption)
                    if exp_smooth_forecast:
                        methods.append(('exponential', exp_smooth_forecast))
                    
                    # Method 4: Simple average (fallback)
                    avg_monthly = monthly_consumption.mean()
                    avg_forecast = avg_monthly * 12 * 1.1  # 10% growth buffer
                    methods.append(('average', avg_forecast))
                    
                    # Select best method based on data quality
                    if len(monthly_consumption) >= 24:
                        # Use weighted combination for longer history
                        weights = [0.4, 0.3, 0.2, 0.1]  # Trend gets highest weight
                        weighted_forecast = sum(w * f for (_, f), w in zip(methods, weights))
                        projected_annual = weighted_forecast
                        forecast_method = "weighted_combination"
                        confidence_level = 0.85
                    elif len(monthly_consumption) >= 12:
                        # Use seasonal for 1+ year data
                        projected_annual = seasonal_forecast or avg_forecast
                        forecast_method = "seasonal_average"
                        confidence_level = 0.75
                    else:
                        # Use simple average for limited data
                        projected_annual = avg_forecast
                        forecast_method = "simple_average"
                        confidence_level = 0.6
            
            # Calculate consumption rate
            if current_stock > 0:
                annual_consumption_rate = projected_annual / max(current_stock, 1)
            else:
                annual_consumption_rate = 0
            
            # Monthly projected consumption
            monthly_projected = projected_annual / 12
            
            # Calculate months until minimum stock
            if monthly_projected > 0:
                months_to_min = max((current_stock - min_stock) / monthly_projected, 0)
            else:
                months_to_min = 999
            
            # Calculate reorder date with buffer
            if months_to_min <= 12:
                # Add safety buffer based on confidence level
                buffer_days = max(7, int((1 - confidence_level) * 30))
                reorder_date = datetime.now() + timedelta(days=int(months_to_min * 30) + buffer_days)
            else:
                reorder_date = None
            
            # Calculate recommended order quantity with optimization
            if months_to_min <= 6:  # Extended reorder window
                # Base calculation
                base_qty = int(projected_annual * (6 - months_to_min) / 12)
                
                # Adjust based on current stock vs min stock
                stock_adjustment = max(min_stock - current_stock, 0)
                
                # Economic order quantity consideration
                if monthly_projected > 0:
                    # EOQ = sqrt(2 * D * S / H) where D=demand, S=ordering cost, H=holding cost
                    # Simplified EOQ with estimated values
                    eoq = int(np.sqrt(2 * projected_annual * 50 / (projected_annual * 0.2)))
                    optimal_qty = max(base_qty, stock_adjustment, eoq)
                else:
                    optimal_qty = max(base_qty, stock_adjustment)
                
                recommended_qty = max(optimal_qty, min_stock)
            else:
                recommended_qty = 0
            
            # Ensure recommended quantity is reasonable
            if recommended_qty > 0:
                recommended_qty = max(recommended_qty, min_stock)
                if current_stock > 0:
                    recommended_qty = min(recommended_qty, current_stock * 3)  # Cap at 3x current stock
            
            # Store result with enhanced metadata
            forecast_result = {
                'item_id': item_id,
                'item_name': item_name,
                'category': item['category'],
                'current_stock': current_stock,
                'min_stock': min_stock,
                'unit': unit,
                'annual_consumption_rate': annual_consumption_rate,
                'projected_annual_consumption': projected_annual,
                'monthly_projected_consumption': monthly_projected,
                'months_to_min_stock': months_to_min,
                'reorder_date': reorder_date,
                'recommended_order_qty': recommended_qty,
                'confidence_level': confidence_level,
                'forecast_method': forecast_method,
                'forecast_date': datetime.now()
            }
            
            forecast_results.append(forecast_result)
            
            processed_count += 1
            
            # Progress indicator
            if processed_count % 10 == 0:
                print(f"Processed {processed_count} items...")
        
        # Insert all forecast results into MongoDB
        if forecast_results:
            forecast_collection.insert_many(forecast_results)
            print(f"Successfully inserted {len(forecast_results)} forecast records")
        
        # Create DataFrame for analysis
        forecast_df = pd.DataFrame(forecast_results)
        
        if not forecast_df.empty:
            # Generate comprehensive summary
            print("=" * 60)
            print("INVENTORY FORECASTING SUMMARY")
            print("=" * 60)
            print(f"Total items analyzed: {len(forecast_df)}")
            print(f"Items with transaction history: {len(forecast_df[forecast_df['forecast_method'] != 'minimum_baseline'])}")
            print(f"Items using advanced forecasting: {len(forecast_df[forecast_df['confidence_level'] >= 0.6])}")
            
            # High priority items
            urgent_items = forecast_df[forecast_df['months_to_min_stock'] <= 2]
            if not urgent_items.empty:
                print(f"\n🚨 URGENT REORDER NEEDED (≤ 2 months): {len(urgent_items)} items")
                for _, item in urgent_items.iterrows():
                    print(f"   • {item['item_name']}: {item['months_to_min_stock']:.1f} months, "
                          f"order {item['recommended_order_qty']} {item['unit']} "
                          f"(confidence: {item['confidence_level']:.0%})")
            
            # Medium priority items
            medium_items = forecast_df[(forecast_df['months_to_min_stock'] > 2) & 
                                     (forecast_df['months_to_min_stock'] <= 6)]
            if not medium_items.empty:
                print(f"\n⚠️  MEDIUM PRIORITY (2-6 months): {len(medium_items)} items")
                for _, item in medium_items.head(5).iterrows():
                    print(f"   • {item['item_name']}: {item['months_to_min_stock']:.1f} months")
            
            # Category analysis
            print(f"\n📊 FORECASTING METHODS USED:")
            method_counts = forecast_df['forecast_method'].value_counts()
            for method, count in method_counts.items():
                print(f"   • {method.replace('_', ' ').title()}: {count} items")
            
            # Export detailed results
            forecast_df.to_excel(os.path.join(reports_dir, 'inventory_forecast_detailed.xlsx'), 
                               index=False)
            
            # Create simplified summary
            summary_df = forecast_df[['item_name', 'category', 'current_stock', 'min_stock', 
                                    'months_to_min_stock', 'recommended_order_qty', 
                                    'confidence_level', 'forecast_method']]
            summary_df.to_excel(os.path.join(reports_dir, 'inventory_forecast_summary.xlsx'), 
                              index=False)
            
            print(f"\n✅ Forecasting completed successfully!")
            print(f"   Detailed report: {os.path.join(reports_dir, 'inventory_forecast_detailed.xlsx')}")
            print(f"   Summary report: {os.path.join(reports_dir, 'inventory_forecast_summary.xlsx')}")
            
        else:
            print("❌ No forecast data generated")
            
    except Exception as e:
        print(f"❌ Error during forecasting: {str(e)}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    run_forecast()