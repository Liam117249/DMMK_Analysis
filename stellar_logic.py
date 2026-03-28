import pandas as pd
from datetime import datetime, timedelta, timezone
from stellar_sdk import Server
from decimal import Decimal, getcontext
import requests

# Fixed-point precision for blockchain math
getcontext().prec = 28 

def get_federation_server():
    """Fetches the federation URL dynamically from nugpay.app."""
    try:
        url = "https://nugpay.app/.well-known/stellar.toml"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            for line in response.text.splitlines():
                if "FEDERATION_SERVER" in line:
                    return line.split("=")[1].strip(' "\'')
    except Exception as e:
        print(f"TOML fetch error: {e}")
    return None

def resolve_username_to_id(username):
    """Translates 'name' or 'name*domain' into a G-Address."""
    if not username: return None
    
    full_address = username if "*" in username else f"{username}*nugpay.app"
    domain = full_address.split("*")[1]
    
    try:
        toml_url = f"https://{domain}/.well-known/stellar.toml"
        res = requests.get(toml_url, timeout=5)
        fed_url = None
        if res.status_code == 200:
            for line in res.text.splitlines():
                if "FEDERATION_SERVER" in line:
                    fed_url = line.split("=")[1].strip(' "\'')
                    break
        
        if fed_url:
            query = f"{fed_url}?q={full_address}&type=name"
            api_res = requests.get(query, timeout=5)
            if api_res.status_code == 200:
                return api_res.json().get("account_id")
    except Exception as e:
        print(f"Forward lookup error: {e}")
    return None

def resolve_id_to_name(account_id):
    """Translates a G-Address back into a username."""
    fed_url = get_federation_server()
    if not fed_url: return None
    try:
        url = f"{fed_url}?q={account_id}&type=id"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            addr = res.json().get("stellar_address", "")
            return addr.split("*")[0] if "*" in addr else None
    except:
        pass
    return None

def get_account_name(account_id, cache_dict, federation_url):
    """Checks cache or Federation API for transaction history names."""
    if not account_id or len(account_id) < 16: return account_id
    if account_id in cache_dict: return cache_dict[account_id]

    if federation_url:
        url = f"{federation_url}?q={account_id}&type=id"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                stellar_address = response.json().get("stellar_address", "")
                if stellar_address and "*" in stellar_address:
                    username = stellar_address.split("*")[0]
                    cache_dict[account_id] = username
                    return username
        except:
            pass

    fallback = f"{account_id[:8]}*******{account_id[-8:]}"
    cache_dict[account_id] = fallback
    return fallback

def analyze_stellar_account(account_id, months=1):
    server = Server("https://horizon.stellar.org")
    now_utc = datetime.now(timezone.utc)
    start_date = now_utc - timedelta(days=30 * months)
    
    processed_data = []
    name_cache = {} 
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
                if asset_code not in ["DMMK", "nUSDT"]: continue

                raw_val = Decimal(record.get('amount', '0'))
                final_val = raw_val * Decimal('1000') if asset_code == "DMMK" else raw_val
                is_sender = record.get('from') == account_id
                raw_other_account = record.get('to') if is_sender else record.get('from')
                
                display_name = get_account_name(raw_other_account, name_cache, federation_url)
                
                processed_data.append({
                    "timestamp": dt,
                    "date": dt.date(),
                    "month_name": dt.strftime("%B"),
                    "week_num": f"Week {dt.isocalendar()[1]}",
                    "direction": "OUTGOING" if is_sender else "INCOMING",
                    "other_account": display_name,
                    "other_account_id": raw_other_account, # Added to support row-click navigation
                    "amount": float(final_val),
                    "asset": asset_code
                })
            records = payments_call.next()
            if not records['_embedded']['records']: break
        return processed_data
    except Exception as e:
        print(f"Error: {e}")
        return None
