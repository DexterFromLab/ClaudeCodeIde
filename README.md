# Claude Code IDE

Desktop IDE for automation with built-in Claude AI, web scraper, and task scheduler.

Built in Python (tkinter). Dark theme, two panels: tools on the left, Python editor on the right.

## Features

- **Claude** — chat with Claude Code CLI, full communication view (prompts + responses)
- **Scraper** — web scraping via Crawl4AI (local, no API keys)
- **Context Keeper** — automatic context injection into every Claude call
- **Scheduler** — run code from the editor on schedule (once, daily, every N minutes, weekdays)
- **Discord** — webhook notifications (scheduler results, Claude responses)
- **Python Editor** — with syntax highlighting, output console, F5 to run
- **CLI** — console mode (`automate`) for running scripts and scheduler without GUI

## Requirements

- Python 3.10+
- python3-venv (`sudo apt install python3-venv` on Debian/Ubuntu)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and configured
- tkinter (`sudo apt install python3-tk`) — required only for GUI

## Installation

```bash
git clone https://github.com/DexterFromLab/ClaudeCodeIde.git
cd ClaudeCodeIde
bash install.sh
```

The installer (`install.sh`):
- Requires no sudo — installs per-user to `~/.local/`
- Creates a venv, installs dependencies (Crawl4AI, Firecrawl), runs `crawl4ai-setup`
- Creates `automate` and `automate-gui` commands in `~/.local/bin/`
- On update, overwrites .py files but preserves existing `config.json`

If `~/.local/bin` is not in PATH, add to `~/.bashrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Uninstallation

```bash
bash uninstall.sh
```

## Usage

### GUI

```bash
automate-gui
```

### CLI — one-time script execution

```bash
cd ~/your-project
automate --run script.py
```

### CLI — scheduler (daemon)

```bash
cd ~/your-project
automate
```

The scheduler reads `config.json` from the current directory. You can specify a different file:

```bash
automate --config ~/other-project/config.json
```

## Keyboard shortcuts (GUI)

| Shortcut | Action |
|----------|--------|
| `F5` | Run code from editor |
| `Ctrl+S` | Save file |
| `Ctrl+O` | Open file |

## File structure

| File | Description |
|------|-------------|
| `main.py` | Main GUI application |
| `cli.py` | Console runner / scheduler |
| `claude_code.py` | Claude Code CLI wrapper (`ClaudeCode`, `ClaudeResponse`) |
| `config_manager.py` | JSON configuration management |
| `scraper.py` | Local scraper based on Crawl4AI |
| `firecrawl_tool.py` | Optional scraper via Firecrawl API |
| `discord_notifier.py` | Discord webhook notifications |
| `demo_code.py` | Demo script loaded in the editor |
| `install.sh` | Per-user installer |
| `uninstall.sh` | Uninstaller |

## Usage from code

```python
from claude_code import ClaudeCode

claude = ClaudeCode()
resp = claude.ask("Write a sorting function")
print(resp.text)
```

```python
from scraper import Scraper

scraper = Scraper()
page = scraper.scrape("https://example.com")
print(page.markdown)
```

## Discord webhook

1. Discord → Channel Settings → Integrations → Webhook → New → Copy URL
2. Paste the URL in the Discord tab in IDE (or in `config.json`)
3. Click "Test" (GUI) or check CLI logs
