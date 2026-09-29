"""Safe, serializable domain errors for HTTP and native RPC."""
from typing import Any

class AppError(Exception):
    def __init__(self, message: str, code: str = "validation", details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details

def require(condition: Any, message: str, code: str = "validation", details: Any = None) -> None:
    if not condition:
        raise AppError(message, code, details)
