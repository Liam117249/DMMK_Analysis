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

# Centralized loading function for both UI buttons and row clicks
def load_account_data(identifier, months):
    with st.spinner(f"Resolving identity for {identifier}..."):
        target_id = None
        current_name = identifier
        
        # Determine if input is a raw G-Address or a Username
        if identifier.startswith("G") and len(identifier) == 56:
            target_id = identifier
            found_name = resolve_id_to_name(identifier)
            if found_name: current_name = found_name
        else:
            target_id = resolve_username_to_id(identifier)
        
        if target_id:
            data = analyze_stellar_account(target_id, months=months)
            if data:
                st.session_state.stellar_data = data
                st.session_state.display_name = current_name
                return True
            else:
                st.error("No transactions found.")
        else:
            st.error("Username or ID not found.")
        return False

# Handle Navigation from clicked rows
if 'next_account_to_load' in st.session_state:
    acc_to_load = st.session_state.next_account_to_load
    del st.session_state.next_account_to_load
    load_account_data(acc_to_load, st.session_state.get('analysis_months', 1))

# 3. Sidebar
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Username", "Account ID"])

if input_method == "Username":
    user_input = st.sidebar.text_input("Enter Name", placeholder="e.g. sithu")
else:
    user_input = st.sidebar.text_input("Enter Stellar ID", placeholder="G...")

analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, 1)
st.session_state.analysis_months = analysis_months 

col_side1, col_side2 = st.sidebar.columns(2)
run_btn = col_side1.button("Analyze Account", use_container_width=True)
clear_btn = col_side2.button("Clear Cache", use_container_width=True)

if clear_btn:
    st.session_state.stellar_data = None
    st.session_state.display_name = ""
    st.rerun()

if run_btn and user_input:
    load_account_data(user_input, analysis_months)

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
    st.write("**Transaction History** (Click a row to analyze that account)")
    def format_val(row):
        return f"{row['amount']:,.2f}" if row['asset'] == "DMMK" else f"{row['amount']:,.7f}"
    
    filtered_df['formatted_amount'] = filtered_df.apply(format_val, axis=1)
    
    # Selection event handling for Tx Table
    tx_event = st.dataframe(
        filtered_df[["timestamp", "direction", "other_account", "formatted_amount", "asset"]],
        use_container_width=True, hide_index=True,
        selection_mode="single-row",
        on_select="rerun"
    )
    
    if tx_event.selection.rows:
        sel_idx = tx_event.selection.rows[0]
        selected_id = filtered_df.iloc[sel_idx]['other_account_id']
        st.session_state.next_account_to_load = selected_id
        st.rerun()

    # --- SUMMARY TABLE ---
    st.markdown("---")
    st.subheader("Summary by Account")
    
    # Asset Filter specific to Summary section
    summary_asset = st.radio("Asset Filter (Summary Only)", ["Both", "DMMK", "nUSDT"], horizontal=True)
    
    summary_df = filtered_df.copy()
    if summary_asset != "Both":
        summary_df = summary_df[summary_df['asset'] == summary_asset]

    summary_df['Incoming'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
    summary_df['Outgoing'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)

    # Grouping by both Display Name and ID so we retain the ID for clicking
    account_summary = summary_df.groupby(['other_account', 'other_account_id', 'asset']).agg(
        Outgoing=('Outgoing', 'sum'),
        Incoming=('Incoming', 'sum'),
        Total_Volume=('amount', 'sum'),
        Tx_Count=('amount', 'count')
    ).reset_index()
    
    account_summary['Net_Difference'] = account_summary['Incoming'] - account_summary['Outgoing']

    # Filter Top 10 by Transaction Count Descending
    account_summary = account_summary.sort_values("Tx_Count", ascending=False).head(10)

    st.write("**Top 10 Accounts by Transaction Count** (Click a row to analyze that account)")
    
    # Selection event handling for Summary Table
    summary_event = st.dataframe(
        account_summary[["other_account", "asset", "Total_Volume", "Incoming", "Outgoing", "Net_Difference", "Tx_Count"]],
        column_config={
            "Total_Volume": st.column_config.NumberColumn("Total Volume", format="%,.2f"),
            "Outgoing": st.column_config.NumberColumn("Total Outgoing", format="%,.2f"),
            "Incoming": st.column_config.NumberColumn("Total Incoming", format="%,.2f"),
            "Net_Difference": st.column_config.NumberColumn("Net Balance", format="%,.2f"),
        },
        use_container_width=True, hide_index=True,
        selection_mode="single-row",
        on_select="rerun"
    )

    if summary_event.selection.rows:
        sel_idx = summary_event.selection.rows[0]
        selected_id = account_summary.iloc[sel_idx]['other_account_id']
        st.session_state.next_account_to_load = selected_id
        st.rerun()

    st.download_button("Export CSV", filtered_df.to_csv(index=False).encode('utf-8'), "nugpay_report.csv")
else:
    st.info("Enter a Username or Account ID in the sidebar to begin.")
