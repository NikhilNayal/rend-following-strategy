
from datetime import datetime, timedelta
import re

def parse_tradingsymbol(symbol: str):
    """
    Parses symbols like BANKNIFTY26JAN54000CE
    Returns dict or None
    """
    # Regex: Name, YY, MMM, Strike, Type
    # e.g. BANKNIFTY 26 JAN 54000 CE
    pattern = r"^([A-Z]+)(\d{2})([A-Z]{3})(\d+)([CP]E)$"
    match = re.match(pattern, symbol)
    if match:
        return {
            "name": match.group(1),
            "year": match.group(2), # "26"
            "month": match.group(3), # "JAN"
            "strike": float(match.group(4)),
            "type": match.group(5), # "CE"
            "expiry_str": f"{match.group(2)}{match.group(3)}" # "26JAN"
        }
    return None

def parse_expiry_sort_key(expiry_str: str) -> datetime:
    """
    Converts '26JAN' (YYMMM) to datetime for sorting.
    """
    try:
        # datetime.strptime("26JAN", "%y%b") -> 2026-01-01
        return datetime.strptime(expiry_str, "%y%b")
    except ValueError:
        return datetime.max


def get_closest_match(target_premium: float, candidates: list) -> dict:
    """
    Find the item in candidates (list of dicts with 'last_price') 
    whose price is closest to target_premium.
    """
    if not candidates:
        return None
    return min(candidates, key=lambda x: abs(x['last_price'] - target_premium))
