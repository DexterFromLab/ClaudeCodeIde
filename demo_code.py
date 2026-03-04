"""
=== Claude Code IDE + Scraper Demo ===
Nacisnij F5 aby uruchomic!

Scraper dziala LOKALNIE na Twoim komputerze.
Bez API keys, bez tokenow, bez limitow.
Uzywa przegladarki Chromium przez Crawl4AI.
"""
import time
from scraper import Scraper
from claude_code import ClaudeCode

scraper = Scraper()
claude = ClaudeCode()

# ==================================================
# 1. SCRAPE - pobierz tresc strony
# ==================================================
print("=" * 50)
print("  KROK 1: Scrapuje strone lokalnie")
print("=" * 50)
print()

url = "https://docs.python.org/3/whatsnew/3.12.html"
print(f"URL: {url}")
print("Otwieram przegladarke i scrapuje...\n")

t0 = time.time()
page = scraper.scrape(url)

if page.is_error:
    print(f"Blad: {page.error_msg}")
else:
    print(page.summary)
    print()
    print("--- Pierwsze 500 znakow ---")
    print(page.markdown[:500])
    print("...\n")

# ==================================================
# 2. MULTI-SCRAPE - wiele stron na raz
# ==================================================
print("=" * 50)
print("  KROK 2: Scrapuje 3 strony na raz")
print("=" * 50)
print()

urls = [
    "https://example.com",
    "https://httpbin.org/html",
    "https://www.python.org",
]
print(f"Scrapuje {len(urls)} stron rownolegle...\n")

t0 = time.time()
results = scraper.scrape_many(urls)
elapsed = time.time() - t0

for r in results:
    if r.is_error:
        print(f"  BLAD {r.url}: {r.error_msg}")
    else:
        print(f"  OK {r.url}")
        print(f"     Tytul: {r.title}")
        print(f"     Rozmiar: {len(r.markdown)} zn")
print(f"\nLacznie w {elapsed:.1f}s\n")

# ==================================================
# 3. SCRAPE + CLAUDE - scrapuj i analizuj
# ==================================================
print("=" * 50)
print("  KROK 3: Scrape + analiza przez Claude")
print("=" * 50)
print()

if page.is_error:
    print("Pomijam - poprzedni scrape sie nie udal.")
else:
    print("Pytam Claude o podsumowanie strony...")
    print("(to moze potrwac ~30-60 sekund)\n")

    t0 = time.time()
    resp = claude.scrape_and_ask(
        url,
        "Wymien 5 najwazniejszych nowosci z tej strony. "
        "Dla kazdej podaj krotki opis."
    )
    elapsed = time.time() - t0

    print(f"Odpowiedz Claude ({elapsed:.1f}s):\n")
    print(resp.text)

    # --- Wyslij analize na Discord ---
    print("\nWysylam wynik na Discord...")
    import json, urllib.request
    webhook_url = ""  # <-- wklej tu swoj webhook URL z Discorda
    if webhook_url:
        msg = f"**Analiza Python 3.12 ({elapsed:.1f}s):**\n{resp.text[:1900]}"
        payload = json.dumps({"content": msg}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ClaudeCodeIDE/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                print(f"Discord: wyslano! (HTTP {r.status})")
        except Exception as e:
            print(f"Discord: blad - {e}")
    else:
        print("Brak webhook URL - wklej go w zmiennej webhook_url w kodzie")
        print("albo uzyj zakladki Discord w IDE (latwiej!)")

print()
print("=" * 50)
print("  DEMO ZAKONCZONE!")
print("  Bez zadnych API keys i tokenow :)")
print("=" * 50)
