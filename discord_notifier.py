#!/usr/bin/env python3
"""DiscordNotifier - send messages to Discord without tkinter dependency."""

import json
import threading
import urllib.request
import urllib.error
from datetime import datetime


class DiscordNotifier:
    """Sends messages to Discord via webhook. No tkinter dependency."""

    def __init__(self, webhook_url: str, active: bool = True, on_log=None):
        """
        Args:
            webhook_url: Discord webhook URL.
            active: Whether notifications are enabled.
            on_log: Callback(msg, level) for logging. level: "ok", "error", "info".
        """
        self.webhook_url = webhook_url
        self.active = active
        self._on_log = on_log or (lambda msg, level: None)

    def _log(self, msg: str, level: str = "info"):
        self._on_log(msg, level)

    def send(self, text: str):
        """Send message to Discord. Thread-safe, runs in background thread."""
        if not self.active or not self.webhook_url:
            return
        threading.Thread(target=self._do_send, args=(text,), daemon=True).start()

    def send_sync(self, text: str):
        """Send message synchronously (blocks until complete)."""
        if not self.active or not self.webhook_url:
            return
        self._do_send(text)

    def _do_send(self, text: str):
        """Send HTTP POST to webhook. Splits long messages into 2000-char chunks."""
        chunks = []
        while text:
            if len(text) <= 2000:
                chunks.append(text)
                break
            cut = text[:2000].rfind("\n")
            if cut < 100:
                cut = 2000
            chunks.append(text[:cut])
            text = text[cut:].lstrip("\n")

        for i, chunk in enumerate(chunks):
            try:
                payload = json.dumps({"content": chunk}).encode("utf-8")
                req = urllib.request.Request(
                    self.webhook_url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "ClaudeCodeIDE/1.0",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = resp.status
                if len(chunks) > 1:
                    self._log(f"Sent chunk {i+1}/{len(chunks)} (HTTP {status})", "ok")
                else:
                    self._log(f"Sent (HTTP {status}): {chunk[:80]}...", "ok")
            except urllib.error.HTTPError as e:
                self._log(f"HTTP {e.code}: {e.reason}", "error")
            except Exception as e:
                self._log(f"Error: {e}", "error")

    def notify_scheduler(self, job_name: str, output: str):
        """Notify about scheduler job result."""
        ts = datetime.now().strftime("%H:%M:%S")
        msg = f"**Scheduler [{job_name}] {ts}:**\n{output[:1900]}"
        self.send(msg)

    def notify_claude(self, text: str, model: str = ""):
        """Notify about Claude response."""
        preview = text[:1900]
        self.send(f"**Claude{' (' + model + ')' if model else ''}:**\n{preview}")
