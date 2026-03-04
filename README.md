# Claude Code IDE

Desktopowe IDE do automatyzacji z wbudowanym Claude AI, scraperem stron i schedulerem zadań.

Zbudowane w Pythonie (tkinter). Ciemny motyw, dwa panele: narzędzia po lewej, edytor Pythona po prawej.

## Funkcje

- **Claude** — czat z Claude Code CLI, podgląd pełnej komunikacji (prompty + odpowiedzi)
- **Scraper** — scrapowanie stron przez Crawl4AI (lokalnie, bez API keys)
- **Context Keeper** — automatyczne wstrzykiwanie kontekstu do każdego wywołania Claude
- **Scheduler** — uruchamianie kodu z edytora wg harmonogramu (raz, codziennie, co N minut, dni tygodnia)
- **Discord** — powiadomienia webhook (wyniki schedulera, odpowiedzi Claude)
- **Edytor Python** — z podświetlaniem składni, konsolą wyjścia, F5 do uruchomienia
- **CLI** — tryb konsolowy (`automate`) do uruchamiania skryptów i schedulera bez GUI

## Wymagania

- Python 3.10+
- python3-venv (`sudo apt install python3-venv` na Debian/Ubuntu)
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) zainstalowane i skonfigurowane
- tkinter (`sudo apt install python3-tk`) — wymagane tylko dla GUI

## Instalacja

```bash
git clone https://github.com/DexterFromLab/ClaudeCodeIde.git
cd ClaudeCodeIde
bash install.sh
```

Instalator (`install.sh`):
- Nie wymaga sudo — instaluje per-user do `~/.local/`
- Tworzy venv, instaluje zależności (Crawl4AI, Firecrawl), uruchamia `crawl4ai-setup`
- Tworzy komendy `automate` i `automate-gui` w `~/.local/bin/`
- Przy aktualizacji nadpisuje pliki .py, ale zachowuje istniejący `config.json`

Jeśli `~/.local/bin` nie jest w PATH, dodaj do `~/.bashrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Deinstalacja

```bash
bash uninstall.sh
```

## Użycie

### GUI

```bash
automate-gui
```

### CLI — jednorazowe uruchomienie skryptu

```bash
cd ~/twoj-projekt
automate --run skrypt.py
```

### CLI — scheduler (daemon)

```bash
cd ~/twoj-projekt
automate
```

Scheduler czyta `config.json` z bieżącego katalogu. Możesz wskazać inny plik:

```bash
automate --config ~/inny-projekt/config.json
```

## Skróty klawiszowe (GUI)

| Skrót | Akcja |
|-------|-------|
| `F5` | Uruchom kod z edytora |
| `Ctrl+S` | Zapisz plik |
| `Ctrl+O` | Otwórz plik |

## Struktura plików

| Plik | Opis |
|------|------|
| `main.py` | Główna aplikacja GUI |
| `cli.py` | Runner konsolowy / scheduler |
| `claude_code.py` | Wrapper Claude Code CLI (`ClaudeCode`, `ClaudeResponse`) |
| `config_manager.py` | Zarządzanie konfiguracją JSON |
| `scraper.py` | Lokalny scraper oparty na Crawl4AI |
| `firecrawl_tool.py` | Opcjonalny scraper przez Firecrawl API |
| `discord_notifier.py` | Powiadomienia Discord webhook |
| `examples.py` | Przykłady użycia klasy `ClaudeCode` z poziomu Pythona |
| `demo_code.py` | Przykładowy skrypt ładowany w edytorze |
| `install.sh` | Instalator per-user |
| `uninstall.sh` | Deinstalator |

## Użycie z kodu

```python
from claude_code import ClaudeCode

claude = ClaudeCode()
resp = claude.ask("Napisz funkcję sortującą")
print(resp.text)
```

```python
from scraper import Scraper

scraper = Scraper()
page = scraper.scrape("https://example.com")
print(page.markdown)
```

## Discord webhook

1. Discord → Ustawienia kanału → Integracje → Webhook → Nowy → Kopiuj URL
2. Wklej URL w zakładce Discord w IDE (lub w `config.json`)
3. Kliknij "Test" (GUI) lub sprawdź logi CLI
