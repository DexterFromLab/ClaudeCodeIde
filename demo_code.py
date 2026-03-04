"""
=== Claude Code IDE + Scraper Demo ===
Press F5 to run!

The scraper runs LOCALLY on your machine.
No API keys, no tokens, no limits.
Uses Chromium browser via Crawl4AI.
"""
import time
from scraper import Scraper
from claude_code import ClaudeCode

scraper = Scraper()
claude = ClaudeCode()

# ==================================================
# 1. SCRAPE - fetch page content
# ==================================================
print("=" * 50)
print("  STEP 1: Scraping page locally")
print("=" * 50)
print()

url = "https://docs.python.org/3/whatsnew/3.12.html"
print(f"URL: {url}")
print("Opening browser and scraping...\n")

t0 = time.time()
page = scraper.scrape(url)

if page.is_error:
    print(f"Error: {page.error_msg}")
else:
    print(page.summary)
    print()
    print("--- First 500 characters ---")
    print(page.markdown[:500])
    print("...\n")

# ==================================================
# 2. MULTI-SCRAPE - multiple pages at once
# ==================================================
print("=" * 50)
print("  STEP 2: Scraping 3 pages at once")
print("=" * 50)
print()

urls = [
    "https://example.com",
    "https://httpbin.org/html",
    "https://www.python.org",
]
print(f"Scraping {len(urls)} pages in parallel...\n")

t0 = time.time()
results = scraper.scrape_many(urls)
elapsed = time.time() - t0

for r in results:
    if r.is_error:
        print(f"  ERROR {r.url}: {r.error_msg}")
    else:
        print(f"  OK {r.url}")
        print(f"     Title: {r.title}")
        print(f"     Size: {len(r.markdown)} chars")
print(f"\nTotal in {elapsed:.1f}s\n")

# ==================================================
# 3. SCRAPE + CLAUDE - scrape and analyze
# ==================================================
print("=" * 50)
print("  STEP 3: Scrape + analysis by Claude")
print("=" * 50)
print()

if page.is_error:
    print("Skipping - previous scrape failed.")
else:
    print("Asking Claude to summarize the page...")
    print("(this may take ~30-60 seconds)\n")

    t0 = time.time()
    resp = claude.scrape_and_ask(
        url,
        "List the 5 most important new features from this page. "
        "Provide a brief description for each."
    )
    elapsed = time.time() - t0

    print(f"Claude response ({elapsed:.1f}s):\n")
    print(resp.text)

    # --- Send analysis to Discord ---
    print("\nSending result to Discord...")
    import json, urllib.request
    webhook_url = ""  # <-- paste your Discord webhook URL here
    if webhook_url:
        msg = f"**Python 3.12 Analysis ({elapsed:.1f}s):**\n{resp.text[:1900]}"
        payload = json.dumps({"content": msg}).encode("utf-8")
        req = urllib.request.Request(
            webhook_url, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ClaudeCodeIDE/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                print(f"Discord: sent! (HTTP {r.status})")
        except Exception as e:
            print(f"Discord: error - {e}")
    else:
        print("No webhook URL - paste it in the webhook_url variable in the code")
        print("or use the Discord tab in the IDE (easier!)")

print()
print("=" * 50)
print("  DEMO COMPLETE!")
print("  No API keys or tokens needed :)")
print("=" * 50)
