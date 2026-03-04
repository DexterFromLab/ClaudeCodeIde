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

## Wymagania

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) zainstalowane i skonfigurowane
- Crawl4AI (do scrapowania):
  ```
  pip install crawl4ai
  crawl4ai-setup
  ```

## Uruchomienie

```bash
python3 main.py
```

## Skróty klawiszowe

| Skrót | Akcja |
|-------|-------|
| `F5` | Uruchom kod z edytora |
| `Ctrl+S` | Zapisz plik |
| `Ctrl+O` | Otwórz plik |

## Struktura plików

| Plik | Opis |
|------|------|
| `main.py` | Główna aplikacja GUI |
| `claude_code.py` | Wrapper Claude Code CLI (`ClaudeCode`, `ClaudeResponse`) |
| `scraper.py` | Lokalny scraper oparty na Crawl4AI |
| `demo_code.py` | Przykładowy skrypt ładowany w edytorze |
| `examples.py` | Przykłady użycia klasy `ClaudeCode` z poziomu Pythona |

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
2. Wklej URL w zakładce Discord w IDE
3. Kliknij "Test"
