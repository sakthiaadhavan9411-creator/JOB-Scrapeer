import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


def event(name: str, level: int = logging.INFO, **fields: Any) -> None:
    logging.getLogger("hiring_alerts").log(level, json.dumps({
        "time": datetime.now(timezone.utc).isoformat(), "level": logging.getLevelName(level),
        "event": name, **fields,
    }, ensure_ascii=True))


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout, force=True)
    # HTTP exceptions can contain credential-bearing URLs; never emit them or HTTP debug logs.
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    logging.getLogger("requests").setLevel(logging.CRITICAL)
