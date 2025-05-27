import functools
import hashlib
import json
import logging
from pathlib import Path
import inspect

logger = logging.getLogger(__name__)

CACHE_BASE_DIR = Path(".cache/app_cache") # General base cache directory

def disk_cache(cache_subdirectory_name: str):
    """
    General-purpose decorator to cache function results to disk.

    Args:
        cache_subdirectory_name: Name of the subdirectory within CACHE_BASE_DIR
                                 to store cache files for the decorated function.
    """
    def decorator(func):
        cache_dir = CACHE_BASE_DIR / cache_subdirectory_name
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            # This might happen in rare concurrent scenarios or due to permissions
            logger.error(f"Error creating cache directory {cache_dir}: {e}. Caching may fail.")

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create a stable cache key from args and kwargs
            # Bind arguments to their names for stable key generation
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            
            # Create a dictionary of arguments, ensuring consistent order for hashing
            # by sorting keys.
            key_dict = dict(sorted(bound_args.arguments.items()))

            try:
                # Serialize the sorted dictionary of arguments to a JSON string.
                # Using default=str to handle simple non-serializable types like datetime, Path etc.
                # For more complex objects, a custom default handler might be needed.
                cache_key_input = json.dumps(key_dict, sort_keys=True, default=str)
            except TypeError as e:
                logger.error(
                    f"Cache key generation failed for {func.__name__} due to non-serializable arguments: {e}. "
                    f"Caching will be skipped for this call."
                )
                return func(*args, **kwargs) # Execute the function without caching

            cache_key = hashlib.md5(cache_key_input.encode('utf-8')).hexdigest()
            cache_file = cache_dir / f"{cache_key}.json"

            # Try to read from cache
            if cache_file.exists():
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                    logger.info(f"💾 Cache HIT for {func.__name__} in '{cache_subdirectory_name}'. Key: {cache_key}")
                    return cached_data
                except (IOError, json.JSONDecodeError, TypeError) as e: # Added TypeError for safety
                    logger.warning(
                        f"⚠️ Error reading cache file {cache_file} for {func.__name__}: {e}. "
                        f"Cache will be re-populated."
                    )
            else:
                logger.info(f"💨 Cache MISS for {func.__name__} in '{cache_subdirectory_name}'. Key: {cache_key}")

            # Execute the function if cache miss or error
            result = func(*args, **kwargs)

            # Write to cache
            # Only attempt to cache if the result is not None.
            # You might want to change this if caching None is desirable.
            if result is not None:
                try:
                    with open(cache_file, 'w', encoding='utf-8') as f:
                        json.dump(result, f, indent=2) # Using indent for readability of cache files
                    logger.info(f"💾 Cache WRITE for {func.__name__} in '{cache_subdirectory_name}'. Key: {cache_key}")
                except (IOError, TypeError) as e: # TypeError if result is not JSON serializable
                    logger.warning(
                        f"⚠️ Error writing cache file {cache_file} for {func.__name__}: {e}. "
                        f"Result not cached."
                    )
            return result
        return wrapper
    return decorator 