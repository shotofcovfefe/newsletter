import hashlib
import math
import logging
import typing as ta
import os
import pandas as pd
import time
from functools import lru_cache, wraps
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@lru_cache
def _load_postcode_data():
    data_path = os.path.join(os.path.dirname(__file__), "../data/london_postcodes.csv")
    df = pd.read_csv(data_path, dtype=str)
    df["postcode_clean"] = df["postcode"].str.replace(" ", "").str.upper()
    df.set_index("postcode_clean", inplace=True)
    return df


def round_sig(x, sig=1):
    if x == 0:
        return 0
    return round(x, -int(math.floor(math.log10(abs(x)))) + (sig - 1))


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
                "neighbourhood": row["neighbourhood"],
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
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculates the initial bearing between two points (in degrees).
    Bearing is measured clockwise from North (0°).
    """
    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Difference in longitude
    dlon_rad = lon2_rad - lon1_rad

    # Calculate components for atan2
    y = math.sin(dlon_rad) * math.cos(lat2_rad)
    x = math.cos(lat1_rad) * math.sin(lat2_rad) - \
        math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad)

    # Calculate bearing in radians
    initial_bearing_rad = math.atan2(y, x)

    # Convert bearing from radians to degrees
    initial_bearing_deg = math.degrees(initial_bearing_rad)

    # Normalize bearing to 0-360 range
    compass_bearing = (initial_bearing_deg + 360) % 360

    return compass_bearing


def bearing_to_arrow(angle_degrees: float) -> str:
    """
    Converts a bearing angle (0-360 degrees) to an ASCII arrow.
    """
    if angle_degrees is None:
        return ""  # Return empty if angle is invalid

    # Define the arrows (N, NE, E, SE, S, SW, W, NW)
    arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]

    # Each segment is 360 / 8 = 45 degrees wide.
    # We shift by half a segment (22.5 degrees) to center the segments on the directions.
    segment_index = int(((angle_degrees + 22.5) % 360) / 45.0)

    try:
        return arrows[segment_index]
    except IndexError:
        # This should ideally not happen if angle_degrees is within 0-360
        logger.warning(f"Could not map bearing {angle_degrees} to arrow index {segment_index}.")
        return "·"  # Fallback character


def trim_aggregator_email_bodies_from_known_sources(
        body: str,
) -> str:
    """
    Trims aggregator-style email content to isolate just the event section.
    Custom logic is applied for known senders like The London Scoop.

    Args:
        body (str): The full text content of the email.
        sender (str): The normalized name or identifier for the sender.

    Returns:
        str: Trimmed body content focused on events, or the original if no rules match.
    """
    if "london scoop" in body.lower():
        split_marker = " *EVENTS SCOOP* *.*"
        if split_marker in body:
            body = body.split(split_marker, 1)[-1].strip()

        split_marker = "*Let me know what you think!"
        if split_marker in body:
            body = body.split(split_marker, 1)[0].strip()

    if 'cheapskate' in body.lower():
        split_marker = "_**And for dessert...**_"
        if split_marker in body:
            body = body.split(split_marker, 1)[0].strip()

    return body


def timed(label="Function"):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                end = time.perf_counter()
                duration = end - start
                logging.info(f"{label} took {duration:.2f} seconds")

        return wrapper

    return decorator


def replace_json_gates(s: str) -> str:
    return s.replace('```json', '').replace('```', '').replace('\n', '')
