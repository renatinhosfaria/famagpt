"""
Validation utilities.
"""
import re
from typing import Any, Dict, List, Optional
from uuid import UUID


def validate_phone_number(phone: str) -> bool:
    """Validate phone number format."""
    # Remove non-numeric characters
    cleaned = ''.join(filter(str.isdigit, phone))
    
    # Check if it has at least 10 digits (minimum for mobile)
    if len(cleaned) < 10:
        return False
    
    # Check if it has at most 15 digits (international limit)
    if len(cleaned) > 15:
        return False
    
    return True


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_url(url: str) -> bool:
    """Validate URL format."""
    pattern = r'^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$'
    return re.match(pattern, url) is not None


def validate_uuid(uuid_string: str) -> bool:
    """Validate UUID format."""
    try:
        UUID(uuid_string)
        return True
    except ValueError:
        return False


def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> List[str]:
    """Validate required fields in data dictionary."""
    missing_fields = []
    
    for field in required_fields:
        if field not in data or data[field] is None or data[field] == '':
            missing_fields.append(field)
    
    return missing_fields


def validate_file_extension(filename: str, allowed_extensions: List[str]) -> bool:
    """Validate file extension."""
    if '.' not in filename:
        return False
    
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in [ext.lower() for ext in allowed_extensions]


def validate_file_size(file_size_bytes: int, max_size_mb: int) -> bool:
    """Validate file size."""
    max_size_bytes = max_size_mb * 1024 * 1024
    return file_size_bytes <= max_size_bytes


def sanitize_phone_number(phone: str) -> str:
    """Sanitize phone number by removing non-numeric characters."""
    return ''.join(filter(str.isdigit, phone))


def sanitize_string(text: str, max_length: Optional[int] = None) -> str:
    """Sanitize string by removing dangerous characters."""
    # Remove control characters and normalize whitespace
    sanitized = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    
    # Truncate if max_length specified
    if max_length and len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    
    return sanitized


def validate_coordinates(latitude: float, longitude: float) -> bool:
    """Validate latitude and longitude coordinates."""
    return -90 <= latitude <= 90 and -180 <= longitude <= 180


def validate_price(price: float) -> bool:
    """Validate price value."""
    return price > 0


def validate_area(area_sqm: float) -> bool:
    """Validate area in square meters."""
    return area_sqm > 0


def validate_bedrooms(bedrooms: int) -> bool:
    """Validate number of bedrooms."""
    return 0 <= bedrooms <= 20


def validate_bathrooms(bathrooms: int) -> bool:
    """Validate number of bathrooms."""
    return 0 <= bathrooms <= 20
