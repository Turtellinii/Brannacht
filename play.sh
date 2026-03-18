#!/bin/bash
# Brannacht launcher — double-click this file to play.
# On most Linux desktops: right-click → Properties → Allow executing as program,
# then double-click and choose "Run in Terminal".

cd "$(dirname "$0")"

# ── Check Python ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "Python 3 is required but was not found."
    echo "Install it with: sudo apt install python3"
    read -rp "Press Enter to exit..."
    exit 1
fi

# ── Check / prompt for API key ────────────────────────────────────────────────
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "Your Anthropic API key is not set."
    echo "You can get one at: https://console.anthropic.com"
    echo ""
    read -rp "Paste your API key here: " entered_key
    if [ -z "$entered_key" ]; then
        echo "No key entered. Exiting."
        read -rp "Press Enter to exit..."
        exit 1
    fi
    export ANTHROPIC_API_KEY="$entered_key"
fi

# ── Install dependencies if missing ───────────────────────────────────────────
if ! python3 -c "import anthropic" &>/dev/null; then
    echo "Installing required packages..."
    pip3 install -q -r requirements.txt
fi

# ── Launch game ───────────────────────────────────────────────────────────────
python3 main.py "$@"

echo ""
read -rp "Press Enter to close..."
