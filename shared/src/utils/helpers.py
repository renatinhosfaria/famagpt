"""
Utility helpers and common functions.
"""
import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import UUID


def generate_correlation_id() -> str:
    """Generate a unique correlation ID."""
    return str(uuid.uuid4())


def generate_hash(data: str) -> str:
    """Generate SHA-256 hash of data."""
    return hashlib.sha256(data.encode()).hexdigest()


def generate_short_id(length: int = 8) -> str:
    """Generate a short random ID."""
    return str(uuid.uuid4()).replace('-', '')[:length]


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def to_dict(obj: Any, exclude_none: bool = True) -> Dict[str, Any]:
    """Convert object to dictionary."""
    if hasattr(obj, 'dict'):
        # Pydantic model
        return obj.dict(exclude_none=exclude_none)
    elif hasattr(obj, '__dict__'):
        # Regular object
        result = obj.__dict__.copy()
        if exclude_none:
            result = {k: v for k, v in result.items() if v is not None}
        return result
    else:
        return {}


def serialize_for_json(obj: Any) -> Any:
    """Serialize object for JSON encoding."""
    if isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, 'dict'):
        return obj.dict()
    elif hasattr(obj, '__dict__'):
        return obj.__dict__
    else:
        return obj


def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """Safely parse JSON string."""
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default


def safe_json_dumps(obj: Any, default: Any = serialize_for_json) -> str:
    """Safely serialize object to JSON."""
    try:
        return json.dumps(obj, default=default, ensure_ascii=False)
    except (TypeError, ValueError):
        return "{}"


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split list into chunks of specified size."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def flatten_dict(d: Dict[str, Any], parent_key: str = '', sep: str = '.') -> Dict[str, Any]:
    """Flatten nested dictionary."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def deep_merge_dict(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries."""
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dict(result[key], value)
        else:
            result[key] = value
    
    return result


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """Truncate text to maximum length."""
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def extract_numbers(text: str) -> List[float]:
    """Extract all numbers from text."""
    import re
    pattern = r'-?\d+\.?\d*'
    matches = re.findall(pattern, text)
    return [float(match) for match in matches if match]


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    import re
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove control characters
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    # Strip whitespace
    text = text.strip()
    
    return text


def format_phone_number(phone: str, country_code: str = "+55") -> str:
    """Format phone number with country code."""
    # Remove non-numeric characters
    cleaned = ''.join(filter(str.isdigit, phone))
    
    # Add country code if not present
    if not cleaned.startswith('55') and country_code == "+55":
        cleaned = '55' + cleaned
    
    return f"+{cleaned}"


def format_currency(amount: float, currency: str = "BRL") -> str:
    """Format currency amount."""
    if currency == "BRL":
        return f"R$ {amount:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    else:
        return f"{currency} {amount:,.2f}"


def format_area(area_sqm: float) -> str:
    """Format area in square meters."""
    return f"{area_sqm:,.0f} m²".replace(',', '.')


def parse_area_from_text(text: str) -> Optional[float]:
    """Parse area from text description."""
    import re
    
    # Look for patterns like "100m²", "100 m2", "100 metros"
    patterns = [
        r'(\d+(?:\.\d+)?)\s*m[²2]',
        r'(\d+(?:\.\d+)?)\s*metros?',
        r'(\d+(?:\.\d+)?)\s*metro',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            return float(match.group(1))
    
    return None


def parse_price_from_text(text: str) -> Optional[float]:
    """Parse price from text description."""
    import re
    
    # Look for patterns like "R$ 100.000", "100000", "100k"
    patterns = [
        r'R\$\s*(\d+(?:\.\d+)*(?:,\d+)?)',
        r'(\d+)\s*mil',
        r'(\d+)k',
        r'(\d+(?:\.\d+)*(?:,\d+)?)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            value_str = match.group(1).replace('.', '').replace(',', '.')
            value = float(value_str)
            
            # Handle "mil" (thousand) and "k" multipliers
            if 'mil' in pattern or 'k' in pattern:
                value *= 1000
            
            return value
    
    return None


async def retry_async(
    func,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """Retry async function with exponential backoff."""
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt == max_retries:
                break
            
            # Wait with exponential backoff
            wait_time = delay * (backoff_factor ** attempt)
            await asyncio.sleep(wait_time)
    
    raise last_exception


def bytes_to_human_readable(bytes_size: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"
