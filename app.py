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

# Custom CSS - Optimized to ensure both tables look identical
st.markdown("""
<style>
    html { scroll-behavior: smooth; }
    .reportview-container { background: #ffffff; }
    
    /* Standard Table Styling used for both sections */
    table.dataframe {
        width: 100%;
        border-collapse: collapse;
        border: none;
        font-family: sans-serif;
    }
    table.dataframe th, table.dataframe td {
        padding: 12px 15px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
        text-align: left;
    }
    table.dataframe th {
        font-size: 14px;
        color: rgba(128, 128, 128, 0.8);
        font-weight: 600;
        background-color: transparent;
    }
    table.dataframe tr:hover { background-color: rgba(128, 128, 128, 0.05); }
    
    a.account-link {
        text-decoration: none;
        color: #1f77b4;
        font-weight: 600;
    }
    a.account-link:hover { text-decoration: underline; }
    
    /* Removing Streamlit button borders to make the icon look like part of the table */
    .stButton > button {
        border: none;
        background: transparent;
        padding: 0;
        margin: 0;
        font-size: 1.2rem;
    }
    .stButton > button:hover {
        background: transparent;
        color: #1f77b4;
    }
    
    .back-top {
        font-size: 0.8rem;
        color: #aaa !important;
        text-decoration: none;
        float: right;
    }
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
    st.session_state.analysis_months = 1

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
    st.markdown(f"**Connection:** `{st.session_state.display_name}` ↔ `{other_name}`")
    detail_df = source_df[(source_df['other_account_id'] == other_id) & (source_df['asset'] == asset_filter)].copy()
    
    detail_df['Date/Time'] = detail_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    detail_df['Amount_Disp'] = detail_df.apply(lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1)
    
    st.markdown(detail_df[['Date/Time', 'direction', 'Amount_Disp', 'asset']]
                .rename(columns={'direction':'Direction','Amount_Disp':'Amount','asset':'Asset'})
                .to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

def load_account_data(identifier, months):
    with st.spinner("Fetching data..."):
        target_id = identifier if (identifier.startswith("G") and len(identifier) == 56) else resolve_username_to_id(identifier)
        if target_id:
            data = fetch_cached_analysis(target_id, months)
            if data:
                st.session_state.stellar_data = data
                st.session_state.target_id = target_id
                st.session_state.display_name = resolve_id_to_name(target_id) or identifier
                return True
    return False

# Sidebar
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Account Name", "Account ID"])
user_input = st.sidebar.text_input("Input", value=st.session_state.display_name if input_method == "Account Name" else st.session_state.target_id)
analysis_months = st.sidebar.slider("Months", 1, 12, st.session_state.analysis_months)

if st.sidebar.button("Analyze Account", use_container_width=True):
    st.session_state.analysis_months = analysis_months
    load_account_data(user_input, analysis_months)

# Main UI
if st.session_state.stellar_data:
    df = pd.DataFrame(st.session_state.stellar_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # --- TOP TABLE: TRANSACTION HISTORY ---
    st.subheader("Transaction History")
    display_df = df.copy().head(10) # Limit for clean view
    display_df['Date/Time'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    display_df['Other Account'] = display_df.apply(lambda r: f'<a class="account-link" href="#">{r["other_account"]}</a>', axis=1)
    display_df['Amount_Disp'] = display_df.apply(lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1)
    
    st.markdown(display_df[['Date/Time', 'direction', 'Other Account', 'Amount_Disp', 'asset']]
                .rename(columns={'direction':'Direction','Amount_Disp':'Amount','asset':'Asset'})
                .to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

    # --- BOTTOM TABLE: SUMMARY BY ACCOUNT ---
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.subheader("Summary by Account")
    
    summary_df = df.copy()
    summary_df['Incoming'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
    summary_df['Outgoing'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)
    
    acc_sum = summary_df.groupby(['other_account', 'other_account_id', 'asset']).agg(
        Incoming=('Incoming', 'sum'), Outgoing=('Outgoing', 'sum'), Tx_Count=('amount', 'count')
    ).reset_index()
    acc_sum['Net_Balance'] = acc_sum['Incoming'] - acc_sum['Outgoing']
    acc_sum = acc_sum.sort_values('Tx_Count', ascending=False).head(10)

    # Replicating the Top Table structure exactly
    # 1. Header row
    h1, h2, h3, h4, h5, h6 = st.columns([3, 1, 2, 2, 2, 1])
    h1.markdown("**Other Account**")
    h2.markdown("**Asset**")
    h3.markdown("**Incoming**")
    h4.markdown("**Outgoing**")
    h5.markdown("**Net Balance**")
    h6.markdown("**Details**")
    st.markdown("<hr style='margin:0; opacity:0.2;'>", unsafe_allow_html=True)

    # 2. Data rows
    for i, row in acc_sum.iterrows():
        r1, r2, r3, r4, r5, r6 = st.columns([3, 1, 2, 2, 2, 1])
        
        # We wrap the content in a div with a bottom border to mimic the table 1:1
        border_style = "border-bottom: 1px solid rgba(128, 128, 128, 0.2); padding: 12px 5px;"
        
        r1.markdown(f"<div style='{border_style}'><a class='account-link' href='#'>{row['other_account']}</a></div>", unsafe_allow_html=True)
        r2.markdown(f"<div style='{border_style}'>{row['asset']}</div>", unsafe_allow_html=True)
        r3.markdown(f"<div style='{border_style}'>{row['Incoming']:,.2f}</div>", unsafe_allow_html=True)
        r4.markdown(f"<div style='{border_style}'>{row['Outgoing']:,.2f}</div>", unsafe_allow_html=True)
        r5.markdown(f"<div style='{border_style}'>{row['Net_Balance']:,.2f}</div>", unsafe_allow_html=True)
        
        with r6:
            st.markdown(f"<div style='{border_style}'>", unsafe_allow_html=True)
            if st.button("📑", key=f"sum_btn_{i}"):
                show_account_details(row['other_account'], row['other_account_id'], row['asset'], df)
            st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<br><a href="#" class="back-top">↑ Back to Top</a>', unsafe_allow_html=True)

else:
    st.info("Enter an account to begin.")
