import hashlib
import math
import logging
import typing as ta
import os
import pandas as pd
import time
from functools import lru_cache, wraps
import re

from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from curl_cffi import requests as curl_requests

from newsletter.constants import TRACKERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@lru_cache
def _load_postcode_data():
    data_path = os.path.join(os.path.dirname(__file__), "data/london_postcodes.csv")
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


def resolve_redirect_impersonate(url: str, timeout: float = 15.0) -> str:
    if not url or not (url.startswith('http://') or url.startswith('https://')):
        logger.warning(f"Invalid URL scheme: '{url}'.")
        return url
    try:
        # Impersonate a recent Chrome version. Others like 'chrome110', 'firefox117' are possible.
        # Use allow_redirects=True (default)
        response = curl_requests.get(url, impersonate="chrome116", timeout=timeout, allow_redirects=True)
        response.raise_for_status()  # Raise exception for 4xx/5xx errors

        # Debugging: Check history (response.history is not directly available like in requests)
        # You might need to check response.url against the original url
        logger.info(f"curl_cffi successful for {url}. Final URL: {response.url}, Status: {response.status_code}")

        return response.url
    except Exception as e:
        logger.warning(f"curl_cffi failed for {url}: {e}")
        return url


def resolve_redirect_from_known_sources(url: str, trackers: ta.List[str] = TRACKERS, timeout: float = 10.0) -> str:
    """
    Resolves a redirect-tracking URL if its domain is in the provided trackers list.
    """
    if url and any(tracker_domain in url for tracker_domain in trackers):
        return resolve_redirect_impersonate(url, timeout=timeout)
    return url


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

    # Add additional known senders and trimming logic here
    # elif sender == "xyz":
    #     ...

    return body  # fallback to original content


def strip_tracking_params(url: str, allowed_params=None) -> str:
    """
    Removes common tracking query parameters like utm_* from a URL.
    """
    if allowed_params is None:
        allowed_params = set()  # e.g., allowlist like {"ref"} if needed

    parsed = urlparse(url)
    clean_query = {
        k: v for k, v in parse_qs(parsed.query).items()
        if not k.lower().startswith("utm_") and k not in allowed_params
    }
    new_query = urlencode(clean_query, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def resolve_links_in_body(body: str) -> str:
    """
    Finds and resolves Beehiiv-style or standalone https URLs in text,
    removing tracking parameters if present.
    """
    pattern = re.compile(r"<(https://[^>\s]+)>|(?<!href=\")\b(https://[^\s<>\"']+)\b")
    found_links = set(match.group(1) or match.group(2) for match in pattern.finditer(body))

    replacements = {}
    for url in found_links:
        try:
            resolved = resolve_redirect_from_known_sources(url)
            stripped = strip_tracking_params(resolved)
            replacements[url] = stripped
        except Exception as e:
            print(f"[warn] Could not resolve: {url} — {e}")
            replacements[url] = url

    def replacer(match):
        original = match.group(1) or match.group(2)
        resolved = replacements.get(original, original)
        return f"<{resolved}>" if match.group(1) else resolved

    return pattern.sub(replacer, body)


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
