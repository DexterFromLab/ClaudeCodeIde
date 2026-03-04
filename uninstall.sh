#!/bin/bash
# ============================================================
#  Claude Code IDE — uninstaller
# ============================================================

set -euo pipefail

echo "Uninstalling Claude Code IDE..."

rm -rf ~/.local/share/claude-code-ide/
rm -f ~/.local/bin/automate
rm -f ~/.local/bin/automate-gui

echo "Uninstalled. All files removed."
