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

# Custom CSS for UI refinement
st.markdown("""
<style>
    html { scroll-behavior: smooth; }
    
    /* Table Styling */
    table.dataframe {
        width: 100%;
        border-collapse: collapse;
        border: none;
        font-family: sans-serif;
    }
    table.dataframe th, table.dataframe td {
        padding: 10px 12px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
    }
    
    /* Aligning Headers and Numbers */
    table.dataframe th {
        font-size: 14px;
        color: rgba(128, 128, 128, 0.8);
        font-weight: 600;
        text-align: left;
    }
    /* Right-align numeric columns in HTML tables */
    table.dataframe td:nth-child(4), 
    table.dataframe td:nth-child(5),
    table.dataframe td:nth-child(6),
    table.dataframe td:nth-child(7) {
        text-align: right;
    }

    table.dataframe tr:hover { background-color: rgba(128, 128, 128, 0.1); }
    
    a.account-link {
        text-decoration: none;
        color: #1f77b4;
        font-weight: 600;
    }
    
    /* Sidebar Button Styling */
    div[data-testid="stSidebar"] .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
        border: 1px solid rgba(31, 119, 180, 0.2);
    }
    div[data-testid="stSidebar"] button[kind="secondary"]:hover {
        border-color: #1f77b4;
        color: #1f77b4;
    }

    /* Summary Section Numeric Alignment */
    .num-align { text-align: right; }

    /* Dialog/Icon Button */
    .stButton > button {
        padding: 0px 5px;
        height: 25px;
        min-height: 25px;
        background: transparent;
        border: none;
        font-size: 16px;
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
                st.session_state.target_id = target_id
                st.query_params["target_account"] = target_id
                st.query_params["name"] = current_name
                st.query_params["months"] = str(months)
                return True
        st.error("Account details or transactions not found.")
        return False

@st.dialog("Transaction History Details", width="large")
def show_transaction_details(other_account_id, other_account_name, asset_type):
    st.write(f"**Dashboard Account:** `{st.session_state.display_name}`")
    st.write(f"**Other Account:** `{other_account_name}`")
    raw_df = pd.DataFrame(st.session_state.stellar_data)
    filtered = raw_df[(raw_df['other_account_id'] == other_account_id) & (raw_df['asset'] == asset_type)].copy()
    if not filtered.empty:
        filtered['Date/Time'] = filtered['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        filtered['Amount_Disp'] = filtered.apply(lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1)
        st.markdown(filtered[['Date/Time', 'direction', 'Amount_Disp', 'asset']]
                    .rename(columns={'direction':'Direction','Amount_Disp':'Amount','asset':'Asset'})
                    .to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

target_from_url = st.query_params.get("target_account")
if target_from_url and st.session_state.display_name != st.query_params.get("name"):
    load_account_data(target_from_url, st.session_state.analysis_months)

# 3. Sidebar Configuration
st.sidebar.header("Configuration")
input_method = st.sidebar.radio("Search By", ["Account Name", "Account ID"])

if input_method == "Account Name":
    user_input = st.sidebar.text_input("Enter Name", value=st.session_state.display_name, placeholder="e.g. sithu")
else:
    user_input = st.sidebar.text_input("Enter Account ID", value=st.session_state.target_id, placeholder="G...")

analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, st.session_state.analysis_months)
st.session_state.analysis_months = analysis_months

# Refined Sidebar Buttons
col_side1, col_side2 = st.sidebar.columns(2)
if col_side1.button("✨ Analyze", use_container_width=True, type="primary") and user_input:
    load_account_data(user_input, analysis_months)
if col_side2.button("🗑️ Clear", use_container_width=True):
    st.session_state.stellar_data = None
    st.session_state.display_name = ""
    st.session_state.target_id = ""
    st.query_params.clear()
    fetch_cached_analysis.clear()
    st.rerun()

st.markdown("<div id='top-anchor'></div>", unsafe_allow_html=True)
if st.session_state.display_name:
    st.title(f"{st.session_state.display_name}*nugpay.app 🪙")
else:
    st.title("NUGpay User Analytics")

if st.session_state.stellar_data:
    df = pd.DataFrame(st.session_state.stellar_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['month_year'] = df['timestamp'].dt.strftime('%B %Y')
    df['day'] = df['timestamp'].dt.day

    st.subheader("Current Balance")
    dmmk_bal, nusdt_bal = fetch_balances(st.session_state.target_id)
    b1, b2, _ = st.columns([1, 1, 2])
    b1.metric("DMMK", f"{dmmk_bal:,.2f}")
    b2.metric("nUSDT", f"{nusdt_bal:,.7f}")
    st.markdown("---")

    st.subheader("Interactive Filters")
    filter_mode = st.radio("Date Filter Mode", ["Standard (Month/Week)", "Custom Date Range"], horizontal=True)
    t1, t2, t3 = st.columns(3)
    start_date, end_date = None, None

    if filter_mode == "Standard (Month/Week)":
        with t1:
            available_months = df.sort_values('timestamp', ascending=False)['month_year'].unique().tolist()
            sel_month = st.selectbox("Filter by Month", ["All Months"] + available_months)
        with t2:
            if sel_month == "All Months":
                sel_week = st.selectbox("Filter by Week", ["All Weeks"], disabled=True)
            else:
                month_name, year_str = sel_month.split(" ")
                month_idx = list(calendar.month_name).index(month_name)
                _, last_day = calendar.monthrange(int(year_str), month_idx)
                dynamic_weeks = ["1 - 7 (First Week)", "8 - 14 (Second Week)", "15 - 21 (Third Week)", f"22 - {last_day} (Fourth Week)"]
                sel_week = st.selectbox("Filter by Week", ["All Weeks"] + dynamic_weeks)
    else:
        with t1:
            date_range = st.date_input("Select Range", value=(df['timestamp'].min().date(), df['timestamp'].max().date()))
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range

    with t3:
        recency = st.radio("Quick Tracker", ["Full History", "Last 7 Days", "Last 24 Hours"], horizontal=True)
        st.markdown('<a href="#summary-section" class="subtle-jump">Jump to Account Summary</a>', unsafe_allow_html=True)

    selected_assets = st.pills("Filter Assets", options=["DMMK", "nUSDT"], default=["DMMK", "nUSDT"], selection_mode="multi")

    filtered_df = df.copy()
    if selected_assets:
        filtered_df = filtered_df[filtered_df['asset'].isin(selected_assets)]
    else:
        filtered_df = pd.DataFrame(columns=df.columns)

    if filter_mode == "Standard (Month/Week)":
        if sel_month != "All Months":
            filtered_df = filtered_df[filtered_df['month_year'] == sel_month]
            if sel_week != "All Weeks":
                bounds = sel_week.split(" (")[0].split(" - ")
                filtered_df = filtered_df[filtered_df['day'].between(int(bounds[0]), int(bounds[1]))]
    elif start_date and end_date:
        filtered_df = filtered_df[(filtered_df['timestamp'].dt.date >= start_date) & (filtered_df['timestamp'].dt.date <= end_date)]
    
    now = datetime.now(timezone.utc)
    if recency == "Last 7 Days": filtered_df = filtered_df[filtered_df['timestamp'] >= (now - timedelta(days=7))]
    elif recency == "Last 24 Hours": filtered_df = filtered_df[filtered_df['timestamp'] >= (now - timedelta(hours=24))]

    if not selected_assets:
        st.info("Select an asset to view data.")
    elif filtered_df.empty:
        st.warning("No data found for this selection.")
    else:
        # History Table
        display_df = filtered_df.copy()
        display_df['Date/Time'] = display_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        def create_link(row):
            safe_name = urllib.parse.quote(str(row['other_account']))
            return f'<a class="account-link" href="/?target_account={row["other_account_id"]}&name={safe_name}&months={st.session_state.analysis_months}" target="_self">{row["other_account"]}</a>'
        
        display_df['Other Account'] = display_df.apply(create_link, axis=1)
        display_df['Amount_Disp'] = display_df.apply(lambda r: f"{r['amount']:,.2f}" if r['asset'] == "DMMK" else f"{r['amount']:,.7f}", axis=1)
        st.write("**Transaction History**")
        st.markdown(display_df[['Date/Time', 'direction', 'Other Account', 'Amount_Disp', 'asset']]
                    .rename(columns={'direction':'Direction','Amount_Disp':'Amount','asset':'Asset'})
                    .to_html(escape=False, index=False, classes="dataframe"), unsafe_allow_html=True)

        # Summary Section
        st.markdown("<div id='summary-section' style='padding-top:20px;'></div>", unsafe_allow_html=True)
        st.markdown("---")
        st.subheader("Summary by Account")
        
        s1, s2 = st.columns([2, 1])
        sort_metric = s1.selectbox("Sort Summary By", options=["Tx_Count", "Total_Volume", "Net_Difference", "Incoming", "Outgoing"], format_func=lambda x: x.replace("_", " "))
        sort_order = s2.radio("Order", ["Ascending", "Descending"], index=1, horizontal=True)
        
        summary_df = filtered_df.copy()
        summary_df['Incoming'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
        summary_df['Outgoing'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)
        account_summary = summary_df.groupby(['other_account', 'other_account_id', 'asset']).agg(
            Outgoing=('Outgoing', 'sum'), Incoming=('Incoming', 'sum'),
            Total_Volume=('amount', 'sum'), Tx_Count=('amount', 'count')
        ).reset_index()
        account_summary['Net_Difference'] = account_summary['Incoming'] - account_summary['Outgoing']
        account_summary = account_summary.sort_values(sort_metric, ascending=(sort_order == "Ascending")).head(10)

        # Right-aligned Summary Table Headers
        cols = st.columns([2.5, 1, 1.5, 1.5, 1.5, 1.5, 1])
        headers = ['Other Account', 'Asset', 'Total Volume', 'Incoming', 'Outgoing', 'Net Balance', 'Tx Count']
        for i, (col, h) in enumerate(zip(cols, headers)):
            # Columns 2 onwards (indices 2-6) are right-aligned
            align = "right" if i >= 2 else "left"
            col.markdown(f"<div style='text-align:{align}; font-weight:bold;'>{h}</div>", unsafe_allow_html=True)
        st.divider()

        for idx, row in account_summary.iterrows():
            c1, c2, c3, c4, c5, c6, c7 = st.columns([2.5, 1, 1.5, 1.5, 1.5, 1.5, 1])
            with c1:
                inner_col1, inner_col2 = st.columns([0.8, 0.2])
                with inner_col1:
                    safe_name = urllib.parse.quote(str(row['other_account']))
                    link_html = f'<a class="account-link" href="/?target_account={row["other_account_id"]}&name={safe_name}&months={st.session_state.analysis_months}" target="_self">{row["other_account"]}</a>'
                    st.markdown(link_html, unsafe_allow_html=True)
                with inner_col2:
                    if st.button("📜", key=f"btn_{idx}_{row['asset']}"):
                        show_transaction_details(row['other_account_id'], row['other_account'], row['asset'])
            
            c2.text(row['asset'])
            # Numeric columns with explicit right-alignment
            c3.markdown(f"<div class='num-align'>{row['Total_Volume']:,.2f}</div>", unsafe_allow_html=True)
            c4.markdown(f"<div class='num-align'>{row['Incoming']:,.2f}</div>", unsafe_allow_html=True)
            c5.markdown(f"<div class='num-align'>{row['Outgoing']:,.2f}</div>", unsafe_allow_html=True)
            c6.markdown(f"<div class='num-align'>{row['Net_Difference']:,.2f}</div>", unsafe_allow_html=True)
            c7.markdown(f"<div class='num-align'>{row['Tx_Count']}</div>", unsafe_allow_html=True)
            st.markdown('<hr style="margin:0; border-color:rgba(128,128,128,0.2)">', unsafe_allow_html=True)

        st.markdown("### Export Data")
        ex_col1, ex_col2 = st.columns(2)
        with ex_col1:
            history_csv = filtered_df[['timestamp', 'direction', 'other_account', 'amount', 'asset']].to_csv(index=False).encode('utf-8')
            st.download_button(label="⬇️ Export Transaction History (CSV)", data=history_csv, file_name=f"{st.session_state.display_name}_history.csv", mime="text/csv", use_container_width=True)
        with ex_col2:
            clean_sum = account_summary.rename(columns={'other_account':'Other Account','asset':'Asset','Total_Volume':'Total Volume','Net_Difference':'Net Balance','Tx_Count':'Tx Count'})
            summary_csv = clean_sum[['Other Account','Asset','Total Volume','Incoming','Outgoing','Net Balance','Tx Count']].to_csv(index=False).encode('utf-8')
            st.download_button(label="⬇️ Export Account Summary (CSV)", data=summary_csv, file_name=f"{st.session_state.display_name}_summary.csv", mime="text/csv", use_container_width=True)

        st.markdown('---')
        st.markdown('<a href="#top-anchor" class="back-top">↑ Back to Top</a>', unsafe_allow_html=True)
else:
    st.info("Enter an Account Name or Account ID in the sidebar to begin.")
