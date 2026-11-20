"""HTTP and description options for board fetches.

Search CLI uses DEFAULT. Radar passes RADAR (longer timeout, full JD text with line breaks).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FetchConfig:
    timeout: int = 15
    description_max: Optional[int] = 1500
    keep_lines: bool = False


DEFAULT = FetchConfig()
RADAR = FetchConfig(timeout=45, description_max=None, keep_lines=True)
