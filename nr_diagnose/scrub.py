"""PII scrubbing - replaces sensitive values with <REDACTED>."""

import re

# Key-value patterns (license_key: VALUE, api_key: VALUE, etc.)
_KV_PATTERN = re.compile(
    r'(?i)(license_key|api_key|apikey|api-key|secret|token|password|passwd|pwd)\s*[:=]\s*"?([^\s"]+)"?'
)

# New Relic specific keys (NRAK-, NRIQ-, etc.)
_NR_KEY_PATTERN = re.compile(r'NR[A-Z]{2}-[A-Za-z0-9]{20,}')

# Generic 40-char hex strings (common API key format)
_HEX_PATTERN = re.compile(r'\b[0-9a-fA-F]{40}\b')


def scrub(text: str) -> str:
    """Replace sensitive values in text with <REDACTED>."""
    result = _KV_PATTERN.sub(r'\1: <REDACTED>', text)
    result = _NR_KEY_PATTERN.sub('<REDACTED>', result)
    result = _HEX_PATTERN.sub('<REDACTED>', result)
    return result
