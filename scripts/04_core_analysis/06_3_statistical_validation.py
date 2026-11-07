import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

# MIN_ORDER_THRESHOLD: minimum orders required for a state to be included in the
# Pearson correlation. A threshold of 10 is sufficient here because the correlation
# uses each state as one data point — we only need enough orders per state to make
# its cancellation rate a non-trivial value, not enough for a business recommendation.
# (The executive_recommendation.py script uses a separate, much higher threshold of
# 500 orders before making a business recommendation for a state — that threshold is
# about operational confidence, not statistical validity of the correlation.)
MIN_ORDER_THRESHOLD = 10

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

state_performance = pd.read_sql("SELECT * FROM state_performance", engine)
filtered = state_performance[state_performance['total_orders'] >= MIN_ORDER_THRESHOLD]

correlation, p_value = stats.pearsonr(filtered['total_orders'], filtered['cancellation_rate'])

print(f"Correlation coefficient: {correlation:.4f}")
print(f"P-value: {p_value:.4f}")
print(f"Statistically significant (p < 0.05): {p_value < 0.05}")

result = pd.DataFrame([{
    'metric_pair': 'order_volume_vs_cancellation_rate',
    'correlation_coefficient': round(correlation, 4),
    'p_value': round(p_value, 4),
    'is_significant': bool(p_value < 0.05),
    'min_order_threshold': MIN_ORDER_THRESHOLD,
    'states_included': len(filtered)
}])
result.to_csv('data/report/correlation_result.csv', index=False)
result.to_sql('correlation_result', engine, if_exists='replace', index=False)
print("\nSaved to correlation_result.csv and correlation_result table")

plt.figure(figsize=(10, 6))
plt.scatter(filtered['total_orders'], filtered['cancellation_rate'], alpha=0.7)
for _, row in filtered.iterrows():
    plt.annotate(row['state_code'], (row['total_orders'], row['cancellation_rate']),
                 fontsize=8, xytext=(3, 3), textcoords='offset points')
plt.xlabel('Total Orders (Order Volume)')
plt.ylabel('Cancellation Rate (%)')
plt.title(f'Order Volume vs Cancellation Rate by State (r = {correlation:.3f})')
plt.tight_layout()
plt.savefig('data/report/scatter_volume_vs_cancellation.png', dpi=150)
print("Scatter plot saved as scatter_volume_vs_cancellation.png")
plt.show()