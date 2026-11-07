import os
import pandas as pd
import numpy as np
from scipy import stats
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from dotenv import load_dotenv

load_dotenv()


def get_engine():
    password = os.getenv("POSTGRES_PASSWORD")
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
    return engine


def cramers_v(contingency_table):
    chi2 = stats.chi2_contingency(contingency_table)[0]
    n = contingency_table.sum().sum()
    r, k = contingency_table.shape
    return np.sqrt(chi2 / (n * (min(r, k) - 1)))

 
# 1. Delivery Performance Analysis
# Question: How prevalent is late delivery, and how does it
# affect fulfillment duration? (delivered orders only) 
def delivery_performance_analysis(engine):
    df = pd.read_sql("SELECT * FROM fact_orders", engine)
    df['is_cancelled'] = df['order_status_clean'] == 'canceled'

    delivered = df[df['fulfillment_duration_days'].notna()].copy()
    late_deliv = delivered[delivered['is_late'] == True]
    ontime_deliv = delivered[delivered['is_late'] == False]

    cancellation_rate_overall = df['is_cancelled'].mean() * 100

    result = pd.DataFrame([{
        'total_orders': len(df),
        'delivered_orders': len(delivered),
        'cancelled_orders': int(df['is_cancelled'].sum()),
        'delivered_on_time': len(ontime_deliv),
        'delivered_late': len(late_deliv),
        'avg_fulfillment_duration_on_time': round(ontime_deliv['fulfillment_duration_days'].mean(), 1),
        'avg_fulfillment_duration_late': round(late_deliv['fulfillment_duration_days'].mean(), 1),
        'overall_cancellation_rate': round(cancellation_rate_overall, 2),
        'note': 'Cancelled orders have no delivery date, so lateness is undefined for them and excluded here.'
    }])

    result.to_sql('delivery_performance_analysis', engine, if_exists='replace', index=False)
    result.to_csv('data/report/delivery_performance_analysis.csv', index=False)
    print(result.T)
    return result

 
# 2. SLA Operational Zones 
def sla_operational_zones(engine):
    state_performance = pd.read_sql("SELECT * FROM state_performance", engine)

    cancel_median = state_performance['cancellation_rate'].median()
    late_median = state_performance['late_delivery_rate'].median()

    def assign_zone(row):
        high_cancel = row['cancellation_rate'] > cancel_median
        high_late = row['late_delivery_rate'] > late_median
        if high_cancel and high_late:
            return 'Critical Zone'
        elif high_cancel and not high_late:
            return 'Customer Risk Zone'
        elif not high_cancel and high_late:
            return 'Operational Risk Zone'
        else:
            return 'Healthy Zone'

    state_performance['sla_zone'] = state_performance.apply(assign_zone, axis=1)
    state_performance['cancellation_threshold'] = round(cancel_median, 2)
    state_performance['late_delivery_threshold'] = round(late_median, 2)

    sla_zones = state_performance[[
        'state_code', 'state_name', 'total_orders', 'cancellation_rate',
        'late_delivery_rate', 'sla_zone', 'cancellation_threshold', 'late_delivery_threshold'
    ]].sort_values(['sla_zone', 'cancellation_rate'], ascending=[True, False])

    sla_zones.to_sql('sla_operational_zones', engine, if_exists='replace', index=False)
    sla_zones.to_csv('data/report/sla_operational_zones.csv', index=False)

    print(sla_zones.to_string(index=False))
    print("\nZone counts:")
    print(sla_zones['sla_zone'].value_counts())

    critical = sla_zones[sla_zones['sla_zone'] == 'Critical Zone']
    print(f"\nStates in CRITICAL ZONE: {len(critical)}")
    print(critical.to_string(index=False))
    return sla_zones

 
# 3. Revenue-at-Risk Pareto 
def revenue_risk_pareto(engine):
    revenue_at_risk = pd.read_sql("SELECT * FROM revenue_at_risk_state", engine)
    revenue_at_risk = revenue_at_risk.sort_values('revenue_at_risk', ascending=False).reset_index(drop=True)

    total_risk = revenue_at_risk['revenue_at_risk'].sum()
    revenue_at_risk['pct_of_total'] = (revenue_at_risk['revenue_at_risk'] / total_risk * 100).round(2)
    revenue_at_risk['cumulative_pct'] = revenue_at_risk['pct_of_total'].cumsum().round(2)
    revenue_at_risk['rank'] = range(1, len(revenue_at_risk) + 1)

    pareto = revenue_at_risk[['rank', 'state_code', 'state_name', 'revenue_at_risk',
                                'pct_of_total', 'cumulative_pct']]

    crossing_idx = pareto['cumulative_pct'].ge(80).idxmax()
    n_states_80pct = crossing_idx + 1
    total_states = len(pareto)
    top3_share = pareto.iloc[:3]['pct_of_total'].sum()

    pareto.to_sql('revenue_at_risk_pareto', engine, if_exists='replace', index=False)
    pareto.to_csv('data/report/revenue_at_risk_pareto.csv', index=False)

    print(pareto.to_string(index=False))
    print(f"\n💡 {n_states_80pct} of {total_states} states ({n_states_80pct/total_states*100:.0f}%) "
          f"account for ~80% of total revenue at risk.")
    print(f"💡 Top 3 states alone account for {top3_share:.1f}% of total revenue at risk.")
    print(f"Total Revenue at Risk: R$ {total_risk:,.2f}")

    return pareto, n_states_80pct, top3_share

 
# 4. Cancellation Driver Analysis
# Question: Which measurable factors are statistically
# associated with cancellation? State, Order Value, Item Count only.
# Late Delivery is intentionally excluded — see Analysis 1 for
# why lateness can't be validly cross-tabbed against cancellation. 
def cancellation_driver_analysis(engine):
    fact_orders = pd.read_sql("SELECT * FROM fact_orders", engine)
    dim_customer = pd.read_sql("SELECT * FROM dim_customer", engine)
    dim_state = pd.read_sql("SELECT * FROM dim_state", engine)

    df = fact_orders.merge(dim_customer, on='customer_id', how='left')
    df = df.merge(dim_state, on='state_id', how='left')
    df['is_cancelled'] = df['order_status_clean'] == 'canceled'

    results = []

    # State vs Cancellation
    ct_state = pd.crosstab(df['state_code'], df['is_cancelled'])
    chi2, p_val, _, _ = stats.chi2_contingency(ct_state)
    v = cramers_v(ct_state)
    results.append({'factor': 'State', 'test': 'Chi-square', 'statistic': round(chi2, 4),
                     'p_value': round(p_val, 6), 'effect_size_cramers_v': round(v, 4),
                     'significant': bool(p_val < 0.05), 'relationship': 'Varies by state'})

    # Order Value vs Cancellation (point-biserial)
    valid = df.dropna(subset=['total_price'])
    corr, p_val = stats.pointbiserialr(valid['is_cancelled'].astype(int), valid['total_price'])
    results.append({'factor': 'Order Value', 'test': 'Point-biserial correlation', 'statistic': round(corr, 4),
                     'p_value': round(p_val, 6), 'effect_size_cramers_v': None,
                     'significant': bool(p_val < 0.05), 'relationship': 'Positive' if corr > 0 else 'Negative'})

    # Item Count vs Cancellation (point-biserial)
    valid = df.dropna(subset=['item_count'])
    corr, p_val = stats.pointbiserialr(valid['is_cancelled'].astype(int), valid['item_count'])
    results.append({'factor': 'Item Count', 'test': 'Point-biserial correlation', 'statistic': round(corr, 4),
                     'p_value': round(p_val, 6), 'effect_size_cramers_v': None,
                     'significant': bool(p_val < 0.05), 'relationship': 'Positive' if corr > 0 else 'Negative'})

    results_df = pd.DataFrame(results)
    results_df.to_sql('cancellation_drivers', engine, if_exists='replace', index=False)
    results_df.to_csv('data/report/cancellation_drivers.csv', index=False)
    print(results_df.to_string(index=False))

    state_summary = df.groupby(['state_code', 'state_name']).agg(
        orders=('order_id', 'count'),
        cancellation_rate=('is_cancelled', 'mean')
    ).reset_index()
    state_summary['cancellation_rate'] = (state_summary['cancellation_rate'] * 100).round(2)
    state_summary = state_summary.sort_values('cancellation_rate', ascending=False)

    print("\nHighest cancellation rate states:")
    print(state_summary.head(5).to_string(index=False))

    state_summary.to_sql('cancellation_by_state_summary', engine, if_exists='replace', index=False)
    return results_df

 
# MAIN 
def main():
    engine = get_engine()

    print("\n" + "="*60)
    print("1. DELIVERY PERFORMANCE ANALYSIS")
    print("="*60)
    delivery_result = delivery_performance_analysis(engine)

    print("\n" + "="*60)
    print("2. SLA OPERATIONAL ZONES")
    print("="*60)
    sla_result = sla_operational_zones(engine)

    print("\n" + "="*60)
    print("3. REVENUE-AT-RISK PARETO")
    print("="*60)
    pareto_result, n_states_80pct, top3_share = revenue_risk_pareto(engine)

    print("\n" + "="*60)
    print("4. CANCELLATION DRIVER ANALYSIS")
    print("="*60)
    drivers_result = cancellation_driver_analysis(engine)

    critical_count = (sla_result['sla_zone'] == 'Critical Zone').sum()
    state_p = drivers_result.loc[drivers_result['factor'] == 'State', 'p_value'].iloc[0]
    value_p = drivers_result.loc[drivers_result['factor'] == 'Order Value', 'p_value'].iloc[0]
    item_p = drivers_result.loc[drivers_result['factor'] == 'Item Count', 'p_value'].iloc[0]

    summary = pd.DataFrame([
        {'analysis': 'Delivery Performance',
         'key_finding': f"{delivery_result['delivered_late'].values[0]:,} of {delivery_result['delivered_orders'].values[0]:,} delivered orders were late",
         'statistical_evidence': f"Avg duration: on-time {delivery_result['avg_fulfillment_duration_on_time'].values[0]} days vs late {delivery_result['avg_fulfillment_duration_late'].values[0]} days"},
        {'analysis': 'SLA Zones',
         'key_finding': f"{critical_count} states classified as Critical Zone (high cancellation + high late delivery)",
         'statistical_evidence': "Thresholds: cancellation > median, late-rate > median"},
        {'analysis': 'Revenue Risk (Pareto)',
         'key_finding': f"Top 3 states account for {top3_share:.1f}% of total revenue at risk; {n_states_80pct} states account for ~80%",
         'statistical_evidence': '—'},
        {'analysis': 'Cancellation Drivers',
         'key_finding': 'State, order value, and item count were tested as cancellation-related factors',
         'statistical_evidence': f"State p={state_p:.4f}, Order Value p={value_p:.4f}, Item Count p={item_p:.4f}"}
    ])
    summary.to_csv('data/report/advanced_logistics_summary.csv', index=False)
    summary.to_sql('advanced_logistics_summary', engine, if_exists='replace', index=False)

    print("\n" + "="*60)
    print("EXECUTIVE SUMMARY SAVED")
    print("="*60)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()