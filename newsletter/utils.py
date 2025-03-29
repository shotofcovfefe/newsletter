import hashlib
import math
import typing as ta

import pgeocode


nomi = pgeocode.Nominatim("GB")


def hash_prefix(input_str: str, length: int = 8) -> str:
    """
    Returns a deterministic short hash for the given input string.
    Uses SHA-256 and then truncates the hex digest to `length` characters.
    """
    full_hash = hashlib.sha256(input_str.encode('utf-8')).hexdigest()
    return full_hash[:length]


def is_valid_uk_postcode(postcode: str) -> bool:
    """
    Quick check if the postcode is valid enough for pgeocode to handle.
    We'll rely on pgeocode returning a result with a valid lat/lon.
    Alternatively, you can do a more thorough regex check if you want.
    """
    if not postcode:
        return False

    # Simple approach: get lat/lon from pgeocode
    location = nomi.query_postal_code(postcode)
    # If location.latitude is NaN (float) or None, it's not valid
    if location is None or math.isnan(location.latitude) or math.isnan(location.longitude):
        return False
    return True


def geocode_postcode_to_latlon(postcode: str) -> ta.Tuple[float, float]:
    """
    Returns (latitude, longitude) for the given postcode.
    Assumes postcode is valid. If anything fails, returns (None, None).
    """
    location = nomi.query_postal_code(postcode)
    if location is None:
        return None, None
    return float(location.latitude), float(location.longitude)


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