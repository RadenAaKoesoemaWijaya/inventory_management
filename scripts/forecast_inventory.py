import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
# Before creating visualizations, ensure the static directory exists
import os
# After creating the forecast_results list and before using forecast_df
# Add this near the beginning of the script, after importing libraries but before processing data

# Create a list to store forecasting results
forecast_results = []


# After all items are processed, convert to DataFrame
forecast_df = pd.DataFrame(forecast_results)

# Create static directory if it doesn't exist
static_dir = 'c:/Users/koeso/OneDrive/Desktop/Inventory Management/static'
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

# Create a visualization of the forecast
plt.figure(figsize=(12, 8))
plt.bar(forecast_df['item_name'], forecast_df['projected_annual_consumption'])
plt.xticks(rotation=90)
plt.title('Projected Annual Consumption by Item')
plt.ylabel('Projected Consumption (units)')
plt.tight_layout()
plt.savefig(os.path.join(static_dir, 'forecast_chart.png'))

# Create a visualization of months to reorder
plt.figure(figsize=(12, 8))
plt.bar(forecast_df['item_name'], forecast_df['months_to_min_stock'])
plt.xticks(rotation=90)
plt.title('Months Until Reorder by Item')
plt.ylabel('Months')
plt.tight_layout()
plt.savefig(os.path.join(static_dir, 'reorder_chart.png'))

# Print summary
print("Forecasting completed successfully!")
print(f"Total items analyzed: {len(forecast_df)}")
print("\nItems requiring reorder within 3 months:")
reorder_soon = forecast_df[forecast_df['months_to_min_stock'] <= 3].sort_values('months_to_min_stock')
if not reorder_soon.empty:
    for _, item in reorder_soon.iterrows():
        print(f"- {item['item_name']}: {item['months_to_min_stock']} months until minimum stock, order {item['recommended_order_qty']} {item['unit']}")
else:
    print("None")

# Also ensure the reports directory exists for Excel export
reports_dir = 'c:/Users/koeso/OneDrive/Desktop/Inventory Management/reports'
if not os.path.exists(reports_dir):
    os.makedirs(reports_dir)

# Export to Excel
forecast_df.to_excel(os.path.join(reports_dir, 'inventory_forecast.xlsx'), index=False)

# Close connection
conn.close()

print("\nForecast data has been saved to the database and exported to Excel.")
print("Visualization charts have been saved to the static folder.")