import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
from stellar_logic import (
    analyze_stellar_account, 
    resolve_username_to_id, 
    resolve_id_to_name
)

# 1. Page Configuration
st.set_page_config(page_title="NUGpay Pro Dashboard", layout="wide")

# 2. Session State Initialization
if 'stellar_data' not in st.session_state:
    st.session_state.stellar_data = None
if 'display_name' not in st.session_state:
    st.session_state.display_name = ""

# 3. Sidebar
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Username", "Account ID"])

if input_method == "Username":
    user_input = st.sidebar.text_input("Enter Name", placeholder="e.g. sithu")
else:
    user_input = st.sidebar.text_input("Enter Stellar ID", placeholder="G...")

analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, 1)

col_side1, col_side2 = st.sidebar.columns(2)
run_btn = col_side1.button("Analyze Account", use_container_width=True)
clear_btn = col_side2.button("Clear Cache", use_container_width=True)

if clear_btn:
    st.session_state.stellar_data = None
    st.session_state.display_name = ""
    st.rerun()

if run_btn and user_input:
    with st.spinner("Resolving identity..."):
        target_id = None
        current_name = user_input
        
        if input_method == "Username":
            target_id = resolve_username_to_id(user_input)
            if not target_id:
                st.sidebar.error("Username not found.")
        else:
            if user_input.startswith("G") and len(user_input) == 56:
                target_id = user_input
                # Try to find the name for the G-address
                found_name = resolve_id_to_name(user_input)
                if found_name: current_name = found_name
            else:
                st.sidebar.error("Invalid G-Address.")

        if target_id:
            data = analyze_stellar_account(target_id, months=analysis_months)
            if data:
                st.session_state.stellar_data = data
                st.session_state.display_name = current_name
                st.sidebar.success(f"Loaded: {current_name}")
            else:
                st.error("No transactions found.")

# 4. Main Dashboard
if st.session_state.display_name:
    st.title(f"Dashboard: {st.session_state.display_name}")
else:
    st.title("NUGpay User Analytics")

if st.session_state.stellar_data:
    df = pd.DataFrame(st.session_state.stellar_data)

    # --- FILTERS ---
    st.subheader("Interactive Filters")
    t1, t2, t3 = st.columns(3)
    with t1:
        months = ["All Months"] + sorted(df['month_name'].unique().tolist())
        sel_month = st.selectbox("Filter by Month", months)
    with t2:
        temp_df = df if sel_month == "All Months" else df[df['month_name'] == sel_month]
        weeks = ["All Weeks"] + sorted(temp_df['week_num'].unique().tolist())
        sel_week = st.selectbox("Filter by Week", weeks)
    with t3:
        recency = st.radio("Quick Tracker", ["Full History", "Last 7 Days", "Last 24 Hours"], horizontal=True)

    # Apply Filtering
    filtered_df = df.copy()
    if sel_month != "All Months":
        filtered_df = filtered_df[filtered_df['month_name'] == sel_month]
    if sel_week != "All Weeks":
        filtered_df = filtered_df[filtered_df['week_num'] == sel_week]
    
    now = datetime.now(timezone.utc)
    if recency == "Last 7 Days":
        filtered_df = filtered_df[filtered_df['timestamp'] >= (now - timedelta(days=7))]
    elif recency == "Last 24 Hours":
        filtered_df = filtered_df[filtered_df['timestamp'] >= (now - timedelta(hours=24))]

    st.markdown("---")
    
    # --- TRANSACTION TABLE ---
    def format_val(row):
        return f"{row['amount']:,.2f}" if row['asset'] == "DMMK" else f"{row['amount']:,.7f}"
    
    filtered_df['formatted_amount'] = filtered_df.apply(format_val, axis=1)
    st.dataframe(
        filtered_df[["timestamp", "direction", "other_account", "formatted_amount", "asset"]],
        use_container_width=True, hide_index=True
    )

    # --- SUMMARY TABLE ---
    st.markdown("---")
    st.subheader("Summary by Account")
    summary_df = filtered_df.copy()
    summary_df['Incoming'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
    summary_df['Outgoing'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)

    account_summary = summary_df.groupby(['other_account', 'asset']).agg(
        Outgoing=('Outgoing', 'sum'),
        Incoming=('Incoming', 'sum'),
        Total_Volume=('amount', 'sum'),
        Tx_Count=('amount', 'count')
    ).reset_index()
    account_summary['Net_Difference'] = account_summary['Incoming'] - account_summary['Outgoing']

    st.dataframe(
        account_summary.sort_values("Total_Volume", ascending=False),
        column_config={
            "Total_Volume": st.column_config.NumberColumn("Total Volume", format="%,.2f"),
            "Outgoing": st.column_config.NumberColumn("Total Outgoing", format="%,.2f"),
            "Incoming": st.column_config.NumberColumn("Total Incoming", format="%,.2f"),
            "Net_Difference": st.column_config.NumberColumn("Net Balance", format="%,.2f"),
        },
        use_container_width=True, hide_index=True
    )
    st.download_button("Export CSV", filtered_df.to_csv(index=False).encode('utf-8'), "nugpay_report.csv")
else:
    st.info("Enter a Username or Account ID in the sidebar to begin.")
