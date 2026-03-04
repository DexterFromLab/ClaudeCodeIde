#!/usr/bin/env python3
"""
Claude Code IDE - Runner konsolowy.

Uruchomienie:
    python3 cli.py                          # Scheduler loop (daemon)
    python3 cli.py --run script.py          # Jednorazowe wykonanie pliku
    python3 cli.py --config /path/config.json  # Z innym plikiem konfiguracji
"""

import argparse
import io
import os
import queue
import signal
import sys
import time
import traceback
import threading
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime

from config_manager import ConfigManager
from discord_notifier import DiscordNotifier
from claude_code import ClaudeCode


# ============================================================
#  Logging z prefiksami
# ============================================================

def log(tag: str, msg: str):
    """Wypisz sformatowana linie: [HH:MM:SS] [TAG] msg"""
    ts = datetime.now().strftime("%H:%M:%S")
    # Wyrownaj tag do 10 znakow
    print(f"[{ts}] [{tag:<10}] {msg}", flush=True)


# ============================================================
#  Context Keeper hook
# ============================================================

def make_context_hook(ctx_cfg: dict):
    """Tworzy message_hook na bazie konfiguracji context_keeper."""
    if not ctx_cfg.get("active", False):
        return None

    prompt = ctx_cfg.get("prompt", "").strip()
    if not prompt:
        return None

    auto_first = ctx_cfg.get("auto_first", True)
    auto_every = ctx_cfg.get("auto_every", False)
    auto_remind = ctx_cfg.get("auto_remind", True)
    interval = ctx_cfg.get("interval", 100)

    call_count = [0]
    lock = threading.Lock()

    def hook(message: str) -> str:
        with lock:
            n = call_count[0]
            call_count[0] += 1

        prefix = ""

        if n == 0 and auto_first:
            prefix = prompt
            log("CONTEXT", f"Context injected (call #{n})")
        elif auto_every and n > 0:
            prefix = f"[PRZYPOMNIENIE KONTEKSTU - wywolanie #{n}]\n\n{prompt}"
            log("CONTEXT", f"Context reminder (call #{n})")
        elif auto_remind and interval > 0 and n > 0 and n % interval == 0:
            prefix = f"[PRZYPOMNIENIE KONTEKSTU POCZATKOWEGO - wywolanie #{n}]\n\n{prompt}"
            log("CONTEXT", f"Periodic context reminder (call #{n}, every {interval})")

        if prefix:
            return f"{prefix}\n\n{message}"
        return message

    return hook


# ============================================================
#  Wykonywanie kodu
# ============================================================

def execute_code(code: str, name: str, discord: DiscordNotifier = None) -> str:
    """Wykonaj kod Python, wypisz output z prefiksem [SCHEDULER], powiadom Discord."""
    log("SCHEDULER", f'Job "{name}" started')
    start_time = time.time()

    output_buf = io.StringIO()

    project_dir = os.path.dirname(os.path.abspath(__file__))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)
    venv_sp = os.path.join(project_dir, ".venv", "lib")
    if os.path.isdir(venv_sp):
        import glob as g
        for sp in g.glob(os.path.join(venv_sp, "python*", "site-packages")):
            if sp not in sys.path:
                sys.path.insert(0, sp)

    had_error = False
    try:
        with redirect_stdout(output_buf), redirect_stderr(output_buf):
            exec(code, {"__name__": "__main__", "__builtins__": __builtins__})
    except Exception:
        output_buf.write(traceback.format_exc())
        had_error = True

    output = output_buf.getvalue()
    elapsed = time.time() - start_time

    # Wypisz output linia po linii z prefiksem
    if output.strip():
        for line in output.rstrip("\n").split("\n"):
            log("SCHEDULER", f">>> {line}")

    tag = "error" if had_error else "done"
    log("SCHEDULER", f'Job "{name}" {tag} ({elapsed:.1f}s)')

    # Discord
    if discord:
        discord.notify_scheduler(name, output)
        log("DISCORD", f'Sent scheduler result for "{name}"')

    return output


# ============================================================
#  Scheduler - import klas z main.py bez GUI
# ============================================================

def _import_scheduler_classes():
    """Importuj ScheduledJob i Scheduler z main.py - te klasy nie zaleza od tkinter."""
    # Zamiast importowac caly main.py (ktory importuje tkinter),
    # uzyj bezposrednich klas ktore sa niezalezne od GUI.
    # Poniewaz ScheduledJob i Scheduler sa w main.py ale nie uzywaja tkinter,
    # musimy je zaimportowac selektywnie lub zduplikowac.
    # Najlepsze podejscie: zduplikuj minimalna wersje tu.
    pass


# Minimalna kopia Scheduler i ScheduledJob (bez tkinter) do uzycia w CLI
from dataclasses import dataclass, field
from datetime import timedelta


@dataclass
class ScheduledJob:
    name: str
    code: str
    mode: str              # "once" | "daily" | "interval" | "weekly"
    time_str: str          # "14:30"
    date_str: str          # "2026-03-15" (dla once)
    interval_min: int      # minuty (dla interval)
    weekdays: list         # 0=Pn..6=Nd (dla weekly)
    active: bool = True
    next_run: datetime = field(default_factory=datetime.now)
    last_run: datetime | None = None


class Scheduler:
    """Silnik harmonogramu - identyczny z main.py ale bez tkinter."""

    def __init__(self):
        self.jobs: list[ScheduledJob] = []

    def add_job(self, job: ScheduledJob):
        job.next_run = self._calculate_next_run(job)
        self.jobs.append(job)

    def remove_job(self, name: str):
        self.jobs = [j for j in self.jobs if j.name != name]

    def toggle_job(self, name: str):
        for j in self.jobs:
            if j.name == name:
                j.active = not j.active
                if j.active:
                    j.next_run = self._calculate_next_run(j)
                return j.active
        return None

    def get_due_jobs(self) -> list[ScheduledJob]:
        now = datetime.now()
        return [j for j in self.jobs if j.active and j.next_run <= now]

    def mark_run(self, job: ScheduledJob):
        job.last_run = datetime.now()
        if job.mode == "once":
            job.active = False
        else:
            job.next_run = self._calculate_next_run(job)

    def _calculate_next_run(self, job: ScheduledJob) -> datetime:
        now = datetime.now()

        if job.mode == "once":
            try:
                return datetime.strptime(f"{job.date_str} {job.time_str}", "%Y-%m-%d %H:%M")
            except ValueError:
                return now

        elif job.mode == "daily":
            try:
                h, m = map(int, job.time_str.split(":"))
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if target <= now:
                    target += timedelta(days=1)
                return target
            except ValueError:
                return now + timedelta(days=1)

        elif job.mode == "interval":
            return now + timedelta(minutes=max(job.interval_min, 1))

        elif job.mode == "weekly":
            if not job.weekdays:
                return now + timedelta(days=7)
            try:
                h, m = map(int, job.time_str.split(":"))
            except ValueError:
                h, m = 0, 0
            for delta in range(1, 8):
                candidate = now + timedelta(days=delta)
                if candidate.weekday() in job.weekdays:
                    return candidate.replace(hour=h, minute=m, second=0, microsecond=0)
            if now.weekday() in job.weekdays:
                target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if target > now:
                    return target
            return now + timedelta(days=1)

        return now + timedelta(hours=1)

    def next_scheduled(self) -> datetime | None:
        active = [j for j in self.jobs if j.active]
        if not active:
            return None
        return min(j.next_run for j in active)


# ============================================================
#  Ladowanie jobow z konfiguracji
# ============================================================

def load_jobs_from_config(cfg: dict) -> list[ScheduledJob]:
    """Utworz liste ScheduledJob z konfiguracji JSON."""
    jobs = []
    for jd in cfg.get("scheduler_jobs", []):
        job = ScheduledJob(
            name=jd.get("name", "unnamed"),
            code=jd.get("code", ""),
            mode=jd.get("mode", "interval"),
            time_str=jd.get("time_str", "00:00"),
            date_str=jd.get("date_str", ""),
            interval_min=jd.get("interval_min", 30),
            weekdays=jd.get("weekdays", []),
            active=jd.get("active", True),
        )
        jobs.append(job)
    return jobs


# ============================================================
#  Claude traffic listener (konsola)
# ============================================================

def make_traffic_listener(discord: DiscordNotifier = None, notify_claude: bool = False):
    """Tworzy traffic listener ktory loguje do konsoli."""
    def listener(direction: str, text: str, meta: dict):
        if direction == "send":
            preview = text[:200].replace("\n", " ")
            log("CLAUDE", f">>> Prompt: {preview}...")
        elif direction == "recv":
            preview = text[:200].replace("\n", " ")
            model = meta.get("model", "")
            cost = meta.get("cost_usd")
            info = f" ({model}" if model else ""
            if cost:
                info += f", ${cost:.4f}"
            if info:
                info += ")"
            log("CLAUDE", f"<<< Response{info}: {preview}...")

            if discord and notify_claude:
                discord.notify_claude(text, model)
                log("DISCORD", "Sent Claude response")
        elif direction == "error":
            log("CLAUDE", f"!!! Error: {text[:200]}")

    return listener


# ============================================================
#  Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Claude Code IDE - runner konsolowy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Przyklady:
  python3 cli.py                             # Scheduler loop
  python3 cli.py --run script.py             # Jednorazowe uruchomienie
  python3 cli.py --config ~/myconfig.json    # Z innym plikiem konfiguracji
""",
    )
    parser.add_argument("--config", default="config.json",
                        help="Sciezka do pliku konfiguracji (domyslnie: config.json)")
    parser.add_argument("--run", metavar="FILE",
                        help="Uruchom plik .py i zakoncz (bez schedulera)")
    args = parser.parse_args()

    # Wczytaj konfiguracje
    config_path = args.config
    if not os.path.exists(config_path):
        log("SYSTEM", f"config.json nie znaleziony w: {os.path.abspath(config_path)}")
        log("SYSTEM", "Uzyto domyslnej konfiguracji. Utworz config.json w katalogu projektu lub uzyj --config.")

    cm = ConfigManager(config_path)
    cfg = cm.load()

    log("SYSTEM", f"Config: {os.path.abspath(config_path)}")

    # --- Discord ---
    discord = None
    discord_cfg = cfg.get("discord", {})
    if discord_cfg.get("active") and discord_cfg.get("webhook_url"):
        def discord_log(msg, level):
            log("DISCORD", msg)
        discord = DiscordNotifier(
            webhook_url=discord_cfg["webhook_url"],
            active=True,
            on_log=discord_log,
        )
        log("DISCORD", f"Notifier active (webhook: ...{discord_cfg['webhook_url'][-20:]})")
    else:
        log("DISCORD", "Notifier inactive (no webhook or disabled)")

    # --- Context Keeper ---
    ctx_cfg = cfg.get("context_keeper", {})
    hook = make_context_hook(ctx_cfg)
    if hook:
        ClaudeCode.set_message_hook(hook)
        log("CONTEXT", "Context keeper active")
    else:
        log("CONTEXT", "Context keeper inactive")

    # --- Traffic listener ---
    notify_claude = discord_cfg.get("notify_claude", False)
    listener = make_traffic_listener(discord, notify_claude)
    ClaudeCode.add_traffic_listener(listener)

    # === Tryb: jednorazowe uruchomienie ===
    if args.run:
        if not os.path.exists(args.run):
            log("SYSTEM", f"File not found: {args.run}")
            sys.exit(1)
        with open(args.run, "r", encoding="utf-8") as f:
            code = f.read()
        log("SYSTEM", f"Running: {args.run}")
        execute_code(code, os.path.basename(args.run), discord)
        log("SYSTEM", "Done.")
        return

    # === Tryb: scheduler loop ===
    jobs = load_jobs_from_config(cfg)
    scheduler = Scheduler()

    if not jobs:
        log("SCHEDULER", "No jobs configured. Nothing to do.")
        log("SYSTEM", "Tip: Add jobs to scheduler_jobs in config.json or use --run to execute a file.")
        return

    for job in jobs:
        scheduler.add_job(job)
        log("SCHEDULER", f'Job "{job.name}" ({job.mode}) -> next: {job.next_run.strftime("%Y-%m-%d %H:%M:%S")}')

    active_count = sum(1 for j in scheduler.jobs if j.active)
    log("SCHEDULER", f"{active_count} active job(s). Starting tick loop... (Ctrl+C to stop)")

    # Obsluga Ctrl+C
    running = True

    def signal_handler(sig, frame):
        nonlocal running
        running = False
        log("SYSTEM", "Shutting down...")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Glowna petla
    while running:
        due = scheduler.get_due_jobs()
        for job in due:
            scheduler.mark_run(job)
            # Uruchom w osobnym watku
            notify_sched = discord_cfg.get("notify_scheduler", False)
            d = discord if notify_sched else None
            threading.Thread(
                target=execute_code,
                args=(job.code, job.name, d),
                daemon=True,
            ).start()

        # Wyswietl nastepny zaplanowany czas co 60s
        try:
            time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            running = False

    log("SYSTEM", "Bye.")


if __name__ == "__main__":
    main()
