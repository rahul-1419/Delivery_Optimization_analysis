import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

import os
from dotenv import load_dotenv

load_dotenv()

db_url = URL.create(
    drivername="postgresql",
    username=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("POSTGRES_HOST"),
    port=int(os.getenv("POSTGRES_PORT", 5432)),
    database=os.getenv("POSTGRES_DB")
)

engine = create_engine(db_url)

# ============ 1. ORDERS ============
orders = pd.read_sql("SELECT * FROM raw_orders", engine)

# Convert all timestamp columns to proper datetime; NULLs are preserved
# (a NULL delivery date means the order was never delivered — meaningful, not an error)
date_cols = ['order_purchase_timestamp', 'order_approved_at',
             'order_delivered_carrier_date', 'order_delivered_customer_date',
             'order_estimated_delivery_date']
for col in date_cols:
    orders[col] = pd.to_datetime(orders[col], errors='coerce')

# Create date-only helper columns for trend analysis / dim_date joins
# Using .dt.normalize() instead of .dt.date to keep PostgreSQL-friendly datetime type
orders['purchase_date'] = orders['order_purchase_timestamp'].dt.normalize()
orders['approved_date'] = orders['order_approved_at'].dt.normalize()
orders['carrier_date'] = orders['order_delivered_carrier_date'].dt.normalize()
orders['delivered_date'] = orders['order_delivered_customer_date'].dt.normalize()
orders['estimated_delivery_date'] = orders['order_estimated_delivery_date'].dt.normalize()

# Standardize order_status into a clean column; keep raw column untouched for audit
orders['order_status_clean'] = orders['order_status'].str.strip().str.lower()

orders.to_sql('orders_clean', engine, if_exists='replace', index=False)
print(f"orders_clean: {len(orders)} rows saved")

# ============ 2. CUSTOMERS ============
customers = pd.read_sql("SELECT * FROM raw_customers", engine)

# Zip prefix can lose leading zeros when read as a number — force back to 5-char string
customers['customer_zip_code_prefix'] = (
    customers['customer_zip_code_prefix'].astype(str).str.zfill(5)
)

# Cleaned sibling columns for consistent grouping/joins; raw columns stay untouched
customers['customer_city_clean'] = customers['customer_city'].str.strip().str.lower()
customers['customer_state_clean'] = customers['customer_state'].str.strip().str.upper()

customers.to_sql('customers_clean', engine, if_exists='replace', index=False)
print(f"customers_clean: {len(customers)} rows saved")

# ============ 3. ORDER ITEMS ============
items = pd.read_sql("SELECT * FROM raw_order_items", engine)

# Convert shipping deadline to datetime + create date-only helper
items['shipping_limit_date'] = pd.to_datetime(items['shipping_limit_date'], errors='coerce')
items['shipping_limit_only_date'] = items['shipping_limit_date'].dt.normalize()

# Ensure numeric types and round to 2 decimals — these are currency values
items['price'] = pd.to_numeric(items['price'], errors='coerce').round(2)
items['freight_value'] = pd.to_numeric(items['freight_value'], errors='coerce').round(2)

items.to_sql('order_items_clean', engine, if_exists='replace', index=False)
print(f"order_items_clean: {len(items)} rows saved")

# ============ Verification: confirm no rows were accidentally lost ============
print("\n" + "="*40)
print("VERIFICATION — Row counts after cleaning")
print("="*40)
print("orders_clean:", pd.read_sql("SELECT COUNT(*) FROM orders_clean", engine).iloc[0, 0])
print("customers_clean:", pd.read_sql("SELECT COUNT(*) FROM customers_clean", engine).iloc[0, 0])
print("order_items_clean:", pd.read_sql("SELECT COUNT(*) FROM order_items_clean", engine).iloc[0, 0])
print("\nExpected: 99441 / 99441 / 112650")