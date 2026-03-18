import pandas as pd
from datetime import datetime, timedelta, timezone
from stellar_sdk import Server
from decimal import Decimal, getcontext
import requests

# Fixed-point precision for blockchain math
getcontext().prec = 28 

def get_federation_server():
    """
    Stellar SEP-0002 Standard: Fetches the actual federation URL 
    dynamically from the domain's stellar.toml file.
    """
# --- INSERT THE NEW CODE HERE ---
def resolve_id_to_name(account_id):
    """
    Reverse Lookup: Takes a G-Address and returns the name (e.g., 'sithu').
    """
    # Use your existing federation logic
    fed_url = get_federation_server()
    if not fed_url:
        return None
        
    try:
        url = f"{fed_url}?q={account_id}&type=id"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            stellar_address = data.get("stellar_address", "")
            if "*" in stellar_address:
                return stellar_address.split("*")[0]
    except:
        pass
    return None
# --------------------------------

def get_account_name(account_id, cache_dict, federation_url):
    """Checks cache. If not found, calls Federation API."""
    if not account_id or len(account_id) < 16:
        return account_id

    # 1. Instant cache return
    if account_id in cache_dict:
        return cache_dict[account_id]

    # 2. Try API if we successfully found the federation server URL
    if federation_url:
        # Standard SEP-0002 Reverse Lookup
        url = f"{federation_url}?q={account_id}&type=id"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                stellar_address = data.get("stellar_address", "")
                
                # Extract the name before the *
                if stellar_address and "*" in stellar_address:
                    username = stellar_address.split("*")[0]
                    cache_dict[account_id] = username
                    return username
        except requests.exceptions.RequestException as e:
            print(f"API Error for {account_id}: {e}")

    # 3. Fallback to your original mask format if API fails or account has no name
    fallback_name = f"{account_id[:8]}*******{account_id[-8:]}"
    cache_dict[account_id] = fallback_name
    return fallback_name

def analyze_stellar_account(account_id, months=1):
    server = Server("https://horizon.stellar.org")
    now_utc = datetime.now(timezone.utc)
    start_date = now_utc - timedelta(days=30 * months)
    
    processed_data = []
    name_cache = {} 
    
    # Fetch the correct API URL ONCE before the loop starts!
    federation_url = get_federation_server()
    
    try:
        payments_call = server.payments().for_account(account_id).order(desc=True).limit(200)
        records = payments_call.call()

        while records['_embedded']['records']:
            for record in records['_embedded']['records']:
                dt = datetime.strptime(record['created_at'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                
                if dt < start_date:
                    records['_embedded']['records'] = []
                    break
                
                asset_code = record.get('asset_code')
                if asset_code not in ["DMMK", "nUSDT"]:
                    continue

                raw_val = Decimal(record.get('amount', '0'))
                final_val = raw_val * Decimal('1000') if asset_code == "DMMK" else raw_val
                is_sender = record.get('from') == account_id
                
                raw_other_account = record.get('to') if is_sender else record.get('from')
                
                # Resolve the name
                display_name = get_account_name(raw_other_account, name_cache, federation_url)
                
                processed_data.append({
                    "timestamp": dt,
                    "date": dt.date(),
                    "month_name": dt.strftime("%B"),
                    "week_num": f"Week {dt.isocalendar()[1]}",
                    "direction": "OUTGOING" if is_sender else "INCOMING",
                    "other_account": display_name,
                    "amount": float(final_val),
                    "asset": asset_code
                })
            
            records = payments_call.next()
            if not records['_embedded']['records']: break

        return processed_data
    except Exception as e:
        print(f"Error: {e}")
        return None
