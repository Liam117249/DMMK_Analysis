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
    
    # Default to nugpay.app if no domain provided
    full_address = username if "*" in username else f"{username}*nugpay.app"
    domain = full_address.split("*")[1]
    
    try:
        # Get federation server for the specific domain
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
    if account_id in cache_dict:
