from dataclasses import dataclass
from enum import Enum

class APIType(Enum):
    SPECIAL = "special"
    GMAIL = "gmail"
    GOOGLE_CALENDAR = "google_calendar"


@dataclass
class APILinearMemory:
    api_type: APIType
    call: str
    received: str