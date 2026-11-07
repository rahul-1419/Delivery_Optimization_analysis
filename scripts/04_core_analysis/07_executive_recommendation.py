import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

# MIN_ORDERS_FOR_RELIABLE_SIGNAL: minimum orders required before making a business
# recommendation for a state. 500 is chosen as an operational confidence threshold —
# below this, a state's cancellation rate is too noisy to justify a confident
# recommendation to operations teams.
# Note: the statistical_validation script uses a much lower threshold (10) for the
# Pearson correlation — that threshold only needs each state to have a non-trivial
# cancellation rate as a data point, which 10 orders is sufficient for.
MIN_ORDERS_FOR_RELIABLE_SIGNAL = 500  # below this, cancellation rate is statistically noisy

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

warehouse_priority = pd.read_sql("SELECT * FROM warehouse_priority_state", engine)
revenue_at_risk = pd.read_sql("SELECT * FROM revenue_at_risk_state", engine)

df = warehouse_priority.merge(
    revenue_at_risk[['state_code', 'revenue_at_risk']],
    on='state_code', how='left'
)
df['revenue_at_risk'] = df['revenue_at_risk'].fillna(0.0)

volume_threshold = df['total_orders'].median()
cancel_threshold = df['cancellation_rate'].median()
revenue_threshold = df['revenue_at_risk'].median()

# ============ Business Insight (renamed from "reason") ============
def build_insight(row):
    if row['total_orders'] < MIN_ORDERS_FOR_RELIABLE_SIGNAL:
        return ("Small order volume — cancellation rate may not be statistically "
                "reliable; interpret results cautiously.")

    parts = []
    if row['total_orders'] > volume_threshold:
        parts.append("high customer demand")
    if row['cancellation_rate'] > cancel_threshold:
        parts.append("an elevated cancellation rate")
    if row['revenue_at_risk'] > revenue_threshold:
        parts.append("significant revenue at risk")

    if not parts:
        return "This state performs below the median on all key factors."
    if len(parts) == 1:
        return f"This state shows {parts[0]}."
    if len(parts) == 2:
        return f"This state shows {parts[0]} combined with {parts[1]}."
    return f"High customer demand together with an elevated cancellation rate is exposing {parts[2]}."

# ============ Recommendation — now driven by actual factors, not just priority_label ============
def build_recommendation(row):
    if row['total_orders'] < MIN_ORDERS_FOR_RELIABLE_SIGNAL:
        return "Continue monitoring — sample size too small for a confident recommendation."

    high_volume = row['total_orders'] > volume_threshold
    high_cancel = row['cancellation_rate'] > cancel_threshold
    high_revenue = row['revenue_at_risk'] > revenue_threshold

    if row['priority_label'] == 'High Priority':
        return "Investigate fulfillment operations immediately — regional logistics performance likely needs attention."
    elif high_revenue and high_cancel:
        return "Investigate the root causes of cancellations to reduce revenue at risk."
    elif high_revenue:
        return "Monitor closely and investigate regional issues — revenue exposure is notable despite lower cancellation rate."
    elif high_cancel:
        return "Investigate courier performance — cancellation rate is elevated relative to other states."
    elif high_volume:
        return "Review fulfillment capacity to support sustained order demand."
    else:
        return "No immediate action required."

df['business_insight'] = df.apply(build_insight, axis=1)
df['recommendation'] = df.apply(build_recommendation, axis=1)

executive_recommendation = df.sort_values('warehouse_priority_index', ascending=False).head(10).reset_index(drop=True)
executive_recommendation.insert(0, "rank", range(1, len(executive_recommendation) + 1))

executive_recommendation = executive_recommendation.rename(
    columns={'priority_label': 'warehouse_priority'}
)

executive_recommendation = executive_recommendation[[
    'rank', 'state_code', 'state_name', 'total_orders', 'cancellation_rate',
    'revenue_at_risk', 'warehouse_priority_index', 'warehouse_priority',
    'business_insight', 'recommendation'
]]

# Table name fixed — no slashes allowed in SQL table names
executive_recommendation.to_sql('executive_recommendation', engine, if_exists='replace', index=False)
executive_recommendation.to_csv('data/report/executive_recommendation.csv', index=False)

print(f"executive_recommendation: {len(executive_recommendation)} rows saved\n")
print(executive_recommendation.to_string(index=False))

print("\n" + "="*70)
print("EXECUTIVE DECISION SUPPORT — TOP 5 PRIORITY STATES")
print("="*70)
for _, row in executive_recommendation.head(5).iterrows():
    print(f"\n#{row['rank']} — {row['state_name']} ({row['state_code']})")
    print(f"  Orders: {row['total_orders']:,} | Cancellation: {row['cancellation_rate']}% | "
          f"Revenue at Risk: R$ {row['revenue_at_risk']:,.2f}")
    print(f"  Business Insight: {row['business_insight']}")
    print(f"  Recommendation: {row['recommendation']}")