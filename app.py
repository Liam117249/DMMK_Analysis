import streamlit as st
import pandas as pd
import urllib.parse
from datetime import datetime, timezone, timedelta
from stellar_logic import (
    analyze_stellar_account, 
    resolve_username_to_id, 
    resolve_id_to_name
)

# 1. Page Configuration
st.set_page_config(page_title="NUGpay Pro Dashboard", layout="wide")

# Inject Custom CSS to make HTML tables look like Streamlit native tables
st.markdown("""
<style>
    table.dataframe {
        width: 100%;
        border-collapse: collapse;
        border: none;
        font-family: sans-serif;
    }
    table.dataframe th, table.dataframe td {
        padding: 10px 12px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
        text-align: left;
    }
    table.dataframe th {
        font-size: 14px;
        color: rgba(128, 128, 128, 0.8);
        font-weight: 600;
    }
    table.dataframe tr:hover {
        background-color: rgba(128, 128, 128, 0.1);
    }
    a.account-link {
        text-decoration: none;
        color: #1f77b4;
        font-weight: 600;
    }
    a.account-link:hover {
        text-decoration: underline;
    }
</style>
""", unsafe_allow_html=True)

# 2. Session State Initialization
if 'stellar_data' not in st.session_state:
    st.session_state.stellar_data = None
if 'display_name' not in st.session_state:
    st.session_state.display_name = ""
if 'analysis_months' not in st.session_state:
    st.session_state.analysis_months = 1

# Streamlit Cache to remember queries for 1 hour
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_cached_analysis(target_id, months):
    return analyze_stellar_account(target_id, months=months)

# Centralized data loader
def load_account_data(identifier, months):
    with st.spinner(f"Resolving identity and fetching history for {identifier}..."):
        target_id = None
        current_name = identifier
        
        if identifier.startswith("G") and len(identifier) == 56:
            target_id = identifier
            found_name = resolve_id_to_name(identifier)
            if found_name: current_name = found_name
        else:
            target_id = resolve_username_to_id(identifier)
        
        if target_id:
            data = fetch_cached_analysis(target_id, months)
            if data:
                st.session_state.stellar_data = data
                st.session_state.display_name = current_name
                st.query_params["target_account"] = target_id
                st.query_params["name"] = current_name
                return True
            else:
                st.error("No transactions found.")
        else:
            st.error("Username or ID not found.")
        return False

# --- URL QUERY PARAMETER CHECK ---
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
    fetch_cached_analysis.clear() 
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
        # Fixed: Chronological month sorting instead of alphabetical
        chronological_months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
        available_months = [m for m in chronological_months if m in df['month_name'].unique()]
        months_list = ["All Months"] + available_months
        sel_month = st.selectbox("Filter by Month", months_list)
        
    with t2:
        temp_df = df if sel_month == "All Months" else df[df['month_name'] == sel_month]
        
        # Fixed: Numerical week sorting instead of alphabetical (e.g., Week 2 comes before Week 10)
        def extract_week(w):
            return int(w.replace("Week ", ""))
            
        available_weeks = sorted(temp_df['week_num'].unique().tolist(), key=extract_week)
        weeks_list = ["All Weeks"] + available_weeks
        sel_week = st.selectbox("Filter by Week", weeks_list)
        
    with t3:
        recency = st.radio("Quick Tracker", ["Full History", "Last 7 Days", "Last 24 Hours"], horizontal=True)

    # Apply Filtering Logic
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
    
    # --- SAFEGUARD: Check if the strict filters emptied the dataframe ---
    if filtered_df.empty:
        st.warning("No transactions found matching the selected filters.")
    else:
        # --- TRANSACTION TABLE (HTML) ---
        def format_val(row):
            return f"{row['amount']:,.2f}" if row['asset'] == "DMMK" else f"{row['amount']:,.7f}"
        
        filtered_df['Amount'] = filtered_df.apply(format_val, axis=1)
        
        def create_html_link(row):
            safe_name = urllib.parse.quote(row['other_account'])
            return f'<a class="account-link" href="/?target_account={row["other_account_id"]}&name={safe_name}" target="_self">{row["other_account"]}</a>'
        
        filtered_df['Other Account'] = filtered_df.apply(create_html_link, axis=1)
        
        display_tx_df = filtered_df[['timestamp', 'direction', 'Other Account', 'Amount', 'asset']].copy()
        display_tx_df.columns = ['Timestamp', 'Direction', 'Other Account', 'Amount', 'Asset']

        st.write("**Transaction History**")
        st.markdown(display_tx_df.to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

        # --- SUMMARY TABLE (HTML) ---
        st.markdown("---")
        st.subheader("Summary by Account")
        
        summary_asset = st.radio("Asset Filter", ["Both", "DMMK", "nUSDT"], horizontal=True)
        
        summary_df = filtered_df.copy()
        if summary_asset != "Both":
            summary_df = summary_df[summary_df['asset'] == summary_asset]

        if summary_df.empty:
            st.info(f"No {summary_asset} transactions found for this account under the current filters.")
        else:
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

            account_summary['Other Account'] = account_summary.apply(create_html_link, axis=1)

            account_summary['Total_Volume'] = account_summary['Total_Volume'].apply(lambda x: f"{x:,.2f}")
            account_summary['Incoming'] = account_summary['Incoming'].apply(lambda x: f"{x:,.2f}")
            account_summary['Outgoing'] = account_summary['Outgoing'].apply(lambda x: f"{x:,.2f}")
            account_summary['Net_Difference'] = account_summary['Net_Difference'].apply(lambda x: f"{x:,.2f}")

            display_summary_df = account_summary[['Other Account', 'asset', 'Total_Volume', 'Incoming', 'Outgoing', 'Net_Difference', 'Tx_Count']].copy()
            display_summary_df.columns = ['Other Account', 'Asset', 'Total Volume', 'Incoming', 'Outgoing', 'Net Balance', 'Tx Count']

            st.write("**Top 10 Accounts by Transaction Count**")
            st.markdown(display_summary_df.to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.download_button("Export CSV", filtered_df.to_csv(index=False).encode('utf-8'), "nugpay_report.csv")
else:
    st.info("Enter a Username or Account ID in the sidebar to begin.")
