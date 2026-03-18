#!/usr/bin/env python3
"""
Brannacht — AI Text Adventure Engine
Entry point and CLI.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

BANNER = r"""
  ╔══════════════════════════════════════════════════╗
  ║                  B R A N N A C H T               ║
  ║            AI-Narrated Text Adventure            ║
  ╚══════════════════════════════════════════════════╝
"""

SEP = "  " + "─" * 54


def print_sep() -> None:
    print(f"\n{SEP}\n")


def print_info(msg: str) -> None:
    print(f"  [{msg}]")


def print_error(msg: str) -> None:
    print(f"  [!] {msg}", file=sys.stderr)


def stream_narration(events) -> dict | None:
    """
    Consume the event stream from the engine, printing text as it arrives.
    Returns game_over data if the game ended, else None.
    """
    game_over_data = None
    print("  ", end="", flush=True)

    for event_type, data in events:
        if event_type == "text":
            # Indent narration lines for readability
            text: str = data
            # Indent each newline so paragraphs stay visually aligned
            text = text.replace("\n", "\n  ")
            print(text, end="", flush=True)
        elif event_type == "game_over":
            game_over_data = data

    print()  # Final newline after streamed text
    return game_over_data


def prompt_input(location_name: str) -> str:
    """Display the input prompt and return stripped player input."""
    print()
    try:
        return input(f"  ({location_name}) > ").strip()
    except (EOFError, KeyboardInterrupt):
        return "quit"


def show_help() -> None:
    print("""
  COMMANDS
  ────────────────────────────────────────────────────
  look / examine             Look around your location
  go <direction>             Move: north, south, east…
  take / pick up <item>      Pick up an item
  drop <item>                Drop an item
  use <item>                 Use an item
  inventory / i              Check your inventory
  talk to <name>             Speak with a character
  examine <thing>            Look closely at something

  save [name]                Save your game
  load <name>                Load a saved game
  saves                      List saved games
  help                       Show this message
  quit / exit                Quit

  You can also type anything naturally — the narrator
  understands plain English. Try: "ask Bram about the
  Crown Prince" or "break down the door".
  ────────────────────────────────────────────────────
""")


def show_saves(save_dir: Path) -> None:
    saves = sorted(save_dir.glob("*.json"))
    if not saves:
        print_info("No saved games found.")
    else:
        print()
        print("  Saved games:")
        for s in saves:
            print(f"    {s.stem}")
        print()


def print_game_over(data: dict) -> None:
    outcome = data.get("outcome", "end")
    summary = data.get("summary", "")
    print_sep()
    if outcome == "victory":
        print("  ✦  THE END  ✦")
    elif outcome == "defeat":
        print("  ✦  YOU HAVE FALLEN  ✦")
    else:
        print("  ✦  TO BE CONTINUED  ✦")
    if summary:
        print()
        print(f"  {summary}")
    print_sep()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="brannacht",
        description="Brannacht — AI-Narrated Text Adventure Engine",
    )
    parser.add_argument(
        "--story",
        default="data/stories/the_shattered_crown.json",
        metavar="PATH",
        help="Path to the story JSON file (default: The Shattered Crown)",
    )
    parser.add_argument(
        "--world",
        default="data/world",
        metavar="DIR",
        help="Path to the world data directory",
    )
    parser.add_argument(
        "--prose",
        default="data/prose_style.md",
        metavar="PATH",
        help="Path to the prose style guide",
    )
    parser.add_argument(
        "--load",
        metavar="SAVE_NAME",
        help="Load a saved game by name (without .json extension)",
    )
    parser.add_argument(
        "--list-saves",
        action="store_true",
        help="List available saved games and exit",
    )
    args = parser.parse_args()

    save_dir = Path("saves")

    if args.list_saves:
        show_saves(save_dir)
        return

    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print_error(
            "ANTHROPIC_API_KEY is not set.\n"
            "  Export your key: export ANTHROPIC_API_KEY=sk-ant-..."
        )
        sys.exit(1)

    print(BANNER)

    # Initialise engine
    try:
        from game.engine import GameEngine

        engine = GameEngine(
            story_path=args.story,
            world_dir=args.world,
            prose_path=args.prose,
            save_dir=save_dir,
        )
    except FileNotFoundError as exc:
        print_error(f"Could not load game data: {exc}")
        sys.exit(1)

    # Load or start new game
    if args.load:
        save_path = save_dir / f"{args.load}.json"
        try:
            engine.load_game(save_path)
            print_info(f"Loaded: {args.load}")
        except FileNotFoundError:
            print_error(f"Save file not found: {args.load}")
            sys.exit(1)
        print_sep()
    else:
        engine.new_game()
        print(f"  {engine.story_title}")
        print_sep()
        print_info("Opening scene...")
        print()
        stream_narration(engine.opening())
        print_sep()

    print("  Type 'help' for commands. Type 'quit' to exit.")

    # Main game loop
    while not engine.game_over:
        player_input = prompt_input(engine.current_location_name)

        if not player_input:
            continue

        lower = player_input.lower()

        # ── Meta commands ──────────────────────────────────────────────
        if lower in ("quit", "exit", "q"):
            print()
            print_info("Farewell. The story awaits your return.")
            break

        if lower == "help":
            show_help()
            continue

        if lower == "saves":
            show_saves(save_dir)
            continue

        if lower.startswith("save"):
            parts = player_input.split(maxsplit=1)
            name = parts[1].strip() if len(parts) > 1 else None
            try:
                path = engine.save_game(name)
                print_info(f"Saved to {path}")
            except Exception as exc:
                print_error(f"Save failed: {exc}")
            continue

        if lower.startswith("load "):
            save_name = player_input[5:].strip()
            save_path = save_dir / f"{save_name}.json"
            try:
                engine.load_game(save_path)
                print_info(f"Loaded: {save_name}")
            except FileNotFoundError:
                print_error(f"Save file not found: {save_name}")
            continue

        # ── Game turn ──────────────────────────────────────────────────
        print()
        try:
            game_over_data = stream_narration(engine.process_turn(player_input))
        except anthropic_import_error() as exc:
            print_error(f"API error: {exc}")
            print_info("Check your ANTHROPIC_API_KEY and internet connection.")
            continue
        except Exception as exc:
            print_error(f"Unexpected error: {exc}")
            print_info("Your progress is auto-saved. Try again or type 'quit'.")
            continue

        print()

        if game_over_data:
            print_game_over(game_over_data)
            break


def anthropic_import_error():
    """Return the anthropic API error class, importing lazily."""
    try:
        import anthropic
        return anthropic.APIError
    except ImportError:
        return Exception


if __name__ == "__main__":
    main()
