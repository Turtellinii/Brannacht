"""
Game engine: orchestrates state, narrator, and world data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from game.narrator import Narrator
from game.state import GameState
from game.world import WorldData, load_prose_style, load_story


class GameEngine:
    """
    Ties together world data, story data, game state, and the AI narrator.

    Usage:
        engine = GameEngine(story_path="data/stories/the_shattered_crown.json",
                            world_dir="data/world")
        engine.new_game()
        for event_type, data in engine.opening():
            ...
        for event_type, data in engine.process_turn("look around"):
            ...
    """

    def __init__(
        self,
        story_path: str | Path,
        world_dir: str | Path = "data/world",
        prose_path: str | Path = "data/prose_style.md",
        save_dir: str | Path = "saves",
    ) -> None:
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)

        # Load data
        self.world = WorldData(world_dir)
        self.story = load_story(story_path)
        self.prose_style = load_prose_style(prose_path)

        # Build narrator (expensive: loads world data into system prompt)
        self.narrator = Narrator(
            world_data=self.world.to_dict(),
            prose_style=self.prose_style,
            story_data=self.story,
        )

        self.state: GameState | None = None
        self.game_over: bool = False
        self.game_over_data: dict = {}

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def new_game(self) -> None:
        """Start a fresh game from story defaults."""
        starting_location = self.story.get("starting_location", "entrance")
        starting_inventory = list(self.story.get("starting_inventory", []))
        starting_flags = dict(self.story.get("starting_flags", {}))

        self.state = GameState(
            current_location=starting_location,
            inventory=starting_inventory,
            flags=starting_flags,
        )
        self.game_over = False
        self.game_over_data = {}

    def save_game(self, name: str | None = None) -> Path:
        """Save current state. Returns the path to the save file."""
        if self.state is None:
            raise RuntimeError("No active game to save.")
        save_name = name or f"save_{self.state.session_id}"
        path = self.save_dir / f"{save_name}.json"
        self.state.save(path)
        return path

    def load_game(self, save_path: str | Path) -> None:
        """Load a saved game state."""
        self.state = GameState.load(save_path)
        self.game_over = False
        self.game_over_data = {}

    def list_saves(self) -> list[Path]:
        """Return available save files."""
        return sorted(self.save_dir.glob("*.json"))

    # ------------------------------------------------------------------
    # Gameplay
    # ------------------------------------------------------------------

    def opening(self) -> Iterator[tuple[str, Any]]:
        """Stream the opening scene narration. Call once after new_game()."""
        if self.state is None:
            raise RuntimeError("Call new_game() or load_game() first.")
        yield from self.narrator.opening(self.state)

    def process_turn(self, player_input: str) -> Iterator[tuple[str, Any]]:
        """
        Process one player turn. Streams (event_type, data) pairs.

        event_type values:
          "text"         — narration chunk (display immediately)
          "state_change" — state was updated (informational)
          "game_over"    — game has ended
        """
        if self.state is None:
            raise RuntimeError("Call new_game() or load_game() first.")
        if self.game_over:
            yield ("text", "The story has ended. Start a new game to play again.\n")
            return

        self.state.turn_count += 1

        for event_type, data in self.narrator.narrate(player_input, self.state):
            if event_type == "state_change":
                self.state.apply_change(data)
            elif event_type == "game_over":
                self.game_over = True
                self.game_over_data = data
            yield (event_type, data)

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    @property
    def current_location_name(self) -> str:
        if self.state is None:
            return "unknown"
        loc = self.world.get_location(self.state.current_location)
        if loc:
            return loc.get("name", self.state.current_location)
        return self.state.current_location

    @property
    def story_title(self) -> str:
        return self.story.get("title", "Untitled Story")
