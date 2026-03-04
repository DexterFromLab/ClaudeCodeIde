#!/bin/bash
# ============================================================
#  Claude Code IDE — instalator per-user (bez sudo)
#  Instaluje do ~/.local/share/claude-code-ide/
#  Tworzy komendy: automate, automate-gui w ~/.local/bin/
# ============================================================

set -euo pipefail

# Kolory
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
echo -e "${BLUE}  Claude Code IDE — Instalator${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════${NC}"
echo ""

# ============================================================
#  1. Sprawdz wymagania
# ============================================================

info "Sprawdzam wymagania..."

# Python >= 3.10
if ! command -v python3 &>/dev/null; then
    err "python3 nie znaleziony. Zainstaluj Python 3.10+."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
    err "Python $PYTHON_VERSION znaleziony, wymagany >= 3.10."
    exit 1
fi
ok "Python $PYTHON_VERSION"

# pip / venv
if ! python3 -m pip --version &>/dev/null; then
    err "pip nie znaleziony. Zainstaluj python3-pip."
    exit 1
fi
ok "pip dostepny"

if ! python3 -m venv --help &>/dev/null; then
    err "modul venv niedostepny. Zainstaluj python3-venv."
    exit 1
fi
ok "venv dostepny"

# tkinter (ostrzezenie, nie blokada)
HAS_TKINTER=true
if ! python3 -c "import tkinter" &>/dev/null; then
    warn "tkinter niedostepny — GUI (automate-gui) nie bedzie dzialac."
    warn "CLI (automate) bedzie dzialac normalnie."
    warn "Aby zainstalowac: sudo apt install python3-tk (Debian/Ubuntu)"
    HAS_TKINTER=false
else
    ok "tkinter dostepny"
fi

# claude CLI (ostrzezenie, nie blokada)
HAS_CLAUDE=true
if ! command -v claude &>/dev/null; then
    warn "Claude Code CLI nie znaleziony w PATH."
    warn "Zainstaluj: npm install -g @anthropic-ai/claude-code"
    HAS_CLAUDE=false
else
    ok "claude CLI dostepny"
fi

echo ""

# ============================================================
#  2. Utworz katalogi
# ============================================================

info "Tworzenie katalogow..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
ok "$INSTALL_DIR"
ok "$BIN_DIR"

# ============================================================
#  3. Kopiuj pliki .py + config.json
# ============================================================

info "Kopiowanie plikow..."

PY_FILES=(
    main.py
    cli.py
    claude_code.py
    config_manager.py
    discord_notifier.py
    scraper.py
    firecrawl_tool.py
    examples.py
    demo_code.py
)

for f in "${PY_FILES[@]}"; do
    if [ -f "$SCRIPT_DIR/$f" ]; then
        cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
    else
        warn "Pominięto brakujacy plik: $f"
    fi
done

# config.json — kopiuj tylko jesli nie istnieje w INSTALL_DIR
if [ ! -f "$INSTALL_DIR/config.json" ]; then
    if [ -f "$SCRIPT_DIR/config.json" ]; then
        cp "$SCRIPT_DIR/config.json" "$INSTALL_DIR/config.json"
        ok "config.json skopiowany (domyslny)"
    fi
else
    ok "config.json — zachowano istniejacy"
fi

# requirements.txt
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt"
fi

ok "Pliki skopiowane"

# ============================================================
#  4. Utworz venv i zainstaluj zaleznosci
# ============================================================

info "Tworzenie srodowiska wirtualnego..."

if [ -d "$INSTALL_DIR/.venv" ]; then
    info "venv juz istnieje — aktualizacja zaleznosci"
else
    python3 -m venv "$INSTALL_DIR/.venv"
    ok "venv utworzony"
fi

info "Instalowanie zaleznosci (moze potrwac kilka minut)..."
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip --quiet
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --quiet
ok "Zaleznosci zainstalowane"

# ============================================================
#  5. crawl4ai-setup (Chromium)
# ============================================================

info "Uruchamianie crawl4ai-setup (pobieranie Chromium)..."
if "$INSTALL_DIR/.venv/bin/crawl4ai-setup" 2>/dev/null; then
    ok "crawl4ai-setup zakonczone"
else
    warn "crawl4ai-setup nie powiodlo sie — scraper moze nie dzialac"
    warn "Mozesz uruchomic pozniej: $INSTALL_DIR/.venv/bin/crawl4ai-setup"
fi

# ============================================================
#  6. Wrapper scripts w ~/.local/bin/
# ============================================================

info "Tworzenie komend..."

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
#  7. Sprawdz PATH
# ============================================================

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    warn "$BIN_DIR nie jest w PATH!"
    warn "Dodaj do ~/.bashrc lub ~/.zshrc:"
    warn '  export PATH="$HOME/.local/bin:$PATH"'
    warn "Nastepnie: source ~/.bashrc"
fi

# ============================================================
#  8. Podsumowanie
# ============================================================

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Instalacja zakonczona!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BLUE}Komendy:${NC}"
echo -e "    automate          — CLI runner / scheduler"
echo -e "    automate-gui      — GUI aplikacja"
echo ""
echo -e "  ${BLUE}Uzycie:${NC}"
echo -e "    cd ~/twoj-projekt"
echo -e "    automate --help"
echo -e "    automate --run skrypt.py"
echo -e "    automate-gui"
echo ""
echo -e "  ${BLUE}Pliki:${NC}"
echo -e "    Instalacja:  $INSTALL_DIR/"
echo -e "    Komendy:     $BIN_DIR/automate, $BIN_DIR/automate-gui"
echo ""

if [ "$HAS_TKINTER" = false ]; then
    warn "GUI niedostepne (brak tkinter). CLI dziala normalnie."
fi
if [ "$HAS_CLAUDE" = false ]; then
    warn "Claude CLI nie znaleziony — zainstaluj przed uzyciem."
fi
