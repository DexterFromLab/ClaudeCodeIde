#!/usr/bin/env python3
"""
Claude Code IDE - Claude on the left, Python editor on the right.
Integrated with Crawl4AI for web scraping.
Scheduler for running code on schedule.
"""

import io
import json
import os
import queue
import sys
import traceback
import threading
import tkinter as tk
import urllib.request
import urllib.error
from tkinter import ttk, scrolledtext, filedialog, messagebox
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from claude_code import ClaudeCode, ClaudeResponse
from config_manager import ConfigManager
from discord_notifier import DiscordNotifier


class LiveWriter(io.TextIOBase):
    """Stream that sends text to a queue instead of buffering."""

    def __init__(self, output_queue: queue.Queue, tag: str = ""):
        self._queue = output_queue
        self._tag = tag

    def write(self, text: str) -> int:
        if text:
            self._queue.put((text, self._tag))
        return len(text) if text else 0

    def flush(self):
        pass

    @property
    def encoding(self):
        return "utf-8"


# ============================================================
#  Tab: Claude Code
# ============================================================

class ClaudeTab(ttk.Frame):
    """Claude Code console."""

    def __init__(self, parent):
        super().__init__(parent)
        self._build_ui()
        self.claude = ClaudeCode(
            on_response=self._on_response,
            on_error=self._on_error,
        )
        # Queue + polling - reliable pattern for tkinter + background threads
        self._traffic_queue = queue.Queue()
        ClaudeCode.add_traffic_listener(self._on_traffic)
        self._poll_traffic()

    def _build_ui(self):
        self.chat = scrolledtext.ScrolledText(
            self, wrap=tk.WORD, font=("monospace", 11),
            bg="#1e1e2e", fg="#cdd6f4", insertbackground="#cdd6f4",
            selectbackground="#45475a", relief=tk.FLAT, padx=8, pady=8,
            state=tk.DISABLED,
        )
        self.chat.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.chat.tag_configure("user", foreground="#89b4fa", font=("monospace", 11, "bold"))
        self.chat.tag_configure("claude", foreground="#a6e3a1")
        self.chat.tag_configure("error", foreground="#f38ba8")
        self.chat.tag_configure("system", foreground="#6c7086", font=("monospace", 10, "italic"))
        self.chat.tag_configure("prompt_full", foreground="#cba6f7", font=("monospace", 9))
        self.chat.tag_configure("traffic_header", foreground="#f9e2af", font=("monospace", 9, "bold"))
        self.chat.tag_configure("response_full", foreground="#94e2d5", font=("monospace", 9))

        input_frame = ttk.Frame(self)
        input_frame.pack(fill=tk.X, padx=4, pady=(0, 4))

        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(input_frame, textvariable=self.input_var, font=("monospace", 11))
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        self.input_entry.bind("<Return>", self._on_send)

        self.send_btn = ttk.Button(input_frame, text="Send", command=self._on_send)
        self.send_btn.pack(side=tk.RIGHT)

        self._append_text("Type a message for Claude Code.\n", "system")

    def _append_text(self, text, tag=None):
        self.chat.configure(state=tk.NORMAL)
        if tag:
            self.chat.insert(tk.END, text, tag)
        else:
            self.chat.insert(tk.END, text)
        self.chat.configure(state=tk.DISABLED)
        self.chat.see(tk.END)

    def _on_send(self, event=None):
        msg = self.input_var.get().strip()
        if not msg or self.claude.busy:
            return
        self.input_var.set("")

        # Context injection works globally in ClaudeCode.ask() via message_hook
        self._append_text("Claude is thinking...\n", "system")
        self.send_btn.configure(state=tk.DISABLED)
        self.claude.send_chat(msg)

    def _on_traffic(self, direction: str, text: str, meta: dict):
        """Global listener - pushes to queue (called from any thread)."""
        self._traffic_queue.put((direction, text, meta))

    def _poll_traffic(self):
        """Poll every 100ms - reads queue and displays in chat (main thread)."""
        try:
            while True:
                direction, text, meta = self._traffic_queue.get_nowait()
                self._show_traffic_item(direction, text, meta)
        except queue.Empty:
            pass
        self.after(100, self._poll_traffic)

    def _show_traffic_item(self, direction: str, text: str, meta: dict):
        if direction == "send":
            self._append_text(f"\n>>> PROMPT SENT >>>\n", "traffic_header")
            if meta.get("system_prompt"):
                self._append_text(f"[system_prompt: {meta['system_prompt'][:100]}...]\n", "system")
            self._append_text(f"{text}\n", "prompt_full")
            self._append_text(f">>> END OF PROMPT >>>\n\n", "traffic_header")

        elif direction == "recv":
            self._remove_thinking()
            self._append_text(f"<<< CLAUDE RESPONSE <<<\n", "traffic_header")
            self._append_text(f"{text}\n", "response_full")
            meta_parts = []
            if meta.get("model"):
                meta_parts.append(meta["model"])
            if meta.get("cost_usd"):
                meta_parts.append(f"${meta['cost_usd']:.4f}")
            if meta.get("duration_ms"):
                meta_parts.append(f"{meta['duration_ms']:.0f}ms")
            if meta_parts:
                self._append_text(f"  [{' | '.join(meta_parts)}]\n", "system")
            self._append_text(f"<<< END OF RESPONSE <<<\n\n", "traffic_header")
            self.send_btn.configure(state=tk.NORMAL)
            self.input_entry.focus_set()

        elif direction == "error":
            self._remove_thinking()
            self._append_text(f"<<< ERROR <<<\n", "traffic_header")
            self._append_text(f"{text}\n", "error")
            self._append_text(f"<<< END OF ERROR <<<\n\n", "traffic_header")
            self.send_btn.configure(state=tk.NORMAL)
            self.input_entry.focus_set()

    def _on_response(self, response):
        # Response displayed via traffic polling - unlock UI as fallback
        pass

    def _on_error(self, error):
        # Error displayed via traffic polling
        pass

    def _remove_thinking(self):
        self.chat.configure(state=tk.NORMAL)
        content = self.chat.get("1.0", tk.END)
        idx = content.rfind("Claude is thinking...")
        if idx != -1:
            ln = content[:idx].count("\n") + 1
            self.chat.delete(f"{ln}.0", f"{ln}.end+1c")
        self.chat.configure(state=tk.DISABLED)


# ============================================================
#  Tab: Scraper (Crawl4AI - 100% local)
# ============================================================

class ScraperTab(ttk.Frame):
    """Scraper panel - scraping and mapping pages.
    Uses Crawl4AI - runs locally, no API keys."""

    def __init__(self, parent, claude_tab: ClaudeTab):
        super().__init__(parent)
        self.claude_tab = claude_tab
        self._sc = None
        self._build_ui()

    def _get_sc(self):
        if self._sc is None:
            try:
                from scraper import Scraper
                self._sc = Scraper(on_status=self._on_status)
            except ImportError:
                messagebox.showerror("Error", "Missing scraper module.\npip install crawl4ai && crawl4ai-setup")
                return None
        return self._sc

    def _build_ui(self):
        # --- Info ---
        info = ttk.Label(
            self,
            text="Local browser (Crawl4AI) - no API keys, no limits",
            font=("monospace", 9, "italic"),
            foreground="#a6e3a1",
        )
        info.pack(fill=tk.X, padx=8, pady=(8, 2))

        # --- Actions ---
        action_frame = ttk.LabelFrame(self, text="Action")
        action_frame.pack(fill=tk.X, padx=4, pady=4)

        self.action_var = tk.StringVar(value="scrape")
        actions = [
            ("Scrape", "scrape"),
            ("Multi-scrape", "multi"),
            ("Map links", "map"),
            ("Scrape+Claude", "scrape_ask"),
        ]
        btn_row = ttk.Frame(action_frame)
        btn_row.pack(fill=tk.X, padx=4, pady=4)
        for text, val in actions:
            ttk.Radiobutton(btn_row, text=text, variable=self.action_var, value=val).pack(side=tk.LEFT, padx=4)

        # --- URL ---
        input_frame = ttk.Frame(action_frame)
        input_frame.pack(fill=tk.X, padx=4, pady=(0, 4))

        ttk.Label(input_frame, text="URL:").pack(side=tk.LEFT)
        self.url_var = tk.StringVar()
        url_entry = ttk.Entry(input_frame, textvariable=self.url_var, font=("monospace", 10))
        url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        url_entry.bind("<Return>", lambda e: self._run_action())

        self.go_btn = ttk.Button(input_frame, text="Start", command=self._run_action)
        self.go_btn.pack(side=tk.RIGHT)

        # --- Question for Claude ---
        q_frame = ttk.Frame(action_frame)
        q_frame.pack(fill=tk.X, padx=4, pady=(0, 4))

        ttk.Label(q_frame, text="Question:").pack(side=tk.LEFT)
        self.question_var = tk.StringVar()
        ttk.Entry(q_frame, textvariable=self.question_var, font=("monospace", 10)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4
        )

        # --- Result ---
        self.result_text = scrolledtext.ScrolledText(
            self, wrap=tk.WORD, font=("monospace", 11),
            bg="#1e1e2e", fg="#cdd6f4", insertbackground="#cdd6f4",
            selectbackground="#45475a", relief=tk.FLAT, padx=8, pady=8,
            state=tk.DISABLED,
        )
        self.result_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.result_text.tag_configure("title", foreground="#89b4fa", font=("monospace", 11, "bold"))
        self.result_text.tag_configure("url", foreground="#f9e2af")
        self.result_text.tag_configure("status", foreground="#6c7086", font=("monospace", 10, "italic"))
        self.result_text.tag_configure("error", foreground="#f38ba8")
        self.result_text.tag_configure("success", foreground="#a6e3a1")

        # --- Bottom buttons ---
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=4, pady=(0, 4))
        ttk.Button(bottom, text="Clear", command=self._clear).pack(side=tk.LEFT)
        ttk.Button(bottom, text="Send to Claude", command=self._send_to_claude).pack(side=tk.RIGHT)
        ttk.Button(bottom, text="Insert into editor", command=self._insert_to_editor).pack(side=tk.RIGHT, padx=4)

    def _on_status(self, msg):
        self.after(0, self._append_result, f"{msg}\n", "status")

    def _append_result(self, text, tag=None):
        self.result_text.configure(state=tk.NORMAL)
        if tag:
            self.result_text.insert(tk.END, text, tag)
        else:
            self.result_text.insert(tk.END, text)
        self.result_text.configure(state=tk.DISABLED)
        self.result_text.see(tk.END)

    def _clear(self):
        self.result_text.configure(state=tk.NORMAL)
        self.result_text.delete("1.0", tk.END)
        self.result_text.configure(state=tk.DISABLED)

    def _run_action(self):
        sc = self._get_sc()
        if not sc:
            return

        url = self.url_var.get().strip()
        if not url:
            self._append_result("Enter a URL.\n", "error")
            return

        action = self.action_var.get()
        self.go_btn.configure(state=tk.DISABLED)
        self._append_result(f"\n{'='*40}\n", "status")

        threading.Thread(target=self._do_action, args=(action, url), daemon=True).start()

    def _do_action(self, action, url):
        sc = self._get_sc()
        try:
            if action == "scrape":
                result = sc.scrape(url)
                if result.is_error:
                    self.after(0, self._append_result, f"Error: {result.error_msg}\n", "error")
                else:
                    self.after(0, self._show_scrape, result)

            elif action == "multi":
                urls = [u.strip() for u in url.split(",") if u.strip()]
                if len(urls) < 2:
                    self.after(0, self._append_result,
                        "Enter multiple URLs separated by commas.\n"
                        "E.g.: https://a.com, https://b.com\n", "error")
                    return
                self.after(0, self._append_result, f"Scraping {len(urls)} pages...\n", "status")
                results = sc.scrape_many(urls)
                for r in results:
                    if r.is_error:
                        self.after(0, self._append_result, f"Error {r.url}: {r.error_msg}\n", "error")
                    else:
                        self.after(0, self._show_scrape, r)
                        self.after(0, self._append_result, "\n---\n\n", "status")

            elif action == "map":
                self.after(0, self._append_result, f"Mapping links on {url}...\n", "status")
                urls = sc.map_site(url, max_depth=1)
                self.after(0, self._show_urls, url, urls)

            elif action == "scrape_ask":
                question = self.question_var.get().strip()
                if not question:
                    self.after(0, self._append_result, "Enter a question in the 'Question' field.\n", "error")
                    return
                self.after(0, self._append_result, "Scraping page...\n", "status")
                result = sc.scrape(url)
                if result.is_error:
                    self.after(0, self._append_result, f"Scrape error: {result.error_msg}\n", "error")
                    return
                self.after(0, self._append_result,
                    f"OK ({len(result.markdown)} chars). Asking Claude...\n", "status")
                claude = ClaudeCode()
                resp = claude.scrape_and_ask(url, question)
                self.after(0, self._append_result,
                    f"\n{resp.text}\n",
                    "success" if not resp.is_error else "error")

        except Exception as e:
            self.after(0, self._append_result, f"Exception: {e}\n", "error")
        finally:
            self.after(0, lambda: self.go_btn.configure(state=tk.NORMAL))

    def _show_scrape(self, result):
        self._append_result(f"Page: {result.title or '(no title)'}\n", "title")
        self._append_result(f"{result.url}\n", "url")
        self._append_result(f"[{len(result.markdown)} chars | {len(result.links)} links | {result.elapsed_sec:.1f}s]\n\n", "status")
        md = result.markdown
        if len(md) > 5000:
            self._append_result(md[:5000] + f"\n\n... (truncated, total {len(md)} chars)\n")
        else:
            self._append_result(md + "\n")

    def _show_urls(self, base_url, urls):
        self._append_result(f"Links on {base_url}: {len(urls)} found\n\n", "title")
        for u in urls[:80]:
            self._append_result(f"  {u}\n", "url")
        if len(urls) > 80:
            self._append_result(f"\n  ... and {len(urls) - 80} more\n", "status")

    def _send_to_claude(self):
        content = self.result_text.get("1.0", tk.END).strip()
        if not content:
            return
        if len(content) > 8000:
            content = content[:8000] + "\n...(truncated)"
        self.claude_tab._append_text(f"\n[Scraper -> Claude]\n", "system")
        self.claude_tab.input_var.set(f"Analyze this data from the page:\n{content[:200]}...")
        self.claude_tab.input_entry.focus_set()

    def _insert_to_editor(self):
        content = self.result_text.get("1.0", tk.END).strip()
        if not content:
            return
        self.event_generate("<<InsertToEditor>>", data=content)


# ============================================================
#  Scheduler - code execution schedule
# ============================================================

@dataclass
class ScheduledJob:
    name: str
    code: str
    mode: str              # "once" | "daily" | "interval" | "weekly"
    time_str: str          # "14:30"
    date_str: str          # "2026-03-15" (for once)
    interval_min: int      # minutes (for interval)
    weekdays: list         # 0=Mon..6=Sun (for weekly)
    active: bool = True
    next_run: datetime = field(default_factory=datetime.now)
    last_run: datetime | None = None


class Scheduler:
    """Schedule engine - manages jobs and calculates next_run."""

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
        due = []
        for j in self.jobs:
            if j.active and j.next_run <= now:
                due.append(j)
        return due

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
                dt = datetime.strptime(f"{job.date_str} {job.time_str}", "%Y-%m-%d %H:%M")
                return dt
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
            # Find nearest weekday
            for delta in range(1, 8):
                candidate = now + timedelta(days=delta)
                if candidate.weekday() in job.weekdays:
                    return candidate.replace(hour=h, minute=m, second=0, microsecond=0)
            # Still today?
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


class SchedulerTab(ttk.Frame):
    """Scheduler tab - code execution schedule."""

    def __init__(self, parent, python_panel_ref, discord_tab=None):
        super().__init__(parent)
        self.python_panel = python_panel_ref
        self.discord_tab = discord_tab
        self.scheduler = Scheduler()
        self._build_ui()
        self._tick()

    def _build_ui(self):
        # --- Top panel: adding tasks ---
        add_frame = ttk.LabelFrame(self, text="New task")
        add_frame.pack(fill=tk.X, padx=4, pady=4)

        # Name
        name_row = ttk.Frame(add_frame)
        name_row.pack(fill=tk.X, padx=4, pady=(4, 2))
        ttk.Label(name_row, text="Name:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar()
        ttk.Entry(name_row, textvariable=self.name_var, font=("monospace", 10)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4
        )

        # Mode
        mode_row = ttk.Frame(add_frame)
        mode_row.pack(fill=tk.X, padx=4, pady=2)
        self.mode_var = tk.StringVar(value="interval")
        for text, val in [("Once", "once"), ("Daily", "daily"),
                          ("Every X min", "interval"), ("Weekdays", "weekly")]:
            ttk.Radiobutton(mode_row, text=text, variable=self.mode_var,
                            value=val, command=self._on_mode_change).pack(side=tk.LEFT, padx=3)

        # Parameters - container
        self.params_frame = ttk.Frame(add_frame)
        self.params_frame.pack(fill=tk.X, padx=4, pady=2)

        # Date (once)
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d"))
        # Time
        self.hour_var = tk.StringVar(value="12")
        self.min_var = tk.StringVar(value="00")
        # Interval
        self.interval_var = tk.StringVar(value="30")
        # Weekdays
        self.weekday_vars = [tk.BooleanVar(value=False) for _ in range(7)]

        self._on_mode_change()

        # Buttons
        btn_row = ttk.Frame(add_frame)
        btn_row.pack(fill=tk.X, padx=4, pady=(2, 4))
        ttk.Button(btn_row, text="Add to schedule", command=self._add_job).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_row, text="Run now", command=self._run_now).pack(side=tk.LEFT)

        # --- Task list ---
        list_frame = ttk.LabelFrame(self, text="Scheduled tasks")
        list_frame.pack(fill=tk.X, padx=4, pady=4)

        cols = ("name", "mode", "next_run", "status")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=5)
        self.tree.heading("name", text="Name")
        self.tree.heading("mode", text="Mode")
        self.tree.heading("next_run", text="Next run")
        self.tree.heading("status", text="Status")
        self.tree.column("name", width=100)
        self.tree.column("mode", width=80)
        self.tree.column("next_run", width=140)
        self.tree.column("status", width=70)
        self.tree.pack(fill=tk.X, padx=4, pady=4)

        # Treeview styles
        style = ttk.Style()
        style.configure("Treeview", background="#1e1e2e", foreground="#cdd6f4",
                         fieldbackground="#1e1e2e", rowheight=22)
        style.configure("Treeview.Heading", background="#313244", foreground="#cdd6f4")

        tree_btns = ttk.Frame(list_frame)
        tree_btns.pack(fill=tk.X, padx=4, pady=(0, 4))
        ttk.Button(tree_btns, text="Pause/Resume", command=self._toggle_selected).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(tree_btns, text="Remove", command=self._remove_selected).pack(side=tk.LEFT)

        # --- Execution log ---
        log_frame = ttk.LabelFrame(self, text="Execution log")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("monospace", 10),
            bg="#11111b", fg="#cdd6f4", insertbackground="#cdd6f4",
            selectbackground="#45475a", relief=tk.FLAT, padx=6, pady=6,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_configure("error", foreground="#f38ba8")
        self.log_text.tag_configure("info", foreground="#a6e3a1")
        self.log_text.tag_configure("time", foreground="#f9e2af")
        self.log_text.tag_configure("status", foreground="#6c7086", font=("monospace", 9, "italic"))

        # --- Status bar ---
        self.status_var = tk.StringVar(value="No scheduled tasks")
        status_bar = ttk.Label(self, textvariable=self.status_var,
                               font=("monospace", 9, "italic"), foreground="#6c7086")
        status_bar.pack(fill=tk.X, padx=8, pady=(0, 4))

    def _on_mode_change(self):
        for w in self.params_frame.winfo_children():
            w.destroy()

        mode = self.mode_var.get()

        if mode == "once":
            ttk.Label(self.params_frame, text="Date:").pack(side=tk.LEFT)
            ttk.Entry(self.params_frame, textvariable=self.date_var, width=12,
                      font=("monospace", 10)).pack(side=tk.LEFT, padx=4)
            ttk.Label(self.params_frame, text="Time:").pack(side=tk.LEFT)
            ttk.Entry(self.params_frame, textvariable=self.hour_var, width=3,
                      font=("monospace", 10)).pack(side=tk.LEFT, padx=2)
            ttk.Label(self.params_frame, text=":").pack(side=tk.LEFT)
            ttk.Entry(self.params_frame, textvariable=self.min_var, width=3,
                      font=("monospace", 10)).pack(side=tk.LEFT, padx=2)

        elif mode == "daily":
            ttk.Label(self.params_frame, text="Time:").pack(side=tk.LEFT)
            ttk.Entry(self.params_frame, textvariable=self.hour_var, width=3,
                      font=("monospace", 10)).pack(side=tk.LEFT, padx=2)
            ttk.Label(self.params_frame, text=":").pack(side=tk.LEFT)
            ttk.Entry(self.params_frame, textvariable=self.min_var, width=3,
                      font=("monospace", 10)).pack(side=tk.LEFT, padx=2)

        elif mode == "interval":
            ttk.Label(self.params_frame, text="Every").pack(side=tk.LEFT)
            ttk.Entry(self.params_frame, textvariable=self.interval_var, width=5,
                      font=("monospace", 10)).pack(side=tk.LEFT, padx=4)
            ttk.Label(self.params_frame, text="minutes").pack(side=tk.LEFT)

        elif mode == "weekly":
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            for i, day in enumerate(days):
                ttk.Checkbutton(self.params_frame, text=day,
                                variable=self.weekday_vars[i]).pack(side=tk.LEFT, padx=1)
            ttk.Label(self.params_frame, text=" at").pack(side=tk.LEFT)
            ttk.Entry(self.params_frame, textvariable=self.hour_var, width=3,
                      font=("monospace", 10)).pack(side=tk.LEFT, padx=2)
            ttk.Label(self.params_frame, text=":").pack(side=tk.LEFT)
            ttk.Entry(self.params_frame, textvariable=self.min_var, width=3,
                      font=("monospace", 10)).pack(side=tk.LEFT, padx=2)

    def _add_job(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Scheduler", "Enter a task name.")
            return
        # Check for duplicate
        if any(j.name == name for j in self.scheduler.jobs):
            messagebox.showwarning("Scheduler", f"Task '{name}' already exists.")
            return

        code = self.python_panel.editor.get("1.0", tk.END).strip()
        if not code:
            messagebox.showwarning("Scheduler", "Editor is empty - enter code to run.")
            return

        mode = self.mode_var.get()
        time_str = f"{self.hour_var.get().zfill(2)}:{self.min_var.get().zfill(2)}"
        date_str = self.date_var.get().strip()
        try:
            interval_min = int(self.interval_var.get())
        except ValueError:
            interval_min = 30
        weekdays = [i for i, v in enumerate(self.weekday_vars) if v.get()]

        job = ScheduledJob(
            name=name, code=code, mode=mode,
            time_str=time_str, date_str=date_str,
            interval_min=interval_min, weekdays=weekdays,
        )
        self.scheduler.add_job(job)
        self._refresh_tree()
        self._update_status()
        self._log(f"Added task '{name}' ({mode}), next: {job.next_run.strftime('%Y-%m-%d %H:%M:%S')}", "info")
        self.name_var.set("")

    def _run_now(self):
        code = self.python_panel.editor.get("1.0", tk.END).strip()
        if not code:
            messagebox.showwarning("Scheduler", "Editor is empty.")
            return
        name = self.name_var.get().strip() or "test"
        self._log(f"Running '{name}' immediately...", "info")
        threading.Thread(target=self._execute_job_code, args=(name, code), daemon=True).start()

    def _toggle_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.tree.item(sel[0])["values"][0]
        result = self.scheduler.toggle_job(name)
        if result is not None:
            state = "active" if result else "paused"
            self._log(f"Task '{name}' -> {state}", "info")
        self._refresh_tree()
        self._update_status()

    def _remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        name = self.tree.item(sel[0])["values"][0]
        self.scheduler.remove_job(name)
        self._log(f"Removed task '{name}'", "info")
        self._refresh_tree()
        self._update_status()

    def _refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        mode_labels = {"once": "Once", "daily": "Daily",
                       "interval": "Recurring", "weekly": "Weekly"}
        for j in self.scheduler.jobs:
            status = "Active" if j.active else "Paused"
            next_str = j.next_run.strftime("%Y-%m-%d %H:%M") if j.active else "-"
            self.tree.insert("", tk.END, values=(j.name, mode_labels.get(j.mode, j.mode),
                                                  next_str, status))

    def _update_status(self):
        active = sum(1 for j in self.scheduler.jobs if j.active)
        nxt = self.scheduler.next_scheduled()
        if active == 0:
            self.status_var.set("No active tasks")
        elif nxt:
            self.status_var.set(f"Active: {active} | Next: {nxt.strftime('%H:%M:%S')}")
        else:
            self.status_var.set(f"Active: {active}")

    def _tick(self):
        """Check every second if a task needs to run."""
        due = self.scheduler.get_due_jobs()
        for job in due:
            self._log(f"Running '{job.name}'...", "time")
            self.scheduler.mark_run(job)
            threading.Thread(target=self._execute_job_code,
                             args=(job.name, job.code), daemon=True).start()
        if due:
            self._refresh_tree()
        self._update_status()
        self.after(1000, self._tick)

    def _execute_job_code(self, name: str, code: str):
        """Run code in a thread, output to log."""
        output_queue = queue.Queue()
        live_stdout = LiveWriter(output_queue, tag="")
        live_stderr = LiveWriter(output_queue, tag="error")

        project_dir = os.path.dirname(os.path.abspath(__file__))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        venv_sp = os.path.join(project_dir, ".venv", "lib")
        if os.path.isdir(venv_sp):
            import glob as g
            for sp in g.glob(os.path.join(venv_sp, "python*", "site-packages")):
                if sp not in sys.path:
                    sys.path.insert(0, sp)

        try:
            with redirect_stdout(live_stdout), redirect_stderr(live_stderr):
                exec(code, {"__name__": "__main__", "__builtins__": __builtins__})
        except Exception:
            output_queue.put((traceback.format_exc(), "error"))
        finally:
            output_queue.put(("__DONE__", ""))

        # Read all output
        lines = []
        while True:
            try:
                text, tag = output_queue.get_nowait()
                if text == "__DONE__":
                    break
                lines.append((text, tag))
            except queue.Empty:
                break

        # Display in log (from main thread)
        def show():
            self._log(f"--- [{name}] {datetime.now().strftime('%H:%M:%S')} ---", "time")
            for text, tag in lines:
                self._log_raw(text, tag if tag else None)
        self.after(0, show)

        # Discord - send result if configured
        if self.discord_tab and lines:
            output_text = "".join(text for text, _ in lines)
            self.discord_tab.notify_scheduler_result(name, output_text)

    def _log(self, msg: str, tag: str = None):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n", tag)
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def _log_raw(self, text: str, tag: str = None):
        self.log_text.configure(state=tk.NORMAL)
        if tag:
            self.log_text.insert(tk.END, text, tag)
        else:
            self.log_text.insert(tk.END, text)
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    # --- JSON Configuration ---

    def save_to_config(self, cm: ConfigManager):
        cm.save_scheduler_jobs(self.scheduler.jobs)

    def load_from_config(self, cm: ConfigManager):
        jobs_data = cm.get_scheduler_jobs()
        # Remove existing jobs
        self.scheduler.jobs.clear()
        for jd in jobs_data:
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
            self.scheduler.add_job(job)
        self._refresh_tree()
        self._update_status()
        if jobs_data:
            self._log(f"Loaded {len(jobs_data)} tasks from configuration", "info")


# ============================================================
#  Context Keeper - automatic context reminders
# ============================================================

_DEFAULT_CONTEXT = """=== SYSTEM CONTEXT ===
You are an autonomous assistant working in a task automation environment. \
The user uses you as a pipeline element - your responses may be \
processed automatically, cyclically, and without supervision.

Environment: {pwd}
Available tools: Python script execution, web scraper (Crawl4AI), \
task scheduler (Scheduler), external API integration.

Typical use cases:
- Data monitoring and analysis (stock market, statistics)
- Automatic checking and processing of information (emails, notifications, RSS)
- Periodic reports and summaries
- Pipelines combining scraping -> analysis -> decision -> action
- Any repetitive tasks run on schedule

Rules:
- You operate in automatic mode - respond concretely, without unnecessary preamble
- Priority: user security and privacy > correctness > speed
- Do not send user data externally without their knowledge
- Do not perform destructive operations without confirmation
- If something is unclear and you're in manual mode - ask; in auto mode - \
use safe default behavior
=== END OF CONTEXT ==="""


class ContextKeeperTab(ttk.Frame):
    """Context Keeper tab - manage context and reminders for Claude."""

    def __init__(self, parent, claude_tab: ClaudeTab):
        super().__init__(parent)
        self.claude_tab = claude_tab
        self._call_count = 0
        self._lock = threading.Lock()
        self._build_ui()
        # Global hook - injects context into EVERY ClaudeCode.ask()
        ClaudeCode.set_message_hook(self._message_hook)

    def _build_ui(self):
        # --- Active toggle (top) ---
        top_row = ttk.Frame(self)
        top_row.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))

        self.active_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top_row, text="Context Keeper active",
                        variable=self.active_var).pack(side=tk.LEFT)

        self.counter_var = tk.StringVar(value="Calls: 0")
        ttk.Label(top_row, textvariable=self.counter_var,
                  font=("monospace", 9, "italic"), foreground="#6c7086").pack(side=tk.RIGHT)

        # --- Buttons (bottom) - pack from bottom to guarantee space ---
        btn_frame = ttk.Frame(self)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))

        ttk.Button(btn_frame, text="Send context now",
                   command=self._send_now).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Reset counter",
                   command=self._reset_counter).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Restore default prompt",
                   command=self._restore_default).pack(side=tk.LEFT)

        # --- Reminder settings (bottom, above buttons) ---
        settings_frame = ttk.LabelFrame(self, text="Automatic reminders")
        settings_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=(0, 4))

        row1 = ttk.Frame(settings_frame)
        row1.pack(fill=tk.X, padx=4, pady=(4, 2))

        self.auto_first_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="Send context on first call",
                        variable=self.auto_first_var).pack(side=tk.LEFT)

        row2 = ttk.Frame(settings_frame)
        row2.pack(fill=tk.X, padx=4, pady=2)

        self.auto_every_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(row2, text="Remind recursively (on every call)",
                        variable=self.auto_every_var).pack(side=tk.LEFT)

        row3 = ttk.Frame(settings_frame)
        row3.pack(fill=tk.X, padx=4, pady=(2, 4))

        self.auto_remind_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row3, text="Remind every",
                        variable=self.auto_remind_var).pack(side=tk.LEFT)
        self.interval_var = tk.StringVar(value="100")
        ttk.Entry(row3, textvariable=self.interval_var, width=5,
                  font=("monospace", 10)).pack(side=tk.LEFT, padx=4)
        ttk.Label(row3, text="calls").pack(side=tk.LEFT)

        # --- Center: prompt + log in PanedWindow (expandable, fills remaining space) ---
        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)

        prompt_frame = ttk.LabelFrame(paned, text="Context prompt (sent to Claude)")
        paned.add(prompt_frame, weight=3)

        self.prompt_text = scrolledtext.ScrolledText(
            prompt_frame, wrap=tk.WORD, font=("monospace", 10),
            bg="#1e1e2e", fg="#cdd6f4", insertbackground="#cdd6f4",
            selectbackground="#45475a", relief=tk.FLAT, padx=6, pady=6,
        )
        self.prompt_text.pack(fill=tk.BOTH, expand=True)

        default = _DEFAULT_CONTEXT.format(pwd=os.getcwd())
        self.prompt_text.insert("1.0", default)

        log_frame = ttk.LabelFrame(paned, text="Context sending history")
        paned.add(log_frame, weight=1)

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("monospace", 9),
            bg="#11111b", fg="#cdd6f4", relief=tk.FLAT,
            padx=6, pady=6, state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_configure("info", foreground="#a6e3a1")
        self.log_text.tag_configure("remind", foreground="#f9e2af")
        self.log_text.tag_configure("status", foreground="#6c7086")

    def _message_hook(self, message: str) -> str:
        """Global hook - called by ClaudeCode.ask() from any thread."""
        with self._lock:
            call_number = self._call_count
            self._call_count += 1

        if not self.active_var.get():
            self.after(0, self._update_counter, call_number + 1)
            return message

        # Read prompt from widget (safe to read from another thread)
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        if not prompt:
            self.after(0, self._update_counter, call_number + 1)
            return message

        prefix = ""

        # First call
        if call_number == 0 and self.auto_first_var.get():
            prefix = prompt
            self.after(0, self._log, f"[#{call_number}] Sent initial context", "info")

        # Recursive mode - on every call
        elif self.auto_every_var.get() and call_number > 0:
            prefix = (
                f"[CONTEXT REMINDER - call #{call_number}]\n\n"
                f"{prompt}"
            )
            self.after(0, self._log, f"[#{call_number}] Recursive reminder", "remind")

        # Periodic reminder every N calls
        elif self.auto_remind_var.get():
            try:
                interval = int(self.interval_var.get())
            except ValueError:
                interval = 100
            if interval > 0 and call_number > 0 and call_number % interval == 0:
                prefix = (
                    f"[INITIAL CONTEXT REMINDER - call #{call_number}]\n\n"
                    f"{prompt}"
                )
                self.after(0, self._log, f"[#{call_number}] Periodic reminder (every {interval})", "remind")

        self.after(0, self._update_counter, call_number + 1)

        if prefix:
            return f"{prefix}\n\n{message}"
        return message

    def _send_now(self):
        """Manually send context to Claude."""
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("Context Keeper", "Prompt is empty.")
            return
        if self.claude_tab.claude.busy:
            messagebox.showwarning("Context Keeper", "Claude is busy, please wait.")
            return

        msg = f"[MANUAL CONTEXT - call #{self._call_count}]\n\n{prompt}"

        # Traffic listener in ClaudeTab will show the full prompt automatically
        self.claude_tab._append_text("Claude is thinking...\n", "system")
        self.claude_tab.send_btn.configure(state=tk.DISABLED)
        self.claude_tab.claude.send_chat(msg)
        self._log(f"[#{self._call_count}] Manual context sent", "info")

    def _reset_counter(self):
        with self._lock:
            self._call_count = 0
        self._update_counter(0)
        self._log("Counter reset", "status")

    def _restore_default(self):
        self.prompt_text.delete("1.0", tk.END)
        default = _DEFAULT_CONTEXT.format(pwd=os.getcwd())
        self.prompt_text.insert("1.0", default)
        self._log("Restored default prompt", "status")

    def _update_counter(self, count: int):
        self.counter_var.set(f"Calls: {count}")

    def _log(self, msg: str, tag: str = None):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n", tag)
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    # --- JSON Configuration ---

    def save_to_config(self, cm: ConfigManager):
        prompt = self.prompt_text.get("1.0", tk.END).strip()
        try:
            interval = int(self.interval_var.get())
        except ValueError:
            interval = 100
        cm.save_context_keeper(
            active=self.active_var.get(),
            prompt=prompt,
            auto_first=self.auto_first_var.get(),
            auto_every=self.auto_every_var.get(),
            auto_remind=self.auto_remind_var.get(),
            interval=interval,
        )

    def load_from_config(self, cm: ConfigManager):
        c = cm.get_context_keeper()
        self.active_var.set(c.get("active", True))
        prompt = c.get("prompt", "")
        if prompt:
            self.prompt_text.delete("1.0", tk.END)
            self.prompt_text.insert("1.0", prompt)
        self.auto_first_var.set(c.get("auto_first", True))
        self.auto_every_var.set(c.get("auto_every", False))
        self.auto_remind_var.set(c.get("auto_remind", True))
        self.interval_var.set(str(c.get("interval", 100)))


# ============================================================
#  Discord - webhook notifications
# ============================================================

class DiscordTab(ttk.Frame):
    """Discord tab - sending notifications via webhook."""

    def __init__(self, parent):
        super().__init__(parent)
        self._notifier = None  # DiscordNotifier - created dynamically
        self._build_ui()
        # Listener for Claude responses
        ClaudeCode.add_traffic_listener(self._on_claude_traffic)

    def _build_ui(self):
        # --- Configuration (top) ---
        config_frame = ttk.LabelFrame(self, text="Discord Webhook")
        config_frame.pack(side=tk.TOP, fill=tk.X, padx=4, pady=4)

        row1 = ttk.Frame(config_frame)
        row1.pack(fill=tk.X, padx=4, pady=(4, 2))

        self.active_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="Active", variable=self.active_var).pack(side=tk.LEFT)

        ttk.Label(row1, text="  URL:").pack(side=tk.LEFT)
        self.url_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.url_var, font=("monospace", 9)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4
        )
        ttk.Button(row1, text="Test", command=self._test_webhook).pack(side=tk.RIGHT)

        # --- Manual sending ---
        send_frame = ttk.LabelFrame(self, text="Send message")
        send_frame.pack(side=tk.TOP, fill=tk.X, padx=4, pady=(0, 4))

        send_row = ttk.Frame(send_frame)
        send_row.pack(fill=tk.X, padx=4, pady=4)

        self.msg_var = tk.StringVar()
        ttk.Entry(send_row, textvariable=self.msg_var, font=("monospace", 10)).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4)
        )
        ttk.Button(send_row, text="Send", command=self._send_manual).pack(side=tk.RIGHT)

        # --- Automatic notifications ---
        auto_frame = ttk.LabelFrame(self, text="Automatic notifications")
        auto_frame.pack(side=tk.TOP, fill=tk.X, padx=4, pady=(0, 4))

        self.notify_scheduler_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(auto_frame, text="Send Scheduler results to Discord",
                        variable=self.notify_scheduler_var).pack(fill=tk.X, padx=4, pady=(4, 2))

        self.notify_claude_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(auto_frame, text="Send Claude responses to Discord",
                        variable=self.notify_claude_var).pack(fill=tk.X, padx=4, pady=(2, 4))

        # --- Log (bottom, expandable) ---
        log_frame = ttk.LabelFrame(self, text="Send log")
        log_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("monospace", 9),
            bg="#11111b", fg="#cdd6f4", relief=tk.FLAT,
            padx=6, pady=6, state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.tag_configure("ok", foreground="#a6e3a1")
        self.log_text.tag_configure("error", foreground="#f38ba8")
        self.log_text.tag_configure("info", foreground="#f9e2af")

    def _get_notifier(self) -> DiscordNotifier | None:
        """Return or create DiscordNotifier based on current settings."""
        if not self.active_var.get():
            return None
        url = self.url_var.get().strip()
        if not url:
            return None
        # Process on_log to use self.after() for GUI updates
        def on_log(msg, level):
            tag = {"ok": "ok", "error": "error"}.get(level, "info")
            self.after(0, self._log, f"[{level.upper()}] {msg}", tag)
        if self._notifier is None or self._notifier.webhook_url != url:
            self._notifier = DiscordNotifier(webhook_url=url, active=True, on_log=on_log)
        self._notifier.active = True
        return self._notifier

    def send_message(self, text: str):
        """Send message to Discord. Thread-safe, can be called from any thread."""
        notifier = self._get_notifier()
        if notifier:
            notifier.send(text)

    def _test_webhook(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Discord", "Paste a Webhook URL.")
            return
        self._log("Sending test...", "info")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        notifier = self._get_notifier()
        if notifier:
            notifier.send(f"Test from Claude Code IDE [{ts}]")

    def _send_manual(self):
        msg = self.msg_var.get().strip()
        if not msg:
            return
        self.msg_var.set("")
        self.send_message(msg)

    def _on_claude_traffic(self, direction: str, text: str, meta: dict):
        """Claude traffic listener - forward responses to Discord."""
        if direction == "recv" and self.notify_claude_var.get():
            model = meta.get("model", "")
            notifier = self._get_notifier()
            if notifier:
                notifier.notify_claude(text, model)

    def notify_scheduler_result(self, job_name: str, output: str):
        """Called by Scheduler after task execution."""
        if not self.notify_scheduler_var.get():
            return
        notifier = self._get_notifier()
        if notifier:
            notifier.notify_scheduler(job_name, output)

    def _log(self, msg: str, tag: str = None):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n", tag)
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.see(tk.END)

    # --- JSON Configuration ---

    def save_to_config(self, cm: ConfigManager):
        cm.save_discord(
            active=self.active_var.get(),
            webhook_url=self.url_var.get().strip(),
            notify_scheduler=self.notify_scheduler_var.get(),
            notify_claude=self.notify_claude_var.get(),
        )

    def load_from_config(self, cm: ConfigManager):
        d = cm.get_discord()
        self.active_var.set(d.get("active", True))
        self.url_var.set(d.get("webhook_url", ""))
        self.notify_scheduler_var.set(d.get("notify_scheduler", False))
        self.notify_claude_var.set(d.get("notify_claude", False))


# ============================================================
#  Left panel with tabs
# ============================================================

class LeftPanel(ttk.Frame):
    """Left panel: Claude + Scraper + Scheduler + Context + Discord tabs."""

    def __init__(self, parent, python_panel=None):
        super().__init__(parent)
        self._python_panel = python_panel

        header = ttk.Label(self, text="Claude Code IDE", font=("monospace", 13, "bold"))
        header.pack(fill=tk.X, padx=8, pady=(8, 2))

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.claude_tab = ClaudeTab(self.notebook)
        self.notebook.add(self.claude_tab, text=" Claude ")

        self.scraper_tab = ScraperTab(self.notebook, self.claude_tab)
        self.notebook.add(self.scraper_tab, text=" Scraper ")

        self.context_tab = ContextKeeperTab(self.notebook, self.claude_tab)
        self.notebook.add(self.context_tab, text=" Context ")

        self.discord_tab = DiscordTab(self.notebook)
        self.notebook.add(self.discord_tab, text=" Discord ")

    def init_scheduler(self, python_panel):
        """Initialize the Scheduler tab (requires reference to PythonPanel)."""
        self.scheduler_tab = SchedulerTab(self.notebook, python_panel, self.discord_tab)
        self.notebook.add(self.scheduler_tab, text=" Scheduler ")


# ============================================================
#  Right panel - Python editor
# ============================================================

class PythonPanel(ttk.Frame):
    """Right panel - Python code editor and execution."""

    def __init__(self, parent):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(toolbar, text="Python Editor", font=("monospace", 14, "bold")).pack(side=tk.LEFT)

        self.run_btn = ttk.Button(toolbar, text="Run (F5)", command=self.run_code)
        self.run_btn.pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(toolbar, text="Save", command=self.save_file).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(toolbar, text="Open", command=self.open_file).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(toolbar, text="Clear", command=self.clear_output).pack(side=tk.RIGHT, padx=(4, 0))

        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        # Editor
        editor_frame = ttk.Frame(paned)
        paned.add(editor_frame, weight=3)

        editor_inner = ttk.Frame(editor_frame)
        editor_inner.pack(fill=tk.BOTH, expand=True)

        self.line_numbers = tk.Text(
            editor_inner, width=4, font=("monospace", 11),
            bg="#181825", fg="#6c7086", relief=tk.FLAT,
            state=tk.DISABLED, padx=4, pady=8,
        )
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)

        self.editor = scrolledtext.ScrolledText(
            editor_inner, wrap=tk.NONE, font=("monospace", 11),
            bg="#1e1e2e", fg="#cdd6f4", insertbackground="#cdd6f4",
            selectbackground="#45475a", relief=tk.FLAT,
            padx=8, pady=8, undo=True,
        )
        self.editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.editor.bind("<F5>", lambda e: self.run_code())
        self.editor.bind("<KeyRelease>", self._on_key_release)
        self.editor.bind("<MouseWheel>", self._sync_scroll)

        # Syntax highlighting tags
        self.editor.tag_configure("keyword", foreground="#cba6f7")
        self.editor.tag_configure("string", foreground="#a6e3a1")
        self.editor.tag_configure("comment", foreground="#6c7086")
        self.editor.tag_configure("builtin", foreground="#89b4fa")
        self.editor.tag_configure("number", foreground="#fab387")
        self.editor.tag_configure("decorator", foreground="#f9e2af")

        # Output
        output_frame = ttk.LabelFrame(paned, text="Output")
        paned.add(output_frame, weight=1)

        self.output = scrolledtext.ScrolledText(
            output_frame, wrap=tk.WORD, font=("monospace", 11),
            bg="#11111b", fg="#cdd6f4", relief=tk.FLAT,
            padx=8, pady=8, state=tk.DISABLED,
        )
        self.output.pack(fill=tk.BOTH, expand=True)
        self.output.tag_configure("error", foreground="#f38ba8")
        self.output.tag_configure("success", foreground="#a6e3a1")

        self._load_default_code()
        self._update_line_numbers()
        self._highlight_syntax()

    def _load_default_code(self):
        demo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_code.py")
        if os.path.exists(demo_path):
            with open(demo_path, "r") as f:
                self.editor.insert("1.0", f.read())
        else:
            self.editor.insert("1.0", '# Type your Python code here\nprint("Hello!")\n')

    def _on_key_release(self, event=None):
        self._update_line_numbers()
        self._highlight_syntax()

    def _update_line_numbers(self, event=None):
        self.line_numbers.configure(state=tk.NORMAL)
        self.line_numbers.delete("1.0", tk.END)
        count = int(self.editor.index("end-1c").split(".")[0])
        self.line_numbers.insert("1.0", "\n".join(str(i) for i in range(1, count + 1)))
        self.line_numbers.configure(state=tk.DISABLED)

    def _sync_scroll(self, event=None):
        self.line_numbers.yview_moveto(self.editor.yview()[0])

    def _highlight_syntax(self):
        import re
        code = self.editor.get("1.0", tk.END)
        for tag in ("keyword", "string", "comment", "builtin", "number", "decorator"):
            self.editor.tag_remove(tag, "1.0", tk.END)

        keywords = (
            r"\b(and|as|assert|async|await|break|class|continue|def|del|elif|else|"
            r"except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|"
            r"or|pass|raise|return|try|while|with|yield|True|False|None)\b"
        )
        builtins_pat = (
            r"\b(print|len|range|int|str|float|list|dict|set|tuple|type|isinstance|"
            r"enumerate|zip|map|filter|sorted|reversed|open|input|super|property)\b"
        )
        patterns = [
            ("decorator", r"@\w+"),
            ("comment", r"#[^\n]*"),
            ("string", r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"[^"\n]*"|\'[^\'\n]*\''),
            ("number", r"\b\d+\.?\d*\b"),
            ("keyword", keywords),
            ("builtin", builtins_pat),
        ]
        for tag, pattern in patterns:
            for match in re.finditer(pattern, code):
                self.editor.tag_add(tag, f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    def run_code(self):
        code = self.editor.get("1.0", tk.END).strip()
        if not code:
            return
        self.run_btn.configure(state=tk.DISABLED)
        self.clear_output()
        self._append_output("Running...\n", "success")
        self._output_queue = queue.Queue()
        self._running = True
        self._poll_output()
        threading.Thread(target=self._execute_code, args=(code,), daemon=True).start()

    def _execute_code(self, code):
        project_dir = os.path.dirname(os.path.abspath(__file__))
        if project_dir not in sys.path:
            sys.path.insert(0, project_dir)
        # Add venv to path
        venv_sp = os.path.join(project_dir, ".venv", "lib")
        if os.path.isdir(venv_sp):
            import glob as g
            for sp in g.glob(os.path.join(venv_sp, "python*", "site-packages")):
                if sp not in sys.path:
                    sys.path.insert(0, sp)

        live_stdout = LiveWriter(self._output_queue, tag="")
        live_stderr = LiveWriter(self._output_queue, tag="error")
        try:
            with redirect_stdout(live_stdout), redirect_stderr(live_stderr):
                exec(code, {"__name__": "__main__", "__builtins__": __builtins__})
        except Exception:
            self._output_queue.put((traceback.format_exc(), "error"))
        finally:
            self._output_queue.put(("__DONE__", ""))

    def _poll_output(self):
        try:
            while True:
                text, tag = self._output_queue.get_nowait()
                if text == "__DONE__":
                    self._running = False
                    self.run_btn.configure(state=tk.NORMAL)
                    return
                self._append_output(text, tag if tag else None)
        except queue.Empty:
            pass
        if self._running:
            self.after(80, self._poll_output)

    def _append_output(self, text, tag=None):
        self.output.configure(state=tk.NORMAL)
        if tag:
            self.output.insert(tk.END, text, tag)
        else:
            self.output.insert(tk.END, text)
        self.output.configure(state=tk.DISABLED)
        self.output.see(tk.END)

    def clear_output(self):
        self.output.configure(state=tk.NORMAL)
        self.output.delete("1.0", tk.END)
        self.output.configure(state=tk.DISABLED)

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[("Python", "*.py"), ("All", "*.*")])
        if path:
            with open(path, "r") as f:
                self.editor.delete("1.0", tk.END)
                self.editor.insert("1.0", f.read())
            self._update_line_numbers()
            self._highlight_syntax()

    def save_file(self):
        path = filedialog.asksaveasfilename(defaultextension=".py", filetypes=[("Python", "*.py"), ("All", "*.*")])
        if path:
            with open(path, "w") as f:
                f.write(self.editor.get("1.0", tk.END))

    def insert_text(self, text):
        """Insert text at the end of the editor."""
        self.editor.insert(tk.END, text)
        self._update_line_numbers()
        self._highlight_syntax()


# ============================================================
#  Main application
# ============================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Claude Code IDE")
        self.geometry("1500x850")
        self.minsize(1000, 550)

        # ConfigManager - default path next to scripts
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        self._config_manager = ConfigManager(config_path)

        # Dark theme
        self.configure(bg="#1e1e2e")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#1e1e2e", foreground="#cdd6f4", fieldbackground="#1e1e2e")
        style.configure("TFrame", background="#1e1e2e")
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4")
        style.configure("TButton", background="#313244", foreground="#cdd6f4")
        style.map("TButton", background=[("active", "#45475a")])
        style.configure("TLabelframe", background="#1e1e2e", foreground="#cdd6f4")
        style.configure("TLabelframe.Label", background="#1e1e2e", foreground="#cdd6f4")
        style.configure("TPanedwindow", background="#313244")
        style.configure("TNotebook", background="#1e1e2e")
        style.configure("TNotebook.Tab", background="#313244", foreground="#cdd6f4", padding=[12, 4])
        style.map("TNotebook.Tab", background=[("selected", "#45475a")])
        style.configure("TRadiobutton", background="#1e1e2e", foreground="#cdd6f4")
        style.configure("TCheckbutton", background="#1e1e2e", foreground="#cdd6f4")

        # Menu
        menubar = tk.Menu(self, bg="#313244", fg="#cdd6f4", activebackground="#45475a",
                          activeforeground="#cdd6f4")
        file_menu = tk.Menu(menubar, tearoff=0, bg="#313244", fg="#cdd6f4",
                            activebackground="#45475a", activeforeground="#cdd6f4")
        file_menu.add_command(label="Save configuration", command=self._save_config,
                              accelerator="Ctrl+Shift+S")
        file_menu.add_command(label="Load configuration", command=self._load_config,
                              accelerator="Ctrl+Shift+L")
        file_menu.add_separator()
        file_menu.add_command(label="Save configuration as...", command=self._save_config_as)
        file_menu.add_command(label="Load configuration from...", command=self._load_config_from)
        menubar.add_cascade(label="File", menu=file_menu)
        self.config(menu=menubar)

        # Layout
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        self.left_panel = LeftPanel(paned)
        paned.add(self.left_panel, weight=1)

        self.python_panel = PythonPanel(paned)
        paned.add(self.python_panel, weight=1)

        # Scheduler needs a reference to PythonPanel (to get code from editor)
        self.left_panel.init_scheduler(self.python_panel)

        # Handle "Insert into editor" from Scraper
        self.left_panel.scraper_tab.bind("<<InsertToEditor>>", self._on_insert_to_editor)

        # Shortcuts
        self.bind("<F5>", lambda e: self.python_panel.run_code())
        self.bind("<Control-s>", lambda e: self.python_panel.save_file())
        self.bind("<Control-o>", lambda e: self.python_panel.open_file())
        self.bind("<Control-Shift-S>", lambda e: self._save_config())
        self.bind("<Control-Shift-L>", lambda e: self._load_config())

        self.left_panel.claude_tab.input_entry.focus_set()

        # Auto-load config.json if it exists
        if os.path.exists(config_path):
            self._load_config(silent=True)

    def _on_insert_to_editor(self, event=None):
        content = self.left_panel.scraper_tab.result_text.get("1.0", tk.END).strip()
        if content:
            commented = "\n".join(f"# {line}" for line in content.split("\n")[:30])
            self.python_panel.insert_text(f"\n\n{commented}\n")

    def _save_config(self):
        """Save current settings to config.json."""
        cm = self._config_manager
        self.left_panel.context_tab.save_to_config(cm)
        self.left_panel.discord_tab.save_to_config(cm)
        self.left_panel.scheduler_tab.save_to_config(cm)
        messagebox.showinfo("Configuration", f"Saved to: {cm.path}")

    def _load_config(self, silent: bool = False):
        """Load settings from config.json."""
        cm = self._config_manager
        if not os.path.exists(cm.path):
            if not silent:
                messagebox.showwarning("Configuration", f"File does not exist: {cm.path}")
            return
        self.left_panel.context_tab.load_from_config(cm)
        self.left_panel.discord_tab.load_from_config(cm)
        self.left_panel.scheduler_tab.load_from_config(cm)
        if not silent:
            messagebox.showinfo("Configuration", f"Loaded from: {cm.path}")

    def _save_config_as(self):
        """Save configuration to a chosen file."""
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if path:
            cm = ConfigManager(path)
            self.left_panel.context_tab.save_to_config(cm)
            self.left_panel.discord_tab.save_to_config(cm)
            self.left_panel.scheduler_tab.save_to_config(cm)
            messagebox.showinfo("Configuration", f"Saved to: {path}")

    def _load_config_from(self):
        """Load configuration from a chosen file."""
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if path:
            cm = ConfigManager(path)
            self.left_panel.context_tab.load_from_config(cm)
            self.left_panel.discord_tab.load_from_config(cm)
            self.left_panel.scheduler_tab.load_from_config(cm)
            messagebox.showinfo("Configuration", f"Loaded from: {path}")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
