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

fact_orders = pd.read_sql("SELECT * FROM fact_orders", engine)
dim_customer = pd.read_sql("SELECT * FROM dim_customer", engine)
dim_state = pd.read_sql("SELECT * FROM dim_state", engine)

df = fact_orders.merge(dim_customer, on='customer_id', how='left')
df = df.merge(dim_state, on='state_id', how='left')

df['is_cancelled'] = df['order_status_clean'] == 'canceled'
# Delivered = has a delivery date (fulfillment_duration_days is not null)
df['is_delivered'] = df['fulfillment_duration_days'].notna()

def aggregate_performance(df, group_cols):
    grouped = df.groupby(group_cols).agg(
        total_orders=('order_id', 'count'),
        total_revenue=('total_price', 'sum'),
        cancelled_orders=('is_cancelled', 'sum'),
        delivered_orders=('is_delivered', 'sum'),
        late_orders=('is_late', 'sum'),
        avg_fulfillment_duration=('fulfillment_duration_days', 'mean'),
        avg_order_value=('total_price', 'mean')
    ).reset_index()
    
    grouped['cancellation_rate'] = (
        grouped['cancelled_orders'] / grouped['total_orders'] * 100
    ).round(2)
    
    # FIX: late delivery rate is calculated only against DELIVERED orders,
    # not total orders — cancelled orders were never delivered so shouldn't
    # be in the denominator. Avoid divide-by-zero for groups with 0 delivered orders.
    grouped['late_delivery_rate'] = grouped.apply(
        lambda row: round(row['late_orders'] / row['delivered_orders'] * 100, 2)
        if row['delivered_orders'] > 0 else 0.0,
        axis=1
    )
    
    grouped['avg_fulfillment_duration'] = grouped['avg_fulfillment_duration'].round(1)
    grouped['avg_order_value'] = grouped['avg_order_value'].round(2)
    grouped['total_revenue'] = grouped['total_revenue'].round(2)
    return grouped

# ============ STATE PERFORMANCE ============
state_performance = aggregate_performance(df, ['state_id', 'state_code', 'state_name'])
state_performance.to_sql('state_performance', engine, if_exists='replace', index=False)
print(f"state_performance: {len(state_performance)} rows saved")

# ============ CITY PERFORMANCE ============
city_performance = aggregate_performance(df, ['customer_city', 'state_code'])
city_performance.to_sql('city_performance', engine, if_exists='replace', index=False)
print(f"city_performance: {len(city_performance)} rows saved")