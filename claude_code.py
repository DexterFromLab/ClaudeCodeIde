"""Klasa ClaudeCode do komunikacji z Claude Code CLI."""

import json
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ClaudeResponse:
    """Odpowiedz od Claude Code."""
    text: str
    raw_json: Optional[dict] = None
    session_id: Optional[str] = None
    model: Optional[str] = None
    cost_usd: Optional[float] = None
    duration_ms: Optional[float] = None
    is_error: bool = False

    def __str__(self):
        return self.text


class ClaudeCode:
    """Interfejs do komunikacji z Claude Code przez CLI.

    Przyklad uzycia:
        claude = ClaudeCode()
        odpowiedz = claude.ask("Napisz funkcje sortujaca")
        print(odpowiedz.text)
    """

    # Globalny listener ruchu - kazda instancja ClaudeCode raportuje tu komunikacje
    _traffic_listeners: list[Callable] = []
    # Globalny hook na wiadomosci - pozwala wstrzykiwac kontekst do kazdego ask()
    _message_hook: Optional[Callable[[str], str]] = None

    @classmethod
    def add_traffic_listener(cls, listener: Callable):
        """Dodaj globalny listener ruchu. Callback: listener(direction, text, meta).
        direction: 'send' | 'recv' | 'error'
        text: tresc promptu lub odpowiedzi
        meta: dict z dodatkowymi info (source, model, cost, etc.)
        """
        cls._traffic_listeners.append(listener)

    @classmethod
    def set_message_hook(cls, hook: Optional[Callable[[str], str]]):
        """Ustaw hook przetwarzajacy kazdy message przed wyslaniem.
        hook(message) -> zmodyfikowany message
        """
        cls._message_hook = hook

    @classmethod
    def _notify_traffic(cls, direction: str, text: str, meta: dict = None):
        for listener in cls._traffic_listeners:
            try:
                listener(direction, text, meta or {})
            except Exception:
                pass

    def __init__(
        self,
        on_response: Optional[Callable[[ClaudeResponse], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        working_dir: Optional[str] = None,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        timeout: int = 180,
        allowed_tools: Optional[list[str]] = None,
        max_budget_usd: Optional[float] = None,
    ):
        self.on_response = on_response
        self.on_error = on_error
        self.working_dir = working_dir
        self.model = model
        self.system_prompt = system_prompt
        self.timeout = timeout
        self.allowed_tools = allowed_tools
        self.max_budget_usd = max_budget_usd
        self._busy = False
        self._session_id: Optional[str] = None
        self._history: list[dict] = []

    @property
    def busy(self):
        return self._busy

    @property
    def session_id(self):
        return self._session_id

    @property
    def history(self):
        return list(self._history)

    # ------------------------------------------------------------------ #
    #  Budowanie komendy CLI
    # ------------------------------------------------------------------ #

    def _build_cmd(
        self,
        message: str,
        *,
        output_format: str = "json",
        continue_session: bool = False,
        resume_session: Optional[str] = None,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        json_schema: Optional[dict] = None,
        allowed_tools: Optional[list[str]] = None,
        max_budget_usd: Optional[float] = None,
    ) -> list[str]:
        cmd = ["claude", "--print", message]

        fmt = output_format
        cmd += ["--output-format", fmt]

        m = model or self.model
        if m:
            cmd += ["--model", m]

        sp = system_prompt or self.system_prompt
        if sp:
            cmd += ["--system-prompt", sp]

        tools = allowed_tools or self.allowed_tools
        if tools:
            cmd += ["--allowedTools"] + tools

        budget = max_budget_usd or self.max_budget_usd
        if budget is not None:
            cmd += ["--max-budget-usd", str(budget)]

        if json_schema:
            cmd += ["--json-schema", json.dumps(json_schema)]

        if resume_session:
            cmd += ["--resume", resume_session]
        elif continue_session and self._session_id:
            cmd += ["--resume", self._session_id]

        return cmd

    def _parse_json_response(self, stdout: str) -> ClaudeResponse:
        """Parsuj odpowiedz JSON z claude CLI."""
        try:
            data = json.loads(stdout)
            text = data.get("result", stdout)
            return ClaudeResponse(
                text=text,
                raw_json=data,
                session_id=data.get("session_id"),
                model=data.get("model"),
                cost_usd=data.get("cost_usd"),
                duration_ms=data.get("duration_ms"),
            )
        except json.JSONDecodeError:
            return ClaudeResponse(text=stdout.strip())

    def _run_subprocess(self, cmd: list[str]) -> ClaudeResponse:
        """Uruchom subprocess i zwroc ClaudeResponse."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.working_dir,
            )
            if result.returncode != 0 and result.stderr.strip():
                return ClaudeResponse(
                    text=result.stderr.strip(),
                    is_error=True,
                )
            response = self._parse_json_response(result.stdout)
            if response.session_id:
                self._session_id = response.session_id
            return response
        except subprocess.TimeoutExpired:
            return ClaudeResponse(
                text=f"[Timeout po {self.timeout}s]",
                is_error=True,
            )
        except FileNotFoundError:
            return ClaudeResponse(
                text="[Nie znaleziono komendy 'claude'. Zainstaluj Claude Code CLI.]",
                is_error=True,
            )
        except Exception as e:
            return ClaudeResponse(text=f"[Blad: {e}]", is_error=True)

    # ------------------------------------------------------------------ #
    #  API synchroniczne
    # ------------------------------------------------------------------ #

    def ask(self, message: str, **kwargs) -> ClaudeResponse:
        """Wyslij pytanie synchronicznie. Zwraca ClaudeResponse."""
        # Message hook - pozwala Context Keeper wstrzykiwac kontekst
        if ClaudeCode._message_hook:
            message = ClaudeCode._message_hook(message)
        self._notify_traffic("send", message, {
            "system_prompt": kwargs.get("system_prompt") or self.system_prompt,
        })
        cmd = self._build_cmd(message, **kwargs)
        response = self._run_subprocess(cmd)
        if response.is_error:
            self._notify_traffic("error", response.text, {
                "model": response.model,
            })
        else:
            self._notify_traffic("recv", response.text, {
                "model": response.model,
                "cost_usd": response.cost_usd,
                "duration_ms": response.duration_ms,
            })
        self._history.append({"role": "user", "content": message})
        self._history.append({"role": "assistant", "content": response.text})
        return response

    def chat(self, message: str, **kwargs) -> ClaudeResponse:
        """Jak ask(), ale automatycznie kontynuuje sesje (pamiec kontekstu)."""
        kwargs.setdefault("continue_session", True)
        return self.ask(message, **kwargs)

    def generate_code(self, prompt: str, language: str = "python", **kwargs) -> str:
        """Wygeneruj kod w danym jezyku. Zwraca sam kod (bez markdown)."""
        full_prompt = (
            f"Wygeneruj TYLKO kod {language}, bez zadnych komentarzy, "
            f"bez blokow markdown, bez wyjasnien. Samo czysty kod:\n\n{prompt}"
        )
        kwargs.setdefault("system_prompt", "Jestes generatorem kodu. Zwracasz TYLKO kod, bez formatowania markdown.")
        resp = self.ask(full_prompt, **kwargs)
        code = resp.text.strip()
        # Usun bloki markdown jesli Claude i tak je dodal
        if code.startswith("```"):
            lines = code.split("\n")
            lines = lines[1:]  # usun ```python
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)
        return code

    def review_code(self, code: str, **kwargs) -> ClaudeResponse:
        """Przeslij kod do code review."""
        prompt = (
            "Zrob code review ponizszego kodu. Wskazywaj:\n"
            "- Bledy i bugi\n"
            "- Problemy z wydajnoscia\n"
            "- Naruszenia dobrych praktyk\n"
            "- Sugestie poprawek\n\n"
            f"```python\n{code}\n```"
        )
        return self.ask(prompt, **kwargs)

    def fix_code(self, code: str, error: str, **kwargs) -> str:
        """Napraw kod na podstawie bledu. Zwraca poprawiony kod."""
        prompt = (
            f"Ponizszy kod Python zwraca blad. Napraw go i zwroc TYLKO poprawiony kod, "
            f"bez wyjasnien, bez markdown.\n\n"
            f"KOD:\n{code}\n\n"
            f"BLAD:\n{error}"
        )
        kwargs.setdefault("system_prompt", "Naprawiasz kod. Zwracasz TYLKO poprawiony kod, bez formatowania markdown.")
        resp = self.ask(prompt, **kwargs)
        fixed = resp.text.strip()
        if fixed.startswith("```"):
            lines = fixed.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            fixed = "\n".join(lines)
        return fixed

    def explain_code(self, code: str, **kwargs) -> ClaudeResponse:
        """Wyjasni co robi dany kod."""
        prompt = f"Wyjasni krok po kroku co robi ponizszy kod:\n\n```python\n{code}\n```"
        return self.ask(prompt, **kwargs)

    def ask_structured(self, message: str, schema: dict, **kwargs) -> dict:
        """Zadaj pytanie i uzyskaj odpowiedz w formacie JSON wg schematu."""
        resp = self.ask(message, json_schema=schema, **kwargs)
        if resp.raw_json and "result" in resp.raw_json:
            try:
                return json.loads(resp.raw_json["result"])
            except (json.JSONDecodeError, TypeError):
                pass
        try:
            return json.loads(resp.text)
        except json.JSONDecodeError:
            return {"raw_text": resp.text}

    def new_session(self):
        """Zacznij nowa sesje (wyczysc ID sesji i historie)."""
        self._session_id = None
        self._history.clear()

    # ------------------------------------------------------------------ #
    #  API asynchroniczne (callback)
    # ------------------------------------------------------------------ #

    def send(self, message: str, **kwargs):
        """Wyslij wiadomosc asynchronicznie (w watku). Wynik przez on_response callback."""
        if self._busy:
            return
        self._busy = True
        thread = threading.Thread(
            target=self._async_query, args=(message,), kwargs=kwargs, daemon=True
        )
        thread.start()

    def send_chat(self, message: str, **kwargs):
        """Jak send(), ale kontynuuje sesje."""
        kwargs.setdefault("continue_session", True)
        self.send(message, **kwargs)

    def _async_query(self, message: str, **kwargs):
        try:
            response = self.ask(message, **kwargs)
            if response.is_error:
                if self.on_error:
                    self.on_error(response.text)
                elif self.on_response:
                    self.on_response(response)
            elif self.on_response:
                self.on_response(response)
        except Exception as e:
            if self.on_error:
                self.on_error(str(e))
        finally:
            self._busy = False

    # ------------------------------------------------------------------ #
    #  Narzedzia pomocnicze
    # ------------------------------------------------------------------ #

    def batch(self, prompts: list[str], **kwargs) -> list[ClaudeResponse]:
        """Wykonaj liste promptow sekwencyjnie. Zwraca liste odpowiedzi."""
        results = []
        for prompt in prompts:
            results.append(self.ask(prompt, **kwargs))
        return results

    def batch_parallel(
        self, prompts: list[str], max_workers: int = 3, **kwargs
    ) -> list[ClaudeResponse]:
        """Wykonaj liste promptow rownolegle (max_workers na raz)."""
        from concurrent.futures import ThreadPoolExecutor

        def run_one(prompt):
            cmd = self._build_cmd(prompt, **kwargs)
            return self._run_subprocess(cmd)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(run_one, prompts))
        return results

    def pipe(self, code: str, instruction: str, iterations: int = 1, **kwargs) -> str:
        """Iteracyjnie przetwarzaj kod wg instrukcji (np. refaktoryzacja w krokach)."""
        current = code
        for i in range(iterations):
            prompt = f"{instruction}\n\nAktualny kod:\n```python\n{current}\n```\n\nZwroc TYLKO poprawiony kod."
            kwargs_copy = dict(kwargs)
            kwargs_copy.setdefault(
                "system_prompt", "Modyfikujesz kod wg instrukcji. Zwracasz TYLKO kod bez markdown."
            )
            resp = self.ask(prompt, **kwargs_copy)
            result = resp.text.strip()
            if result.startswith("```"):
                lines = result.split("\n")[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                result = "\n".join(lines)
            current = result
        return current

    # ------------------------------------------------------------------ #
    #  Integracja ze Scraperem (Crawl4AI - 100% lokalne)
    # ------------------------------------------------------------------ #

    def scrape_and_ask(self, url: str, question: str, **kwargs) -> ClaudeResponse:
        """Scrapuj strone lokalnie i zadaj pytanie Claude o jej tresc."""
        from scraper import Scraper
        sc = Scraper()
        result = sc.scrape(url)
        if result.is_error:
            return ClaudeResponse(text=f"[Blad scrapowania {url}: {result.error_msg}]", is_error=True)
        prompt = (
            f"Ponizej znajduje sie tresc strony {url}:\n\n"
            f"---\n{result.markdown[:15000]}\n---\n\n"
            f"Pytanie: {question}"
        )
        return self.ask(prompt, **kwargs)

    def scrape_and_summarize(self, url: str, **kwargs) -> ClaudeResponse:
        """Scrapuj strone i stworz streszczenie."""
        return self.scrape_and_ask(url, "Stworz zwiezle streszczenie tej strony po polsku.", **kwargs)

    def scrape_many_and_ask(self, urls: list[str], question: str, **kwargs) -> ClaudeResponse:
        """Scrapuj wiele stron i zadaj pytanie o ich tresc."""
        from scraper import Scraper
        sc = Scraper()
        results = sc.scrape_many(urls)

        scraped_content = []
        for r in results:
            if not r.is_error and r.markdown:
                scraped_content.append(
                    f"## Zrodlo: {r.title or r.url}\nURL: {r.url}\n\n"
                    f"{r.markdown[:5000]}\n"
                )

        if not scraped_content:
            return ClaudeResponse(text="[Nie udalo sie scrapowac zadnych stron]", is_error=True)

        all_content = "\n---\n".join(scraped_content)
        prompt = f"{all_content}\n\n---\n\nPytanie: {question}"
        return self.ask(prompt, **kwargs)
