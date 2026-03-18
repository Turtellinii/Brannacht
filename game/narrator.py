"""
AI Narrator — powered by Claude.

Streams narration to the caller as (event_type, data) tuples:
  ("text", str)            — a chunk of narration to display
  ("state_change", dict)   — a state change to apply
  ("game_over", dict)      — outcome data; game should end
  ("error", str)           — something went wrong
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Generator, Iterator

import anthropic

if TYPE_CHECKING:
    from game.state import GameState

# ---------------------------------------------------------------------------
# Tool definitions — the narrator calls these to update game state
# ---------------------------------------------------------------------------

NARRATOR_TOOLS: list[dict] = [
    {
        "name": "update_location",
        "description": (
            "Move the player to a new location after they successfully travel there. "
            "Call this after narrating the movement, not before."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location_id": {
                    "type": "string",
                    "description": "The ID of the destination location (from world data).",
                }
            },
            "required": ["location_id"],
        },
    },
    {
        "name": "update_inventory",
        "description": (
            "Add or remove an item from the player's inventory. "
            "Call when the player picks up, drops, uses, or loses an item."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove"],
                    "description": "Whether to add or remove the item.",
                },
                "item_id": {
                    "type": "string",
                    "description": "The item ID (from world data).",
                },
            },
            "required": ["action", "item_id"],
        },
    },
    {
        "name": "set_story_flag",
        "description": (
            "Set a story flag to track quest progress, NPC relationships, "
            "discovered secrets, and world events. Use descriptive snake_case names "
            "like 'met_bram', 'read_sealed_letter', 'faction_covenant_ally'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "flag": {
                    "type": "string",
                    "description": "The flag name.",
                },
                "value": {
                    "description": "The flag value (boolean, string, number, or null).",
                },
            },
            "required": ["flag", "value"],
        },
    },
    {
        "name": "reveal_location",
        "description": (
            "Mark a location as discovered and accessible. "
            "Call when the player learns the name and existence of a new area."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location_id": {
                    "type": "string",
                    "description": "The location ID to reveal.",
                }
            },
            "required": ["location_id"],
        },
    },
    {
        "name": "end_game",
        "description": (
            "Conclude the current game session when the story reaches an ending, "
            "the player dies, or a chapter completes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome": {
                    "type": "string",
                    "enum": ["victory", "defeat", "chapter_end"],
                    "description": "The nature of the ending.",
                },
                "summary": {
                    "type": "string",
                    "description": "A one-paragraph summary of what happened.",
                },
            },
            "required": ["outcome", "summary"],
        },
    },
]


# ---------------------------------------------------------------------------
# Narrator class
# ---------------------------------------------------------------------------


class Narrator:
    """
    Wraps the Claude API to provide immersive text-adventure narration.

    Prompt caching is applied to the large world data block so repeated turns
    don't re-encode the same ~50 KB of world context.
    """

    def __init__(
        self,
        world_data: dict,
        prose_style: str,
        story_data: dict,
        max_history_turns: int = 40,
    ) -> None:
        self.client = anthropic.Anthropic()
        self.messages: list[dict] = []
        self.max_history_turns = max_history_turns
        self.system_blocks = self._build_system(world_data, prose_style, story_data)

    # ------------------------------------------------------------------
    # System prompt construction
    # ------------------------------------------------------------------

    def _build_system(
        self, world_data: dict, prose_style: str, story_data: dict
    ) -> list[dict]:
        """
        Build the system prompt as two blocks:
        1. A short preamble (not cached — cheap to re-encode)
        2. The large world + style block (cached — saves ~90% on repeated turns)
        """
        preamble = (
            "You are the narrator of an immersive text adventure game set in the world below.\n\n"
            "YOUR ROLE:\n"
            "- NARRATE: Describe what happens in response to player actions with vivid, "
            "atmospheric prose true to the style guide.\n"
            "- ADJUDICATE: Determine realistic outcomes. Not every action succeeds. "
            "NPCs have their own agendas.\n"
            "- MAINTAIN CONSISTENCY: Stay true to established facts, NPC personalities, "
            "and the player's history.\n"
            "- UPDATE STATE: Call the provided tools when the game state changes — "
            "always AFTER narrating the outcome, not before.\n\n"
            "RULES:\n"
            "- Always respond as the narrator. Never break the fourth wall.\n"
            "- Call state-update tools after narrating, not before or instead of narrating.\n"
            "- Multiple tool calls are fine in one response.\n"
            "- When a player action is impossible, narrate why naturally and leave them agency.\n"
            "- Keep narration focused: 100–300 words is ideal unless the scene demands more.\n"
            "- NPC dialogue should reveal character, not just deliver information.\n"
        )

        world_section = (
            "PROSE STYLE GUIDE\n"
            "=================\n"
            f"{prose_style}\n\n"
            "WORLD DATA\n"
            "==========\n"
            f"{json.dumps(world_data, indent=2, ensure_ascii=False)}\n\n"
            "STORY DATA\n"
            "==========\n"
            f"{json.dumps(story_data, indent=2, ensure_ascii=False)}"
        )

        return [
            {"type": "text", "text": preamble},
            {
                "type": "text",
                "text": world_section,
                "cache_control": {"type": "ephemeral"},
            },
        ]

    # ------------------------------------------------------------------
    # State formatting
    # ------------------------------------------------------------------

    def _format_state(self, state: "GameState") -> str:
        lines = [
            f"Location: {state.current_location}",
            f"Inventory: {', '.join(state.inventory) if state.inventory else '(empty)'}",
            f"Discovered locations: {', '.join(sorted(state.discovered_locations))}",
            f"Turn: {state.turn_count}",
        ]
        if state.flags:
            lines.append(f"Story flags: {json.dumps(state.flags)}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def _execute_tool(self, name: str, inputs: dict) -> tuple[str, dict]:
        """Execute a narrator tool call. Returns (result_message, state_change)."""
        if name == "update_location":
            loc_id = inputs["location_id"]
            return (
                f"Location updated to {loc_id}.",
                {"type": "location", "location_id": loc_id},
            )

        elif name == "update_inventory":
            action = inputs["action"]
            item_id = inputs["item_id"]
            return (
                f"Inventory {action}: {item_id}.",
                {"type": "inventory", "action": action, "item_id": item_id},
            )

        elif name == "set_story_flag":
            flag = inputs["flag"]
            value = inputs["value"]
            return (
                f"Flag set: {flag} = {value!r}.",
                {"type": "flag", "flag": flag, "value": value},
            )

        elif name == "reveal_location":
            loc_id = inputs["location_id"]
            return (
                f"Location revealed: {loc_id}.",
                {"type": "reveal", "location_id": loc_id},
            )

        elif name == "end_game":
            outcome = inputs["outcome"]
            summary = inputs.get("summary", "")
            return (
                f"Game ended: {outcome}.",
                {"type": "end_game", "outcome": outcome, "summary": summary},
            )

        return "Unknown tool.", {}

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _trim_history(self) -> None:
        """
        Keep the conversation from growing unbounded.
        Preserves the most recent N turns (each turn = user + assistant pair).
        """
        # Each turn is 2 messages; preserve at least the opening exchange
        max_messages = self.max_history_turns * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]

    # ------------------------------------------------------------------
    # Narration — the main public interface
    # ------------------------------------------------------------------

    def narrate(
        self, player_input: str, state: "GameState"
    ) -> Iterator[tuple[str, Any]]:
        """
        Stream narration for a player action.

        Yields:
            ("text", str)            — narration chunk to display immediately
            ("state_change", dict)   — state change to apply
            ("game_over", dict)      — game-ending data
        """
        state_context = self._format_state(state)
        user_content = (
            f"[CURRENT STATE]\n{state_context}\n\n"
            f"[PLAYER ACTION]\n{player_input}"
        )
        self.messages.append({"role": "user", "content": user_content})

        # Agentic loop: narrate → tool calls → (optionally) more narration
        while True:
            with self.client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=1024,
                system=self.system_blocks,
                tools=NARRATOR_TOOLS,
                messages=self.messages,
            ) as stream:
                for event in stream:
                    if (
                        event.type == "content_block_delta"
                        and event.delta.type == "text_delta"
                    ):
                        yield ("text", event.delta.text)

                final = stream.get_final_message()

            # Append full assistant response (preserves any thinking blocks)
            self.messages.append({"role": "assistant", "content": final.content})

            if final.stop_reason == "end_turn":
                self._trim_history()
                break

            if final.stop_reason == "tool_use":
                tool_results = []
                game_over_change: dict | None = None

                for block in final.content:
                    if block.type == "tool_use":
                        result_msg, state_change = self._execute_tool(
                            block.name, block.input
                        )
                        if state_change:
                            yield ("state_change", state_change)
                            if state_change["type"] == "end_game":
                                game_over_change = state_change

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_msg,
                            }
                        )

                self.messages.append({"role": "user", "content": tool_results})

                if game_over_change:
                    self._trim_history()
                    yield ("game_over", game_over_change)
                    break

            else:
                # Unexpected stop reason — stop the loop
                self._trim_history()
                break

    def opening(self, state: "GameState") -> Iterator[tuple[str, Any]]:
        """
        Generate the opening narration for a new game session.
        Does not update state — purely atmospheric scene-setting.
        """
        state_context = self._format_state(state)
        user_content = (
            f"[CURRENT STATE]\n{state_context}\n\n"
            f"[SYSTEM] Begin the story. Write the opening scene only — "
            f"atmospheric, specific, setting up the world and the player's situation. "
            f"Do not move the player or change any state. Aim for 150–250 words."
        )
        self.messages.append({"role": "user", "content": user_content})

        with self.client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=512,
            system=self.system_blocks,
            messages=self.messages,  # No tools for the opening
        ) as stream:
            for event in stream:
                if (
                    event.type == "content_block_delta"
                    and event.delta.type == "text_delta"
                ):
                    yield ("text", event.delta.text)

            final = stream.get_final_message()

        self.messages.append({"role": "assistant", "content": final.content})
