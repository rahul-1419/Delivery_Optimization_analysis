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


customers = pd.read_sql("SELECT * FROM customers_clean", engine)
orders = pd.read_sql("SELECT * FROM orders_clean", engine)
 
state_name_map = {
    'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapa', 'AM': 'Amazonas',
    'BA': 'Bahia', 'CE': 'Ceara', 'DF': 'Distrito Federal', 'ES': 'Espirito Santo',
    'GO': 'Goias', 'MA': 'Maranhao', 'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul',
    'MG': 'Minas Gerais', 'PA': 'Para', 'PB': 'Paraiba', 'PR': 'Parana',
    'PE': 'Pernambuco', 'PI': 'Piaui', 'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte',
    'RS': 'Rio Grande do Sul', 'RO': 'Rondonia', 'RR': 'Roraima', 'SC': 'Santa Catarina',
    'SP': 'Sao Paulo', 'SE': 'Sergipe', 'TO': 'Tocantins'
}

dim_state = pd.DataFrame({'state_code': sorted(customers['customer_state_clean'].unique())})
dim_state['state_id'] = range(1, len(dim_state) + 1)
dim_state['state_name'] = dim_state['state_code'].map(state_name_map)
dim_state = dim_state[['state_id', 'state_code', 'state_name']]

dim_state.to_sql('dim_state', engine, if_exists='replace', index=False)
print(f"dim_state: {len(dim_state)} rows saved")

# ============ dim_customer ============
dim_customer = customers[['customer_id', 'customer_unique_id',
                           'customer_city_clean', 'customer_state_clean',
                           'customer_zip_code_prefix']].copy()

dim_customer = dim_customer.merge(
    dim_state[['state_id', 'state_code']],
    left_on='customer_state_clean', right_on='state_code', how='left'
)
dim_customer = dim_customer[['customer_id', 'customer_unique_id',
                              'customer_city_clean', 'state_id', 'customer_zip_code_prefix']]
dim_customer.columns = ['customer_id', 'customer_unique_id',
                         'customer_city', 'state_id', 'zip_code_prefix']

dim_customer.to_sql('dim_customer', engine, if_exists='replace', index=False)
print(f"dim_customer: {len(dim_customer)} rows saved")

# ============ dim_date ============
date_range = pd.date_range(
    start=orders['order_purchase_timestamp'].min().normalize(),
    end=orders['order_purchase_timestamp'].max().normalize(),
    freq='D'
)
dim_date = pd.DataFrame({'full_date': date_range})
dim_date['date_id'] = dim_date['full_date'].dt.strftime('%Y%m%d').astype(int)
dim_date['year'] = dim_date['full_date'].dt.year
dim_date['month'] = dim_date['full_date'].dt.month
dim_date['month_name'] = dim_date['full_date'].dt.month_name()
dim_date['day'] = dim_date['full_date'].dt.day
dim_date['day_name'] = dim_date['full_date'].dt.day_name()
dim_date['week'] = dim_date['full_date'].dt.isocalendar().week
dim_date['is_weekend'] = dim_date['full_date'].dt.dayofweek.isin([5, 6])
dim_date = dim_date[['date_id', 'full_date', 'year', 'month', 'month_name',
                      'day', 'day_name', 'week', 'is_weekend']]

dim_date.to_sql('dim_date', engine, if_exists='replace', index=False)
print(f"dim_date: {len(dim_date)} rows saved")

print("\n✅ All dimension tables built.")