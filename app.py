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
if 'analysis_months' not in st.session_state:
    st.session_state.analysis_months = 1

# Centralized data loader
def load_account_data(identifier, months):
    with st.spinner(f"Resolving identity for {identifier}..."):
        target_id = None
        current_name = identifier
        
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
                # Update URL parameters so users can share links
                st.query_params["target_account"] = target_id
                st.query_params["name"] = current_name
                return True
            else:
                st.error("No transactions found.")
        else:
            st.error("Username or ID not found.")
        return False

# --- URL QUERY PARAMETER CHECK ---
# If someone clicked a link from the dataframe, it opens a tab with parameters
target_from_url = st.query_params.get("target_account")
name_from_url = st.query_params.get("name")

if target_from_url and st.session_state.display_name != name_from_url:
    load_account_data(target_from_url, st.session_state.analysis_months)

# 3. Sidebar Configuration
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Username", "Account ID"])

if input_method == "Username":
    user_input = st.sidebar.text_input("Enter Name", placeholder="e.g. sithu")
else:
    user_input = st.sidebar.text_input("Enter Stellar ID", placeholder="G...")

analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, st.session_state.analysis_months)
st.session_state.analysis_months = analysis_months 

col_side1, col_side2 = st.sidebar.columns(2)
run_btn = col_side1.button("Analyze Account", use_container_width=True)
clear_btn = col_side2.button("Clear Cache", use_container_width=True)

if clear_btn:
    st.session_state.stellar_data = None
    st.session_state.display_name = ""
    st.query_params.clear()
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
    def format_val(row):
        return f"{row['amount']:,.2f}" if row['asset'] == "DMMK" else f"{row['amount']:,.7f}"
    
    filtered_df['formatted_amount'] = filtered_df.apply(format_val, axis=1)
    
    # Create the clickable link column data
    filtered_df['Account_Link'] = filtered_df.apply(
        lambda x: f"/?target_account={x['other_account_id']}&name={x['other_account']}", axis=1
    )

    st.write("**Transaction History**")
    st.dataframe(
        filtered_df[["timestamp", "direction", "Account_Link", "formatted_amount", "asset"]],
        column_config={
            "Account_Link": st.column_config.LinkColumn(
                "Other Account",
                # Regex extracts just the display name from the URL string for the UI
                display_text=r"name=([^&]+)"
            )
        },
        use_container_width=True, hide_index=True
    )

    # --- SUMMARY TABLE ---
    st.markdown("---")
    st.subheader("Summary by Account")
    
    summary_asset = st.radio("Asset Filter (Summary Only)", ["Both", "DMMK", "nUSDT"], horizontal=True)
    
    summary_df = filtered_df.copy()
    if summary_asset != "Both":
        summary_df = summary_df[summary_df['asset'] == summary_asset]

    summary_df['Incoming'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
    summary_df['Outgoing'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)

    account_summary = summary_df.groupby(['other_account', 'other_account_id', 'asset']).agg(
        Outgoing=('Outgoing', 'sum'),
        Incoming=('Incoming', 'sum'),
        Total_Volume=('amount', 'sum'),
        Tx_Count=('amount', 'count')
    ).reset_index()
    
    account_summary['Net_Difference'] = account_summary['Incoming'] - account_summary['Outgoing']
    account_summary = account_summary.sort_values("Tx_Count", ascending=False).head(10)

    # Re-apply the link generation for the summary table
    account_summary['Account_Link'] = account_summary.apply(
        lambda x: f"/?target_account={x['other_account_id']}&name={x['other_account']}", axis=1
    )

    st.write("**Top 10 Accounts by Transaction Count**")
    st.dataframe(
        account_summary[["Account_Link", "asset", "Total_Volume", "Incoming", "Outgoing", "Net_Difference", "Tx_Count"]],
        column_config={
            "Account_Link": st.column_config.LinkColumn(
                "Other Account",
                display_text=r"name=([^&]+)"
            ),
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
