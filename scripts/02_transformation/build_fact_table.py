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

orders = pd.read_sql("SELECT * FROM orders_clean", engine)
items = pd.read_sql("SELECT * FROM order_items_clean", engine)

# Aggregate items to one row per order
item_totals = items.groupby('order_id').agg(
    total_price=('price', 'sum'),
    total_freight=('freight_value', 'sum'),
    item_count=('order_item_id', 'count')
).reset_index()

fact_orders = orders[['order_id', 'customer_id', 'order_status_clean',
                       'order_purchase_timestamp', 'delivered_date',
                       'estimated_delivery_date']].copy()

fact_orders = fact_orders.merge(item_totals, on='order_id', how='left')

fact_orders['date_id'] = pd.to_numeric(
    fact_orders['order_purchase_timestamp'].dt.strftime('%Y%m%d'), errors='coerce'
)

# Renamed per business-scope correction: this measures order-to-doorstep duration,
# NOT warehouse/logistics performance (no warehouse location data exists in this dataset)
fact_orders['fulfillment_duration_days'] = (
    fact_orders['delivered_date'] - fact_orders['order_purchase_timestamp'].dt.normalize()
).dt.days

fact_orders['is_late'] = fact_orders['delivered_date'] > fact_orders['estimated_delivery_date']

fact_orders = fact_orders[['order_id', 'customer_id', 'date_id',
                            'order_status_clean', 'total_price', 'total_freight',
                            'item_count', 'fulfillment_duration_days', 'is_late']]

fact_orders.to_sql('fact_orders', engine, if_exists='replace', index=False)
print(f"fact_orders: {len(fact_orders)} rows saved")

# Verification
print("\nVerification — expected 99441 rows")
print(pd.read_sql("SELECT COUNT(*) FROM fact_orders", engine).iloc[0, 0])