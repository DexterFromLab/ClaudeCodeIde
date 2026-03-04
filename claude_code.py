"""ClaudeCode class for communicating with the Claude Code CLI."""

import json
import os
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


def _find_claude_binary() -> str:
    """Find the best available claude CLI binary.

    Prefers ~/.local/bin/claude (user install, typically newer)
    over system-wide /usr/local/bin/claude.
    """
    user_bin = Path.home() / ".local" / "bin" / "claude"
    if user_bin.is_file() and os.access(user_bin, os.X_OK):
        return str(user_bin)
    return shutil.which("claude") or "claude"


@dataclass
class ClaudeResponse:
    """Response from Claude Code."""
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
    """Interface for communicating with Claude Code via CLI.

    Example:
        claude = ClaudeCode()
        response = claude.ask("Write a sorting function")
        print(response.text)
    """

    # Global traffic listener - every ClaudeCode instance reports here
    _traffic_listeners: list[Callable] = []
    # Global message hook - allows injecting context into every ask()
    _message_hook: Optional[Callable[[str], str]] = None

    @classmethod
    def add_traffic_listener(cls, listener: Callable):
        """Add a global traffic listener. Callback: listener(direction, text, meta).
        direction: 'send' | 'recv' | 'error'
        text: prompt or response content
        meta: dict with additional info (source, model, cost, etc.)
        """
        cls._traffic_listeners.append(listener)

    @classmethod
    def set_message_hook(cls, hook: Optional[Callable[[str], str]]):
        """Set a hook that processes every message before sending.
        hook(message) -> modified message
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
    #  Building CLI command
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
        cmd = [_find_claude_binary(), "--print", message]

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
        """Parse JSON response from claude CLI."""
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
        """Run subprocess and return ClaudeResponse."""
        # Remove CLAUDECODE env var so nested claude CLI calls are allowed
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self.working_dir,
                env=env,
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
                text=f"[Timeout after {self.timeout}s]",
                is_error=True,
            )
        except FileNotFoundError:
            return ClaudeResponse(
                text="[Command 'claude' not found. Install Claude Code CLI.]",
                is_error=True,
            )
        except Exception as e:
            return ClaudeResponse(text=f"[Error: {e}]", is_error=True)

    # ------------------------------------------------------------------ #
    #  Synchronous API
    # ------------------------------------------------------------------ #

    def ask(self, message: str, **kwargs) -> ClaudeResponse:
        """Send a question synchronously. Returns ClaudeResponse."""
        # Message hook - allows Context Keeper to inject context
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
        """Like ask(), but automatically continues the session (context memory)."""
        kwargs.setdefault("continue_session", True)
        return self.ask(message, **kwargs)

    def generate_code(self, prompt: str, language: str = "python", **kwargs) -> str:
        """Generate code in a given language. Returns only the code (no markdown)."""
        full_prompt = (
            f"Generate ONLY {language} code, no comments, "
            f"no markdown blocks, no explanations. Just clean code:\n\n{prompt}"
        )
        kwargs.setdefault("system_prompt", "You are a code generator. Return ONLY code, without markdown formatting.")
        resp = self.ask(full_prompt, **kwargs)
        code = resp.text.strip()
        # Remove markdown blocks if Claude added them anyway
        if code.startswith("```"):
            lines = code.split("\n")
            lines = lines[1:]  # remove ```python
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)
        return code

    def review_code(self, code: str, **kwargs) -> ClaudeResponse:
        """Submit code for review."""
        prompt = (
            "Review the following code. Point out:\n"
            "- Bugs and errors\n"
            "- Performance issues\n"
            "- Best practice violations\n"
            "- Improvement suggestions\n\n"
            f"```python\n{code}\n```"
        )
        return self.ask(prompt, **kwargs)

    def fix_code(self, code: str, error: str, **kwargs) -> str:
        """Fix code based on an error. Returns the corrected code."""
        prompt = (
            f"The following Python code produces an error. Fix it and return ONLY the corrected code, "
            f"no explanations, no markdown.\n\n"
            f"CODE:\n{code}\n\n"
            f"ERROR:\n{error}"
        )
        kwargs.setdefault("system_prompt", "You fix code. Return ONLY the corrected code, without markdown formatting.")
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
        """Explain what a piece of code does."""
        prompt = f"Explain step by step what the following code does:\n\n```python\n{code}\n```"
        return self.ask(prompt, **kwargs)

    def ask_structured(self, message: str, schema: dict, **kwargs) -> dict:
        """Ask a question and get a JSON-formatted response matching the schema."""
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
        """Start a new session (clear session ID and history)."""
        self._session_id = None
        self._history.clear()

    # ------------------------------------------------------------------ #
    #  Asynchronous API (callback)
    # ------------------------------------------------------------------ #

    def send(self, message: str, **kwargs):
        """Send message asynchronously (in a thread). Result via on_response callback."""
        if self._busy:
            return
        self._busy = True
        thread = threading.Thread(
            target=self._async_query, args=(message,), kwargs=kwargs, daemon=True
        )
        thread.start()

    def send_chat(self, message: str, **kwargs):
        """Like send(), but continues the session."""
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
    #  Utility methods
    # ------------------------------------------------------------------ #

    def batch(self, prompts: list[str], **kwargs) -> list[ClaudeResponse]:
        """Execute a list of prompts sequentially. Returns list of responses."""
        results = []
        for prompt in prompts:
            results.append(self.ask(prompt, **kwargs))
        return results

    def batch_parallel(
        self, prompts: list[str], max_workers: int = 3, **kwargs
    ) -> list[ClaudeResponse]:
        """Execute a list of prompts in parallel (max_workers at a time)."""
        from concurrent.futures import ThreadPoolExecutor

        def run_one(prompt):
            cmd = self._build_cmd(prompt, **kwargs)
            return self._run_subprocess(cmd)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(run_one, prompts))
        return results

    def pipe(self, code: str, instruction: str, iterations: int = 1, **kwargs) -> str:
        """Iteratively process code according to instructions (e.g., step-by-step refactoring)."""
        current = code
        for i in range(iterations):
            prompt = f"{instruction}\n\nCurrent code:\n```python\n{current}\n```\n\nReturn ONLY the modified code."
            kwargs_copy = dict(kwargs)
            kwargs_copy.setdefault(
                "system_prompt", "You modify code according to instructions. Return ONLY code without markdown."
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
    #  Scraper integration (Crawl4AI - 100% local)
    # ------------------------------------------------------------------ #

    def scrape_and_ask(self, url: str, question: str, **kwargs) -> ClaudeResponse:
        """Scrape a page locally and ask Claude a question about its content."""
        from scraper import Scraper
        sc = Scraper()
        result = sc.scrape(url)
        if result.is_error:
            return ClaudeResponse(text=f"[Scraping error {url}: {result.error_msg}]", is_error=True)
        prompt = (
            f"Below is the content of the page {url}:\n\n"
            f"---\n{result.markdown[:15000]}\n---\n\n"
            f"Question: {question}"
        )
        return self.ask(prompt, **kwargs)

    def scrape_and_summarize(self, url: str, **kwargs) -> ClaudeResponse:
        """Scrape a page and create a summary."""
        return self.scrape_and_ask(url, "Create a concise summary of this page.", **kwargs)

    def scrape_many_and_ask(self, urls: list[str], question: str, **kwargs) -> ClaudeResponse:
        """Scrape multiple pages and ask a question about their content."""
        from scraper import Scraper
        sc = Scraper()
        results = sc.scrape_many(urls)

        scraped_content = []
        for r in results:
            if not r.is_error and r.markdown:
                scraped_content.append(
                    f"## Source: {r.title or r.url}\nURL: {r.url}\n\n"
                    f"{r.markdown[:5000]}\n"
                )

        if not scraped_content:
            return ClaudeResponse(text="[Failed to scrape any pages]", is_error=True)

        all_content = "\n---\n".join(scraped_content)
        prompt = f"{all_content}\n\n---\n\nQuestion: {question}"
        return self.ask(prompt, **kwargs)
