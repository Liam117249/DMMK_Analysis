import streamlit as st
import pandas as pd
import urllib.parse
import calendar
from datetime import datetime, timezone, timedelta
from stellar_sdk import Server
from stellar_logic import (
    analyze_stellar_account, 
    resolve_username_to_id, 
    resolve_id_to_name
)

# 1. Page Configuration
st.set_page_config(page_title="NUGpay Pro Dashboard", layout="wide")

# Custom CSS to perfectly match the tables
st.markdown("""
<style>
    html { scroll-behavior: smooth; }
    
    /* Standard Table Styling */
    table.dataframe {
        width: 100%;
        border-collapse: collapse;
        border: 1px solid rgba(128, 128, 128, 0.2);
        font-family: sans-serif;
    }
    table.dataframe th, table.dataframe td {
        padding: 10px 12px;
        border: 1px solid rgba(128, 128, 128, 0.2);
        text-align: left;
    }
    table.dataframe th {
        font-size: 14px;
        color: rgba(128, 128, 128, 0.8);
        font-weight: 600;
        background-color: transparent;
    }
    table.dataframe tr:hover { background-color: rgba(128, 128, 128, 0.1); }
    
    /* Link Styling */
    a.account-link {
        text-decoration: none;
        color: #1f77b4;
        font-weight: 600;
    }
    a.account-link:hover { text-decoration: underline; }

    /* Summary Section Grid Styling to mimic Table Cells */
    .summary-cell {
        border: 1px solid rgba(128, 128, 128, 0.2);
        padding: 10px 12px;
        margin: -1px 0 0 -1px; /* Collapse borders */
        min-height: 50px;
        display: flex;
        align-items: center;
    }
    .summary-header {
        font-size: 14px;
        color: rgba(128, 128, 128, 0.8);
        font-weight: 600;
        background-color: transparent;
        border: 1px solid rgba(128, 128, 128, 0.2);
        padding: 10px 12px;
        margin: -1px 0 0 -1px;
    }

    /* Small Icon Button Styling */
    .stButton > button {
        padding: 0px 5px !important;
        height: 28px !important;
        background-color: transparent !important;
        border: none !important;
        font-size: 18px !important;
    }
    
    .subtle-jump { font-size: 0.85rem; color: #1f77b4; text-decoration: none; border-bottom: 1px dashed #1f77b4; }
    .back-top { font-size: 0.8rem; color: #aaa; text-decoration: none; float: right; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
</style>
""", unsafe_allow_html=True)

# 2. Session State Initialization
if 'stellar_data' not in st.session_state:
    st.session_state.stellar_data = None
if 'display_name' not in st.session_state:
    st.session_state.display_name = ""
if 'target_id' not in st.session_state:  
    st.session_state.target_id = ""
if 'analysis_months' not in st.session_state:
    url_months = st.query_params.get("months")
    st.session_state.analysis_months = int(url_months) if (url_months and url_months.isdigit()) else 1

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_cached_analysis(target_id, months):
    return analyze_stellar_account(target_id, months=months)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_balances(account_id):
    if not account_id: return 0.0, 0.0
    server = Server("https://horizon.stellar.org")
    try:
        account = server.accounts().account_id(account_id).call()
        balances = account.get('balances', [])
        dmmk, nusdt = 0.0, 0.0
        for b in balances:
            asset_code = b.get('asset_code')
            balance = float(b.get('balance', 0))
            if asset_code == 'DMMK': dmmk = balance * 1000.0  
            elif asset_code == 'nUSDT': nusdt = balance
        return dmmk, nusdt
    except Exception: return 0.0, 0.0

@st.dialog("Transaction Detail")
def show_account_details(other_name, other_id, asset_filter, source_df):
    st.write(f"Viewing history between **{st.session_state.display_name}** and **{other_name}**")
    st.caption(f"Asset: {asset_filter}")
    
    detail_df = source_df[
        (source_df['other_account_id'] == other_id) & (source_df['asset'] == asset_filter)
    ].copy()
    
    detail_df['Date/Time'] = detail_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    detail_df['Amount_Disp'] = detail_df.apply(lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1)
    
    st.markdown(detail_df[['Date/Time', 'direction', 'Amount_Disp', 'asset']]
                .rename(columns={'direction':'Direction','Amount_Disp':'Amount','asset':'Asset'})
                .to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

def load_account_data(identifier, months):
    with st.spinner(f"Loading data..."):
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
                st.session_state.target_id = target_id 
                st.query_params["target_account"] = target_id
                st.query_params["name"] = current_name
                st.query_params["months"] = str(months)
                return True
    return False

# URL Check
target_from_url = st.query_params.get("target_account")
if target_from_url and st.session_state.display_name != st.query_params.get("name"):
    load_account_data(target_from_url, st.session_state.analysis_months)

# 3. Sidebar
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Account Name", "Account ID"])
if input_method == "Account Name":
    user_input = st.sidebar.text_input("Enter Name", value=st.session_state.display_name)
else:
    user_input = st.sidebar.text_input("Enter Account ID", value=st.session_state.target_id)

analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, st.session_state.analysis_months)
st.session_state.analysis_months = analysis_months 

if st.sidebar.button("Analyze Account", use_container_width=True) and user_input:
    load_account_data(user_input, analysis_months)

# 4. Main Dashboard
if st.session_state.stellar_data:
    df = pd.DataFrame(st.session_state.stellar_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['month_year'] = df['timestamp'].dt.strftime('%B %Y')
    df['day'] = df['timestamp'].dt.day

    st.title(f"{st.session_state.display_name}*nugpay.app 🪙")
    
    # Balance Section
    dmmk_bal, nusdt_bal = fetch_balances(st.session_state.target_id)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.metric("DMMK", f"{dmmk_bal:,.2f}")
    b2.metric("nUSDT", f"{nusdt_bal:,.7f}")
    st.markdown("---")

    # Filters (Omitted logic for brevity, keeping same structure)
    selected_assets = st.pills("Assets", options=["DMMK", "nUSDT"], default=["DMMK", "nUSDT"])
    filtered_df = df[df['asset'].isin(selected_assets)]

    # --- TRANSACTION HISTORY TABLE ---
    st.write("**Transaction History**")
    display_df = filtered_df.copy()
    display_df['Date/Time'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    def create_link(row):
        safe_name = urllib.parse.quote(str(row['other_account']))
        return f'<a class="account-link" href="/?target_account={row["other_account_id"]}&name={safe_name}&months={st.session_state.analysis_months}" target="_self">{row["other_account"]}</a>'
    
    display_df['Other Account'] = display_df.apply(create_link, axis=1)
    display_df['Amount'] = display_df.apply(lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1)
    
    st.markdown(display_df[['Date/Time', 'direction', 'Other Account', 'Amount', 'asset']]
                .rename(columns={'direction':'Direction','asset':'Asset'})
                .to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

    # --- SUMMARY BY ACCOUNT SECTION ---
    st.markdown("<div id='summary-section' style='padding-top:40px;'></div>", unsafe_allow_html=True)
    st.subheader("Summary by Account")
    
    # Aggregation
    summary_df = filtered_df.copy()
    summary_df['Incoming'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
    summary_df['Outgoing'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)
    account_summary = summary_df.groupby(['other_account', 'other_account_id', 'asset']).agg(
        Outgoing=('Outgoing', 'sum'), Incoming=('Incoming', 'sum'),
        Total_Volume=('amount', 'sum'), Tx_Count=('amount', 'count')
    ).reset_index()
    account_summary['Net_Difference'] = account_summary['Incoming'] - account_summary['Outgoing']
    account_summary = account_summary.sort_values("Tx_Count", ascending=False).head(15)

    # Header Row (Manual Table Simulation)
    cols = [2, 1, 1.5, 1.5, 1.5, 0.6]
    h_col1, h_col2, h_col3, h_col4, h_col5, h_col6 = st.columns(cols, gap="none")
    h_col1.markdown('<div class="summary-header">Other Account</div>', unsafe_allow_html=True)
    h_col2.markdown('<div class="summary-header">Asset</div>', unsafe_allow_html=True)
    h_col3.markdown('<div class="summary-header">Incoming</div>', unsafe_allow_html=True)
    h_col4.markdown('<div class="summary-header">Outgoing</div>', unsafe_allow_html=True)
    h_col5.markdown('<div class="summary-header">Net Balance</div>', unsafe_allow_html=True)
    h_col6.markdown('<div class="summary-header">Details</div>', unsafe_allow_html=True)

    # Data Rows
    for i, row in account_summary.iterrows():
        r1, r2, r3, r4, r5, r6 = st.columns(cols, gap="none")
        
        safe_name = urllib.parse.quote(str(row['other_account']))
        link = f'<a class="account-link" href="/?target_account={row["other_account_id"]}&name={safe_name}&months={st.session_state.analysis_months}" target="_self">{row["other_account"]}</a>'
        
        r1.markdown(f'<div class="summary-cell">{link}</div>', unsafe_allow_html=True)
        r2.markdown(f'<div class="summary-cell">{row["asset"]}</div>', unsafe_allow_html=True)
        r3.markdown(f'<div class="summary-cell">{row["Incoming"]:,.2f}</div>', unsafe_allow_html=True)
        r4.markdown(f'<div class="summary-cell">{row["Outgoing"]:,.2f}</div>', unsafe_allow_html=True)
        r5.markdown(f'<div class="summary-cell">{row["Net_Difference"]:,.2f}</div>', unsafe_allow_html=True)
        
        with r6:
            st.markdown('<div class="summary-cell" style="justify-content: center;">', unsafe_allow_html=True)
            if st.button("📑", key=f"btn_{i}"):
                show_account_details(row['other_account'], row['other_account_id'], row['asset'], filtered_df)
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<br><a href="#top-anchor" class="back-top">↑ Back to Top</a>', unsafe_allow_html=True)

else:
    st.info("Search an account to start.")
