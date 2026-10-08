import json
import time
from pathlib import Path


class TrajectoryLogger:
    """Full record of every thought, action and observation. Saved after each event for crash safety."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events: list[dict] = []
        self.meta: dict = {}

    def log(self, kind: str, **data):
        self.events.append({"t": round(time.time(), 2), "kind": kind, **data})
        self.save()

    def save(self):
        self.path.write_text(json.dumps({"meta": self.meta, "events": self.events},
                                        indent=2, default=str))