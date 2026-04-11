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

# Custom CSS for table styling, vertical lines, and dialogue buttons
st.markdown("""
<style>
    html { scroll-behavior: smooth; }
    
    /* Standard Table Styling (used for History & Dialogs) */
    table.dataframe {
        width: 100%;
        border-collapse: collapse;
        border: 1px solid rgba(128, 128, 128, 0.3);
        font-family: sans-serif;
    }
    table.dataframe th, table.dataframe td {
        padding: 10px 12px;
        border: 1px solid rgba(128, 128, 128, 0.3);
        text-align: left;
    }
    table.dataframe th {
        font-size: 14px;
        color: rgba(128, 128, 128, 0.8);
        font-weight: 600;
        background-color: rgba(128, 128, 128, 0.05);
    }

    /* Vertical Line Logic for the Summary Section Body */
    .summary-col {
        border-right: 1px solid rgba(128, 128, 128, 0.3);
        padding: 8px 12px !important;
        height: 100%;
        display: flex;
        align-items: center;
    }
    .last-col {
        border-right: none;
    }

    a.account-link {
        text-decoration: none;
        color: #1f77b4;
        font-weight: 600;
    }
    
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
    
    /* Clean up button appearance for the 📝 icon */
    .stButton button {
        padding: 0px 5px;
        height: auto;
        border: none;
        background: transparent;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)

# 2. Session State & Cache
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

# 3. Dialogue Component
@st.dialog("Connection History", width="large")
def show_details_dialog(other_id, other_name, target_name, filtered_df):
    st.markdown(f"### History: {target_name} ↔ {other_name}")
    conn_df = filtered_df[filtered_df['other_account_id'] == other_id].copy()
    
    if conn_df.empty:
        st.warning("No transactions found.")
    else:
        conn_df['Date/Time'] = conn_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        conn_df['Amount_Disp'] = conn_df.apply(
            lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1
        )
        st.markdown(
            conn_df[['Date/Time', 'direction', 'Amount_Disp', 'asset']]
            .rename(columns={'direction':'Direction','Amount_Disp':'Amount','asset':'Asset'})
            .to_html(escape=False, index=False, classes="dataframe"), 
            unsafe_allow_html=True
        )

def load_account_data(identifier, months):
    with st.spinner("Analyzing data..."):
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

# 4. Sidebar Logic
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Account Name", "Account ID"])
user_input = st.sidebar.text_input("Enter Identifier", value=st.session_state.display_name if input_method == "Account Name" else st.session_state.target_id)
analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, st.session_state.analysis_months)

if st.sidebar.button("Analyze Account", use_container_width=True) and user_input:
    load_account_data(user_input, analysis_months)

# 5. Dashboard UI
if st.session_state.stellar_data:
    df = pd.DataFrame(st.session_state.stellar_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['month_year'] = df['timestamp'].dt.strftime('%B %Y')

    st.title(f"{st.session_state.display_name}*nugpay.app 🪙")
    
    # Balances
    dmmk_bal, nusdt_bal = fetch_balances(st.session_state.target_id)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.metric("DMMK", f"{dmmk_bal:,.2f}")
    b2.metric("nUSDT", f"{nusdt_bal:,.7f}")
    st.markdown("---")

    # Filters
    st.subheader("Interactive Filters")
    f1, f2 = st.columns(2)
    with f1:
        available_months = df.sort_values('timestamp', ascending=False)['month_year'].unique().tolist()
        sel_month = st.selectbox("Filter by Month", ["All Months"] + available_months)
    with f2:
        # REPLACED st.pills with st.multiselect to prevent version errors
        selected_assets = st.multiselect("Filter Assets", options=["DMMK", "nUSDT"], default=["DMMK", "nUSDT"])

    filtered_df = df[df['asset'].isin(selected_assets)]
    if sel_month != "All Months":
        filtered_df = filtered_df[filtered_df['month_year'] == sel_month]

    # Main Transaction Table
    st.subheader("Transaction History")
    display_df = filtered_df.copy()
    display_df['Date/Time'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    display_df['Other Account'] = display_df.apply(lambda r: f'<a class="account-link" href="/?target_account={r["other_account_id"]}&name={urllib.parse.quote(str(r["other_account"]))}&months={st.session_state.analysis_months}" target="_self">{r["other_account"]}</a>', axis=1)
    display_df['Amount_Disp'] = display_df.apply(lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1)
    
    st.markdown(display_df[['Date/Time', 'direction', 'Other Account', 'Amount_Disp', 'asset']].rename(columns={'direction':'Direction','Amount_Disp':'Amount','asset':'Asset'}).to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

    # --- SUMMARY SECTION WITH VERTICAL LINES ---
    st.markdown("<div id='summary-section' style='padding-top:40px;'></div>", unsafe_allow_html=True)
    st.subheader("Summary by Account")
    
    sum_prep = filtered_df.copy()
    sum_prep['In'] = sum_prep.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
    sum_prep['Out'] = sum_prep.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)

    account_summary = sum_prep.groupby(['other_account', 'other_account_id', 'asset']).agg(
        Out=('Out', 'sum'), In=('In', 'sum'),
        Vol=('amount', 'sum'), Count=('amount', 'count')
    ).reset_index()
    account_summary['Net'] = account_summary['In'] - account_summary['Out']
    account_summary = account_summary.sort_values("Count", ascending=False).head(15)

    # Static Header Table for alignment
    st.markdown("""
    <table class="dataframe">
        <thead>
            <tr>
                <th style="width:25%">Other Account</th>
                <th style="width:10%">Asset</th>
                <th style="width:15%">Total Volume</th>
                <th style="width:12%">Incoming</th>
                <th style="width:12%">Outgoing</th>
                <th style="width:16%">Net Balance</th>
                <th style="width:10%">Tx Count</th>
            </tr>
        </thead>
    </table>
    """, unsafe_allow_html=True)

    # Row Body with Vertical Lines using st.columns
    for i, row in account_summary.iterrows():
        # Match column proportions exactly with header
        cols = st.columns([2.5, 1, 1.5, 1.2, 1.2, 1.6, 1])
        
        # Mapping data to columns with <div> wrappers for vertical lines
        with cols[0]:
            st.markdown('<div class="summary-col">', unsafe_allow_html=True)
            ic1, ic2 = st.columns([0.2, 0.8])
            if ic1.button("📝", key=f"sum_{i}"):
                show_details_dialog(row['other_account_id'], row['other_account'], st.session_state.display_name, filtered_df)
            safe_name = urllib.parse.quote(str(row['other_account']))
            ic2.markdown(f'<a class="account-link" href="/?target_account={row["other_account_id"]}&name={safe_name}&months={st.session_state.analysis_months}" target="_self">{row["other_account"]}</a>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with cols[1]: 
            st.markdown('<div class="summary-col">', unsafe_allow_html=True)
            st.write(row['asset'])
            st.markdown('</div>', unsafe_allow_html=True)
        
        with cols[2]:
            st.markdown('<div class="summary-col">', unsafe_allow_html=True)
            st.write(f"{row['Vol']:,.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
        
        with cols[3]:
            st.markdown('<div class="summary-col">', unsafe_allow_html=True)
            st.write(f"{row['In']:,.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
            
        with cols[4]:
            st.markdown('<div class="summary-col">', unsafe_allow_html=True)
            st.write(f"{row['Out']:,.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
            
        with cols[5]:
            st.markdown('<div class="summary-col">', unsafe_allow_html=True)
            st.write(f"{row['Net']:,.2f}")
            st.markdown('</div>', unsafe_allow_html=True)
            
        with cols[6]:
            st.markdown('<div class="summary-col last-col">', unsafe_allow_html=True)
            st.write(str(row['Count']))
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('<hr style="margin:0; border-color:rgba(128,128,128,0.3)">', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button("Export CSV", df.to_csv().encode('utf-8'), f"{st.session_state.display_name}_data.csv", use_container_width=True)

else:
    st.info("Enter an account name or ID in the sidebar to begin.")
