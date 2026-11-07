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

def normalize(series):
    if series.max() == series.min():
        return pd.Series(0.5, index=series.index)
    return (series - series.min()) / (series.max() - series.min())

def build_priority(df):
    df = df.copy()
    df['norm_volume'] = normalize(df['total_orders'])
    df['norm_cancel_rate'] = normalize(df['cancellation_rate'])
    
    df['warehouse_priority_index'] = (
        0.5 * df['norm_volume'] + 0.5 * df['norm_cancel_rate']
    ) * 100
    df['warehouse_priority_index'] = df['warehouse_priority_index'].round(2)
    
    def label(score):
        if score >= 70:
            return 'High Priority'
        elif score >= 40:
            return 'Medium Priority'
        else:
            return 'Low Priority'
    
    df['priority_label'] = df['warehouse_priority_index'].apply(label)
    return df

# ============ STATE-LEVEL PRIORITY ============
state_performance = pd.read_sql("SELECT * FROM state_performance", engine)
state_priority = build_priority(state_performance)
state_priority = state_priority.sort_values('warehouse_priority_index', ascending=False)

state_priority.to_sql('warehouse_priority_state', engine, if_exists='replace', index=False)
print(f"warehouse_priority_state: {len(state_priority)} rows saved")

top10_states = state_priority.head(10)
top10_states.to_sql('top_priority_states', engine, if_exists='replace', index=False)
print(f"top_priority_states: {len(top10_states)} rows saved")
print(top10_states[['state_code', 'total_orders', 'cancellation_rate',
                     'warehouse_priority_index', 'priority_label']])

# ============ CITY-LEVEL PRIORITY ============
city_performance = pd.read_sql("SELECT * FROM city_performance", engine)
city_priority = build_priority(city_performance)
city_priority = city_priority.sort_values('warehouse_priority_index', ascending=False)

city_priority.to_sql('warehouse_priority_city', engine, if_exists='replace', index=False)
print(f"\nwarehouse_priority_city: {len(city_priority)} rows saved")

top10_cities = city_priority.head(10)
top10_cities.to_sql('top_priority_cities', engine, if_exists='replace', index=False)
print(f"top_priority_cities: {len(top10_cities)} rows saved")