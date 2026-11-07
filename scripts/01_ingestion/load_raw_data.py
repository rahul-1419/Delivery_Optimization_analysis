import os
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
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

files = {
    "raw_orders": "data/raw/olist_orders_dataset.csv",
    "raw_customers": "data/raw/olist_customers_dataset.csv",
    "raw_order_items": "data/raw/olist_order_items_dataset.csv",
    "raw_products": "data/raw/olist_products_dataset.csv",
    "raw_sellers": "data/raw/olist_sellers_dataset.csv",
    "raw_category_translation": "data/raw/product_category_name_translation.csv",
    "raw_geolocation": "data/raw/olist_geolocation_dataset.csv",
    "raw_order_payments": "data/raw/olist_order_payments_dataset.csv",
    "raw_order_reviews": "data/raw/olist_order_reviews_dataset.csv",
}

for table_name, file_path in files.items():
    print(f"Loading {table_name}...")

    df = pd.read_csv(file_path)

    df.to_sql(
        table_name,
        engine,
        if_exists="replace",
        index=False
    )

    print(f"{table_name} loaded successfully.")