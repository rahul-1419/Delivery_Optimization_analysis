import pandas as pd
import json
from datetime import datetime
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

# ---- Load ALL raw tables ----
orders = pd.read_sql("SELECT * FROM raw_orders", engine)
customers = pd.read_sql("SELECT * FROM raw_customers", engine)
items = pd.read_sql("SELECT * FROM raw_order_items", engine)
products = pd.read_sql("SELECT * FROM raw_products", engine)
sellers = pd.read_sql("SELECT * FROM raw_sellers", engine)
payments = pd.read_sql("SELECT * FROM raw_order_payments", engine)
reviews = pd.read_sql("SELECT * FROM raw_order_reviews", engine)
geolocation = pd.read_sql("SELECT * FROM raw_geolocation", engine)
category = pd.read_sql("SELECT * FROM raw_category_translation", engine)

all_tables = {
    "raw_orders": orders, "raw_customers": customers, "raw_order_items": items,
    "raw_products": products, "raw_sellers": sellers, "raw_order_payments": payments,
    "raw_order_reviews": reviews, "raw_geolocation": geolocation,
    "raw_category_translation": category
}

report = {"generated_at": str(datetime.now()), "tables": {}}

# ---- 1. COMPLETENESS (all tables) ----
for name, df in all_tables.items():
    missing = df.isnull().sum()
    missing = missing[missing > 0]
    missing_pct = (missing / len(df) * 100).round(2)
    report["tables"][name] = {
        "row_count": len(df),
        "column_count": len(df.columns),
        "completeness": {
            col: {"missing_count": int(missing[col]), "missing_pct": float(missing_pct[col])}
            for col in missing.index
        },
        "duplicate_rows": int(df.duplicated().sum())
    }

# ---- 2. UNIQUENESS (key columns) ----
report["uniqueness"] = {
    "duplicate_order_id": int(orders['order_id'].duplicated().sum()),
    "duplicate_customer_id": int(customers['customer_id'].duplicated().sum()),
    "duplicate_product_id": int(products['product_id'].duplicated().sum()),
    "duplicate_seller_id": int(sellers['seller_id'].duplicated().sum())
}

# ---- 3. VALIDITY ----
report["validity"] = {
    "order_status_values": orders['order_status'].unique().tolist(),
    "unique_states_customer": sorted(customers['customer_state'].unique().tolist()),
    "unique_states_seller": sorted(sellers['seller_state'].unique().tolist()),
    "payment_type_values": payments['payment_type'].unique().tolist(),
    "review_score_range": [int(reviews['review_score'].min()), int(reviews['review_score'].max())]
}

# ---- 4. ACCURACY ----
date_cols = ['order_purchase_timestamp', 'order_approved_at',
             'order_delivered_customer_date', 'order_estimated_delivery_date']
for col in date_cols:
    orders[col] = pd.to_datetime(orders[col], errors='coerce')

bad_dates = orders[orders['order_delivered_customer_date'] < orders['order_purchase_timestamp']]
bad_price = items[items['price'] <= 0]
bad_freight = items[items['freight_value'] < 0]
bad_payment = payments[payments['payment_value'] <= 0]

report["accuracy"] = {
    "orders_delivered_before_purchase": len(bad_dates),
    "items_with_price_zero_or_negative": len(bad_price),
    "items_with_negative_freight": len(bad_freight),
    "payments_zero_or_negative": len(bad_payment)
}

# ---- 5. CONSISTENCY (cross-table integrity) ----
orphan_customers = orders[~orders['customer_id'].isin(customers['customer_id'])]
orphan_products = items[~items['product_id'].isin(products['product_id'])]
orphan_sellers = items[~items['seller_id'].isin(sellers['seller_id'])]
orphan_payments = payments[~payments['order_id'].isin(orders['order_id'])]
orphan_reviews = reviews[~reviews['order_id'].isin(orders['order_id'])]

report["consistency"] = {
    "orders_with_missing_customer": len(orphan_customers),
    "items_with_missing_product": len(orphan_products),
    "items_with_missing_seller": len(orphan_sellers),
    "payments_with_missing_order": len(orphan_payments),
    "reviews_with_missing_order": len(orphan_reviews)
}

# ---- 6. TIMELINESS ----
report["timeliness"] = {
    "earliest_order": str(orders['order_purchase_timestamp'].min()),
    "latest_order": str(orders['order_purchase_timestamp'].max())
}

# ---- 7. PAYMENT RECONCILIATION CHECK (the BA-favorite check) ----
# For each order: total item price + freight should roughly equal total payment value
item_totals = items.groupby('order_id').agg(
    total_price=('price', 'sum'),
    total_freight=('freight_value', 'sum')
).reset_index()
item_totals['expected_total'] = item_totals['total_price'] + item_totals['total_freight']

payment_totals = payments.groupby('order_id')['payment_value'].sum().reset_index()
payment_totals.columns = ['order_id', 'actual_paid']

reconciliation = item_totals.merge(payment_totals, on='order_id', how='inner')
reconciliation['difference'] = (reconciliation['expected_total'] - reconciliation['actual_paid']).round(2)

# Flag mismatches beyond a small rounding tolerance (e.g., ₹0.10)
mismatches = reconciliation[reconciliation['difference'].abs() > 0.10]

report["payment_reconciliation"] = {
    "total_orders_checked": len(reconciliation),
    "orders_with_mismatch": len(mismatches),
    "mismatch_pct": round(len(mismatches) / len(reconciliation) * 100, 2),
    "avg_mismatch_amount": round(mismatches['difference'].abs().mean(), 2) if len(mismatches) > 0 else 0,
    "max_mismatch_amount": round(mismatches['difference'].abs().max(), 2) if len(mismatches) > 0 else 0,
    "sample_mismatches": mismatches.head(5)[['order_id', 'expected_total', 'actual_paid', 'difference']].to_dict('records')
}

# ---- Print summary to console ----
print("="*60)
print("DATA QUALITY REPORT SUMMARY")
print("="*60)
print(f"\nTables checked: {len(all_tables)}")
print(f"\n--- Payment Reconciliation ---")
print(f"Orders checked: {report['payment_reconciliation']['total_orders_checked']}")
print(f"Mismatches found: {report['payment_reconciliation']['orders_with_mismatch']} "
      f"({report['payment_reconciliation']['mismatch_pct']}%)")
print(f"Avg mismatch: R$ {report['payment_reconciliation']['avg_mismatch_amount']}")
print(f"\n--- Consistency ---")
for k, v in report["consistency"].items():
    print(f"{k}: {v}")

# ---- Save to JSON ----
with open("data/report/data_quality_report.json", "w") as f:
    json.dump(report, f, indent=2, default=str)

print("\n✅ Full report saved to data/report/data_quality_report.json")