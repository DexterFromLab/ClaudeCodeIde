#!/bin/bash
# ============================================================
#  Claude Code IDE — deinstalator
# ============================================================

set -euo pipefail

echo "Odinstalowywanie Claude Code IDE..."

rm -rf ~/.local/share/claude-code-ide/
rm -f ~/.local/bin/automate
rm -f ~/.local/bin/automate-gui

echo "Odinstalowano. Wszystkie pliki usuniete."
