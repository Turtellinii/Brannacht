"""
Game state: tracks everything about the current playthrough.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class GameState:
    current_location: str
    inventory: list[str] = field(default_factory=list)
    discovered_locations: set[str] = field(default_factory=set)
    flags: dict[str, Any] = field(default_factory=dict)
    turn_count: int = 0
    session_id: str = field(
        default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    def __post_init__(self) -> None:
        # Ensure starting location is always discovered
        self.discovered_locations.add(self.current_location)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "current_location": self.current_location,
            "inventory": list(self.inventory),
            "discovered_locations": list(self.discovered_locations),
            "flags": self.flags,
            "turn_count": self.turn_count,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GameState:
        state = cls(
            current_location=data["current_location"],
            inventory=list(data.get("inventory", [])),
            flags=dict(data.get("flags", {})),
            turn_count=data.get("turn_count", 0),
            session_id=data.get("session_id", ""),
        )
        state.discovered_locations = set(data.get("discovered_locations", []))
        state.discovered_locations.add(state.current_location)
        return state

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path | str) -> GameState:
        return cls.from_dict(json.loads(Path(path).read_text()))

    # ------------------------------------------------------------------
    # State mutation — called by the engine when the narrator uses tools
    # ------------------------------------------------------------------

    def apply_change(self, change: dict) -> None:
        """Apply a state change emitted by the narrator's tool calls."""
        kind = change["type"]

        if kind == "location":
            self.current_location = change["location_id"]
            self.discovered_locations.add(change["location_id"])

        elif kind == "inventory":
            item = change["item_id"]
            if change["action"] == "add":
                if item not in self.inventory:
                    self.inventory.append(item)
            elif change["action"] == "remove":
                self.inventory = [i for i in self.inventory if i != item]

        elif kind == "flag":
            self.flags[change["flag"]] = change["value"]

        elif kind == "reveal":
            self.discovered_locations.add(change["location_id"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def has_item(self, item_id: str) -> bool:
        return item_id in self.inventory

    def get_flag(self, flag: str, default: Any = None) -> Any:
        return self.flags.get(flag, default)

    def set_flag(self, flag: str, value: Any) -> None:
        self.flags[flag] = value
