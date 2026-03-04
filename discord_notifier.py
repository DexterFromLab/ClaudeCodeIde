#!/usr/bin/env python3
"""DiscordNotifier - logika wysylania wiadomosci na Discord bez tkinter."""

import json
import threading
import urllib.request
import urllib.error
from datetime import datetime


class DiscordNotifier:
    """Wysyla wiadomosci na Discord przez webhook. Bez zaleznosci od tkinter."""

    def __init__(self, webhook_url: str, active: bool = True, on_log=None):
        """
        Args:
            webhook_url: URL webhooka Discord.
            active: Czy notyfikacje sa wlaczone.
            on_log: Callback(msg, level) do logowania. level: "ok", "error", "info".
        """
        self.webhook_url = webhook_url
        self.active = active
        self._on_log = on_log or (lambda msg, level: None)

    def _log(self, msg: str, level: str = "info"):
        self._on_log(msg, level)

    def send(self, text: str):
        """Wyslij wiadomosc na Discord. Thread-safe, uruchamia watek w tle."""
        if not self.active or not self.webhook_url:
            return
        threading.Thread(target=self._do_send, args=(text,), daemon=True).start()

    def send_sync(self, text: str):
        """Wyslij wiadomosc synchronicznie (blokuje do zakonczenia)."""
        if not self.active or not self.webhook_url:
            return
        self._do_send(text)

    def _do_send(self, text: str):
        """Wysyla HTTP POST na webhook. Dzieli dlugie wiadomosci na chunki po 2000 znakow."""
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
        """Powiadom o wyniku schedulera."""
        ts = datetime.now().strftime("%H:%M:%S")
        msg = f"**Scheduler [{job_name}] {ts}:**\n{output[:1900]}"
        self.send(msg)

    def notify_claude(self, text: str, model: str = ""):
        """Powiadom o odpowiedzi Claude."""
        preview = text[:1900]
        self.send(f"**Claude{' (' + model + ')' if model else ''}:**\n{preview}")
