import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
from stellar_logic import analyze_stellar_account

# 1. Page Configuration
st.set_page_config(page_title="NUGpay Pro Dashboard", layout="wide")

# 2. Session State Initialization
if 'stellar_data' not in st.session_state:
    st.session_state.stellar_data = None
if 'last_id' not in st.session_state:
    st.session_state.last_id = ""

# 3. Sidebar
st.sidebar.header("Configuration")

# Toggle between ID and Username
input_type = st.sidebar.radio("Input Type", ["Account ID (G...)", "Stellar Address (name*domain)"])

if input_type == "Account ID (G...)":
    user_input = st.sidebar.text_input("Enter ID", placeholder="GDMMKKNI...")
else:
    user_input = st.sidebar.text_input("Enter Username", placeholder="user*nugpay.app")

analysis_months = st.sidebar.slider("Timeframe (Months)", 1, 12, 1)

# Action Buttons
col_side1, col_side2 = st.sidebar.columns(2)
run_btn = col_side1.button("Analyze Account", use_container_width=True)
clear_btn = col_side2.button("Clear Cache", use_container_width=True)

if run_btn and user_input:
    with st.spinner("Resolving Identity & Fetching Data..."):
        target_id = user_input
        
        # If user provided a name, resolve it to a G-address first
        if "*" in user_input:
            from stellar_logic import resolve_username_to_id
            resolved_id = resolve_username_to_id(user_input)
            if resolved_id:
                target_id = resolved_id
            else:
                st.error("Could not find a Stellar ID for that username.")
                target_id = None

        if target_id:
            data = analyze_stellar_account(target_id, months=analysis_months)
            if data:
                st.session_state.stellar_data = data
                st.session_state.last_id = target_id
            else:
                st.error("No DMMK or nUSDT transactions found for this account.")
# 4. Main Dashboard Logic
st.title("NUGpay User Analytics")

if st.session_state.stellar_data:
    df = pd.DataFrame(st.session_state.stellar_data)

    # --- ADVANCED TIME FILTERS ---
    st.subheader("Interactive Filters")
    t1, t2, t3 = st.columns(3)
    
    with t1:
        months = ["All Months"] + sorted(df['month_name'].unique().tolist())
        sel_month = st.selectbox("Filter by Month", months)
    with t2:
        # Show weeks only for selected month
        temp_df = df if sel_month == "All Months" else df[df['month_name'] == sel_month]
        weeks = ["All Weeks"] + sorted(temp_df['week_num'].unique().tolist())
        sel_week = st.selectbox("Filter by Week", weeks)
    with t3:
        recency = st.radio("Quick Tracker", ["Full History", "Last 7 Days", "Last 24 Hours"], horizontal=True)

    # Apply Filters
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

    # --- SORTING & ASSETS ---
    st.markdown("---")
    f1, f2, f3 = st.columns(3)
    with f1:
        asset_choice = st.multiselect("Active Assets", ["DMMK", "nUSDT"], default=["DMMK", "nUSDT"])
        filtered_df = filtered_df[filtered_df['asset'].isin(asset_choice)]
    with f2:
        sort_order = st.selectbox("Order by Amount", ["Newest First", "Most to Least", "Least to Most"])
    with f3:
        top_10 = st.checkbox("Show Top 10 Accounts Only")

    # Sorting
    if sort_order == "Newest First":
        filtered_df = filtered_df.sort_values("timestamp", ascending=False)
    elif sort_order == "Most to Least":
        filtered_df = filtered_df.sort_values("amount", ascending=False)
    else:
        filtered_df = filtered_df.sort_values("amount", ascending=True)

    if top_10:
        top_list = filtered_df.groupby('other_account')['amount'].sum().nlargest(10).index
        filtered_df = filtered_df[filtered_df['other_account'].isin(top_list)]

    # --- DISPLAY ---
    def format_val(row):
        return f"{row['amount']:,.2f}" if row['asset'] == "DMMK" else f"{row['amount']:,.7f}"
    
    filtered_df['formatted_amount'] = filtered_df.apply(format_val, axis=1)

    st.dataframe(
        filtered_df[["timestamp", "direction", "other_account", "formatted_amount", "asset"]],
        use_container_width=True,
        hide_index=True
    )

    st.download_button("Export CSV", filtered_df.to_csv(index=False).encode('utf-8'), "nugpay_report.csv")


    ################################
    # --- ACCOUNT SUMMARY TABLE ---
    # --- ACCOUNT SUMMARY TABLE ---
    st.markdown("---")
    st.subheader("Summary by Account")

    # 1. Create separate columns for Incoming and Outgoing to allow summing
    summary_df = filtered_df.copy()
    summary_df['Incoming'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "INCOMING" else 0, axis=1)
    summary_df['Outgoing'] = summary_df.apply(lambda x: x['amount'] if x['direction'] == "OUTGOING" else 0, axis=1)

    # 2. Group by Account and Asset (Adding Count and Total Volume)
    account_summary = summary_df.groupby(['other_account', 'asset']).agg(
        Outgoing=('Outgoing', 'sum'),
        Incoming=('Incoming', 'sum'),
        Total_Volume=('amount', 'sum'),
        Tx_Count=('amount', 'count')
    ).reset_index()

    # Calculate the Net Difference (Incoming minus Outgoing)
    account_summary['Net_Difference'] = account_summary['Incoming'] - account_summary['Outgoing']

    # 3. Add filters and sorting toggles for this table
    sum_f1, sum_f2 = st.columns([1, 2])
    with sum_f1:
        sum_asset_filter = st.multiselect(
            "Filter Summary Assets", 
            ["DMMK", "nUSDT"], 
            default=["DMMK", "nUSDT"],
            key="summary_asset_filter"
        )
    with sum_f2:
        # -> NEW: Dropdown (selectbox) for sorting logic
        sort_choice = st.selectbox(
            "Sort Table By:",
            ["Total Amount (Volume)", "Number of Transactions"]
        )
    
    # Apply local asset filter
    display_summary = account_summary[account_summary['asset'].isin(sum_asset_filter)]

    # Apply sorting based on the user's drop-down choice
    if sort_choice == "Number of Transactions":
        display_summary = display_summary.sort_values("Tx_Count", ascending=False)
    else:
        display_summary = display_summary.sort_values("Total_Volume", ascending=False)

    # 4. Display the table (with the CORRECTED NumberColumn syntax!)
    st.dataframe(
        display_summary,
        column_config={
            "other_account": "Account Name",
            "asset": "Asset",
            "Tx_Count": st.column_config.NumberColumn(
                "Tx Count",
                help="Total number of transactions with this account"
            ),
            "Total_Volume": st.column_config.NumberColumn(
                "Total Volume",
                help="Sum of all incoming and outgoing amounts combined",
                format="%,.2f"
            ),
            "Outgoing": st.column_config.NumberColumn(
                "Total Outgoing",
                help="Total sum of outgoing transactions for this account",
                format="%,.2f"
            ),
            "Incoming": st.column_config.NumberColumn(
                "Total Incoming",
                help="Total sum of incoming transactions for this account",
                format="%,.2f"
            ),
            "Net_Difference": st.column_config.NumberColumn(
                "Net Balance (In - Out)",
                help="Positive means they sent you more. Negative means you sent them more.",
                format="%,.2f"
            ),
        },
        use_container_width=True,
        hide_index=True
    )
########################


else:
    st.info("Enter a Stellar Account ID in the sidebar to begin.")











