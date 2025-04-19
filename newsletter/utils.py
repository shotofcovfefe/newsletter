import hashlib
import math
import typing as ta
import os
import pandas as pd
from functools import lru_cache


@lru_cache
def _load_postcode_data():
    data_path = os.path.join(os.path.dirname(__file__), "../data/london_postcodes.csv")
    df = pd.read_csv(data_path, dtype=str)
    df["postcode_clean"] = df["postcode"].str.replace(" ", "").str.upper()
    df.set_index("postcode_clean", inplace=True)
    return df


def get_postcode_info(postcode: str):
    if isinstance(postcode, str):
        df = _load_postcode_data()
        clean = postcode.replace(" ", "").upper()
        if clean in df.index:
            row = df.loc[clean]
            return {
                "lat": row["lat"],
                "lon": row["lon"],
                "borough": row["borough"],
            }
    return {}


def hash_prefix(input_str: str, length: int = 8) -> str:
    """
    Returns a deterministic short hash for the given input string.
    Uses SHA-256 and then truncates the hex digest to `length` characters.
    """
    full_hash = hashlib.sha256(input_str.encode('utf-8')).hexdigest()
    return full_hash[:length]


def is_valid_london_postcode(postcode: str) -> bool:
    """
    Quick check if the postcode is valid enough for pgeocode to handle.
    We'll rely on pgeocode returning a result with a valid lat/lon.
    Alternatively, you can do a more thorough regex check if you want.
    """
    if not isinstance(postcode, str):
        return False

    # Simple approach: get lat/lon from pgeocode
    pc_dct = get_postcode_info(postcode)

    if pc_dct.get('lat') is None or pc_dct.get('lon') is None:
        return None

    try:
        lat = float(pc_dct.get('lat'))
        lon = float(pc_dct.get('lon'))
        if not math.isnan(lat) or not math.isnan(lon):
            return True
    except Exception:
        pass
    return True


def geocode_postcode_to_latlon(postcode: str) -> ta.Tuple[float, float]:
    """
    Returns (latitude, longitude) for the given postcode.
    Assumes postcode is valid. If anything fails, returns (None, None).
    """
    if not isinstance(postcode, str):
        return None, None

    # Simple approach: get lat/lon from pgeocode
    pc_dct = get_postcode_info(postcode)

    try:
        return float(pc_dct.get('lat')), float(pc_dct.get('lon'))
    except Exception:
        return None, None


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two points on the Earth (in km).
    lat/lon in decimal degrees.
    """
    # Earth radius in km
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2)**2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2)**2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c