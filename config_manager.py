#!/usr/bin/env python3
"""ConfigManager - zapis/odczyt ustawien IDE do/z pliku JSON."""

import json
import os


_DEFAULT_CONFIG = {
    "context_keeper": {
        "active": True,
        "prompt": "",
        "auto_first": True,
        "auto_every": False,
        "auto_remind": True,
        "interval": 100,
    },
    "discord": {
        "active": True,
        "webhook_url": "",
        "notify_scheduler": False,
        "notify_claude": False,
    },
    "scheduler_jobs": [],
}


class ConfigManager:
    """Prosty wrapper na json.load/json.dump do zapisu ustawien IDE."""

    def __init__(self, path: str = "config.json"):
        self.path = path

    def load(self) -> dict:
        """Wczytaj konfiguracje z pliku. Zwraca domyslna jesli plik nie istnieje."""
        if not os.path.exists(self.path):
            return dict(_DEFAULT_CONFIG)
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Uzupelnij brakujace sekcje domyslnymi wartosciami
        for key, default in _DEFAULT_CONFIG.items():
            if key not in data:
                data[key] = default
        return data

    def save(self, data: dict):
        """Zapisz cala konfiguracje do pliku JSON."""
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # --- Sekcja: Context Keeper ---

    def save_context_keeper(self, active: bool, prompt: str, auto_first: bool,
                            auto_every: bool, auto_remind: bool, interval: int):
        data = self.load()
        data["context_keeper"] = {
            "active": active,
            "prompt": prompt,
            "auto_first": auto_first,
            "auto_every": auto_every,
            "auto_remind": auto_remind,
            "interval": interval,
        }
        self.save(data)

    def get_context_keeper(self) -> dict:
        return self.load().get("context_keeper", _DEFAULT_CONFIG["context_keeper"])

    # --- Sekcja: Discord ---

    def save_discord(self, active: bool, webhook_url: str,
                     notify_scheduler: bool, notify_claude: bool):
        data = self.load()
        data["discord"] = {
            "active": active,
            "webhook_url": webhook_url,
            "notify_scheduler": notify_scheduler,
            "notify_claude": notify_claude,
        }
        self.save(data)

    def get_discord(self) -> dict:
        return self.load().get("discord", _DEFAULT_CONFIG["discord"])

    # --- Sekcja: Scheduler Jobs ---

    def save_scheduler_jobs(self, jobs: list):
        """Zapisz liste jobow. Przyjmuje liste ScheduledJob lub list[dict]."""
        data = self.load()
        serialized = []
        for job in jobs:
            if hasattr(job, "name"):
                # ScheduledJob dataclass
                serialized.append({
                    "name": job.name,
                    "code": job.code,
                    "mode": job.mode,
                    "time_str": job.time_str,
                    "date_str": job.date_str,
                    "interval_min": job.interval_min,
                    "weekdays": list(job.weekdays),
                    "active": job.active,
                })
            else:
                # Juz dict
                serialized.append(job)
        data["scheduler_jobs"] = serialized
        self.save(data)

    def get_scheduler_jobs(self) -> list[dict]:
        return self.load().get("scheduler_jobs", [])
