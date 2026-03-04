#!/bin/bash
# ============================================================
#  Claude Code IDE — per-user installer (no sudo)
#  Installs to ~/.local/share/claude-code-ide/
#  Creates commands: automate, automate-gui in ~/.local/bin/
# ============================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }

INSTALL_DIR="$HOME/.local/share/claude-code-ide"
BIN_DIR="$HOME/.local/bin"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Claude Code IDE — Installer${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo ""

# ============================================================
#  1. Check requirements
# ============================================================

info "Checking requirements..."

# Python >= 3.10
if ! command -v python3 &>/dev/null; then
    err "python3 not found. Install Python 3.10+."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    err "Python $PYTHON_VERSION found, >= 3.10 required."
    exit 1
fi
ok "Python $PYTHON_VERSION"

# pip / venv
if ! python3 -m pip --version &>/dev/null; then
    err "pip not found. Install python3-pip."
    exit 1
fi
ok "pip available"

if ! python3 -m venv --help &>/dev/null; then
    err "venv module not available. Install python3-venv."
    exit 1
fi
ok "venv available"

# tkinter (warning, not blocking)
HAS_TKINTER=true
if ! python3 -c "import tkinter" &>/dev/null; then
    warn "tkinter not available — GUI (automate-gui) will not work."
    warn "CLI (automate) will work normally."
    warn "To install: sudo apt install python3-tk (Debian/Ubuntu)"
    HAS_TKINTER=false
else
    ok "tkinter available"
fi

# claude CLI (warning, not blocking)
HAS_CLAUDE=true
if ! command -v claude &>/dev/null; then
    warn "Claude Code CLI not found in PATH."
    warn "Install: npm install -g @anthropic-ai/claude-code"
    HAS_CLAUDE=false
else
    ok "claude CLI available"
fi

echo ""

# ============================================================
#  2. Create directories
# ============================================================

info "Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
ok "$INSTALL_DIR"
ok "$BIN_DIR"

# ============================================================
#  3. Copy .py files + config.json
# ============================================================

info "Copying files..."

PY_FILES=(
    main.py
    cli.py
    claude_code.py
    config_manager.py
    discord_notifier.py
    scraper.py
    firecrawl_tool.py
    demo_code.py
)

for f in "${PY_FILES[@]}"; do
    if [ -f "$SCRIPT_DIR/$f" ]; then
        cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
    else
        warn "Skipped missing file: $f"
    fi
done

# config.json — copy only if it doesn't exist in INSTALL_DIR
if [ ! -f "$INSTALL_DIR/config.json" ]; then
    if [ -f "$SCRIPT_DIR/config.json" ]; then
        cp "$SCRIPT_DIR/config.json" "$INSTALL_DIR/config.json"
        ok "config.json copied (default)"
    fi
else
    ok "config.json — kept existing"
fi

# requirements.txt
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
fi

ok "Files copied"

# ============================================================
#  4. Create venv and install dependencies
# ============================================================

info "Creating virtual environment..."

if [ -d "$INSTALL_DIR/.venv" ]; then
    info "venv already exists — updating dependencies"
else
    python3 -m venv "$INSTALL_DIR/.venv"
    ok "venv created"
fi

info "Installing dependencies (may take a few minutes)..."
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip --quiet
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
ok "Dependencies installed"

# ============================================================
#  5. crawl4ai-setup (Chromium)
# ============================================================

info "Running crawl4ai-setup (downloading Chromium)..."
if "$INSTALL_DIR/.venv/bin/crawl4ai-setup" 2>/dev/null; then
    ok "crawl4ai-setup complete"
else
    warn "crawl4ai-setup failed — scraper may not work"
    warn "You can run it later: $INSTALL_DIR/.venv/bin/crawl4ai-setup"
fi

# ============================================================
#  6. Wrapper scripts in ~/.local/bin/
# ============================================================

info "Creating commands..."

cat > "$BIN_DIR/automate" << 'WRAPPER'
#!/bin/bash
exec ~/.local/share/claude-code-ide/.venv/bin/python \
     ~/.local/share/claude-code-ide/cli.py "$@"
WRAPPER
chmod +x "$BIN_DIR/automate"
ok "automate → CLI/scheduler"

cat > "$BIN_DIR/automate-gui" << 'WRAPPER'
#!/bin/bash
exec ~/.local/share/claude-code-ide/.venv/bin/python \
     ~/.local/share/claude-code-ide/main.py "$@"
WRAPPER
chmod +x "$BIN_DIR/automate-gui"
ok "automate-gui → GUI"

# ============================================================
#  7. Check PATH
# ============================================================

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    warn "$BIN_DIR is not in PATH!"
    warn "Add to ~/.bashrc or ~/.zshrc:"
    warn '  export PATH="$HOME/.local/bin:$PATH"'
    warn "Then: source ~/.bashrc"
fi

# ============================================================
#  8. Summary
# ============================================================

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BLUE}Commands:${NC}"
echo -e "    automate          — CLI runner / scheduler"
echo -e "    automate-gui      — GUI application"
echo ""
echo -e "  ${BLUE}Usage:${NC}"
echo -e "    cd ~/your-project"
echo -e "    automate --help"
echo -e "    automate --run script.py"
echo -e "    automate-gui"
echo ""
echo -e "  ${BLUE}Files:${NC}"
echo -e "    Installation:  $INSTALL_DIR/"
echo -e "    Commands:      $BIN_DIR/automate, $BIN_DIR/automate-gui"
echo ""

if [ "$HAS_TKINTER" = false ]; then
    warn "GUI unavailable (tkinter missing). CLI works normally."
fi
if [ "$HAS_CLAUDE" = false ]; then
    warn "Claude CLI not found — install before use."
fi
