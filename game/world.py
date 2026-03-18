"""
World data loader: reads and serves the JSON world files.
"""

from __future__ import annotations

import json
from pathlib import Path


class WorldData:
    """Loads and provides access to all world data files."""

    def __init__(self, world_dir: str | Path) -> None:
        self.world_dir = Path(world_dir)
        self.lore = self._load("lore.json")
        self.locations = self._load("locations.json").get("locations", {})
        self.npcs = self._load("npcs.json").get("npcs", {})
        self.items = self._load("items.json").get("items", {})

    def _load(self, filename: str) -> dict:
        path = self.world_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"World data file not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def get_location(self, location_id: str) -> dict | None:
        return self.locations.get(location_id)

    def get_npc(self, npc_id: str) -> dict | None:
        return self.npcs.get(npc_id)

    def get_item(self, item_id: str) -> dict | None:
        return self.items.get(item_id)

    def to_dict(self) -> dict:
        """Return world data as a single dict for injection into the system prompt."""
        return {
            "lore": self.lore,
            "locations": self.locations,
            "npcs": self.npcs,
            "items": self.items,
        }


def load_story(story_path: str | Path) -> dict:
    """Load a story JSON file."""
    path = Path(story_path)
    if not path.exists():
        raise FileNotFoundError(f"Story file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_prose_style(prose_path: str | Path) -> str:
    """Load the prose style guide markdown."""
    path = Path(prose_path)
    if not path.exists():
        return ""  # Optional — narrator works without it
    return path.read_text(encoding="utf-8")
