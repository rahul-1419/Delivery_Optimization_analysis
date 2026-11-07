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

cancelled = df[df['order_status_clean'] == 'canceled']

# NOTE: "Revenue at Risk" here is an approximation — the value of cancelled
# orders, not confirmed financial loss (we don't know if these customers
# would have completed the purchase or bought elsewhere). See README.

revenue_at_risk_state = cancelled.groupby(['state_code', 'state_name']).agg(
    cancelled_orders=('order_id', 'count'),
    revenue_at_risk=('total_price', 'sum')
).reset_index()
revenue_at_risk_state['revenue_at_risk'] = revenue_at_risk_state['revenue_at_risk'].round(2)
revenue_at_risk_state = revenue_at_risk_state.sort_values('revenue_at_risk', ascending=False)

revenue_at_risk_state.to_sql('revenue_at_risk_state', engine, if_exists='replace', index=False)
print(f"revenue_at_risk_state: {len(revenue_at_risk_state)} rows saved")
print(revenue_at_risk_state.head(10))

revenue_at_risk_city = cancelled.groupby(['customer_city', 'state_code']).agg(
    cancelled_orders=('order_id', 'count'),
    revenue_at_risk=('total_price', 'sum')
).reset_index()
revenue_at_risk_city['revenue_at_risk'] = revenue_at_risk_city['revenue_at_risk'].round(2)
revenue_at_risk_city = revenue_at_risk_city.sort_values('revenue_at_risk', ascending=False)

revenue_at_risk_city.to_sql('revenue_at_risk_city', engine, if_exists='replace', index=False)
print(f"\nrevenue_at_risk_city: {len(revenue_at_risk_city)} rows saved")

total_risk = cancelled['total_price'].sum()
print(f"\n💰 TOTAL REVENUE AT RISK (approximated as cancelled order value): R$ {total_risk:,.2f}")