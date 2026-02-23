import pandas as pd
import numpy as np
from datetime import datetime, timedelta

np.random.seed(42)  # for reproducibility

# Base setup
weeks = [datetime(2025, 1, 6) + timedelta(weeks=i) for i in range(20)]
stores = ['S1_BigMart', 'S2_ValueGrocer', 'S3_FreshWay', 'S4_SuperSave', 'S5_QuickMart']
products = [
    {'cat': 'Beverages', 'brand': 'Coke', 'upc': '12345678901', 'name': '12oz Coke Can', 'base': 1.29},
    {'cat': 'Beverages', 'brand': 'Pepsi', 'upc': '98765432109', 'name': '12oz Pepsi Can', 'base': 1.29},
    {'cat': 'Snacks', 'brand': 'Lays', 'upc': '11122233344', 'name': 'Family Size Lays Chips', 'base': 3.99},
    {'cat': 'Snacks', 'brand': 'Pringles', 'upc': '44455566677', 'name': 'Pringles Original', 'base': 4.49},
    {'cat': 'Snacks', 'brand': 'Doritos', 'upc': '88899900011', 'name': 'Nacho Cheese Doritos', 'base': 3.79},
    {'cat': 'Dairy', 'brand': 'PrivateLabel', 'upc': '55566677788', 'name': 'Whole Milk Gallon', 'base': 3.49},
    {'cat': 'Dairy', 'brand': 'Yoplait', 'upc': '22233344455', 'name': 'Yogurt 6oz', 'base': 0.89},
    {'cat': 'Beverages', 'brand': 'RedBull', 'upc': '99988877766', 'name': '8.4oz Red Bull', 'base': 2.49},
    {'cat': 'Beverages', 'brand': 'Monster', 'upc': '77766655544', 'name': 'Monster Energy 16oz', 'base': 2.19},
    {'cat': 'Snacks', 'brand': 'Oreo', 'upc': '33344455566', 'name': 'Oreo Family Pack', 'base': 4.99}
]

rows = []
for week in weeks:
    for store in stores:
        for prod in products:
            promo = 1 if np.random.rand() < 0.35 else 0  # ~35% promo chance
            price = prod['base'] if promo == 0 else round(prod['base'] * np.random.uniform(0.75, 0.95), 2)
            base_units = np.random.randint(100, 500)
            lift = 1.6 if promo else 1.0
            seasonal = 1.3 if (week.month >= 5 and prod['cat'] in ['Beverages']) else 1.0
            units = int(base_units * lift * seasonal * np.random.uniform(0.8, 1.2))
            dollars = round(units * price, 2)
            acv = np.random.randint(50, 99)
            share = round(np.random.uniform(25, 65) if promo else np.random.uniform(20, 55), 1)
            
            rows.append({
                'Week': week.strftime('%Y-%m-%d'),
                'Store_ID': store,
                'Category': prod['cat'],
                'Brand': prod['brand'],
                'UPC': prod['upc'],
                'Product_Name': prod['name'],
                'Base_Price': prod['base'],
                'Actual_Price': price,
                'Any_Promo': promo,
                'Units_Sold': units,
                'Dollar_Sales': dollars,
                'ACV_Distribution': acv,
                'Market_Share_Pct': share
            })

df = pd.DataFrame(rows)
print(df.shape)  # Should be around (20 weeks × 5 stores × 10 products = 1000 rows; slice .head(100) for ~100)
df.to_csv('circana_sample_100rows.csv', index=False)
df.to_json('circana_sample_100rows.json', orient='records', indent=2)