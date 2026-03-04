#!/usr/bin/env python3
"""
Rozbudowany przyklad uzycia klasy ClaudeCode.

Pokazuje rozne scenariusze pracy z Claude Code CLI z poziomu Pythona:
  1. Proste pytania i odpowiedzi
  2. Rozmowa z pamiecia kontekstu (sesja)
  3. Generowanie kodu
  4. Code review
  5. Automatyczne naprawianie bledow
  6. Pipeline: generuj -> uruchom -> napraw
  7. Zapytania rownolegle (batch)
  8. Structured output (JSON schema)
  9. Iteracyjna refaktoryzacja
 10. Asystent do nauki

Uruchom calosc:
    python3 examples.py

Lub zaimportuj i uzyj wybranych funkcji:
    from examples import demo_generate_and_run
    demo_generate_and_run()
"""

import io
import sys
import time
import traceback
from contextlib import redirect_stdout, redirect_stderr

from claude_code import ClaudeCode, ClaudeResponse


# ============================================================
# Pomocnicze funkcje
# ============================================================

def header(title: str):
    """Wyswietl naglowek sekcji."""
    w = 60
    print("\n" + "=" * w)
    print(f"  {title}")
    print("=" * w + "\n")


def run_python(code: str) -> tuple[str, str]:
    """Wykonaj kod Pythona i zwroc (stdout, error)."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(code, {"__name__": "__main__", "__builtins__": __builtins__})
        return stdout_buf.getvalue(), ""
    except Exception:
        return stdout_buf.getvalue(), traceback.format_exc()


def print_response(resp: ClaudeResponse):
    """Ladnie wyswietl odpowiedz Claude."""
    print(f"Claude: {resp.text}")
    if resp.model:
        print(f"  [model: {resp.model}]")
    if resp.cost_usd:
        print(f"  [koszt: ${resp.cost_usd:.4f}]")
    if resp.duration_ms:
        print(f"  [czas: {resp.duration_ms:.0f}ms]")
    print()


# ============================================================
# 1. Proste pytanie
# ============================================================

def demo_simple_question():
    """Zadaj proste pytanie i wyswietl odpowiedz."""
    header("1. Proste pytanie")

    claude = ClaudeCode()
    resp = claude.ask("Czym jest list comprehension w Pythonie? Odpowiedz w 2-3 zdaniach.")
    print_response(resp)


# ============================================================
# 2. Rozmowa z pamiecia kontekstu
# ============================================================

def demo_conversation():
    """Rozmowa wieloetapowa - Claude pamięta kontekst."""
    header("2. Rozmowa z pamiecia kontekstu (sesja)")

    claude = ClaudeCode()

    print(">> Pytanie 1:")
    r1 = claude.chat("Wymysl prosta klase Python reprezentujaca Samochod z polami: marka, model, rok. Odpowiedz krotko.")
    print_response(r1)

    print(">> Pytanie 2 (kontynuacja - Claude pamięta klase):")
    r2 = claude.chat("Dodaj do tej klasy metode wiek() ktora zwraca ile lat ma samochod. Odpowiedz krotko.")
    print_response(r2)

    print(">> Pytanie 3 (kontynuacja):")
    r3 = claude.chat("Teraz dodaj __repr__. Odpowiedz krotko.")
    print_response(r3)

    print(f"Sesja ID: {claude.session_id}")
    print(f"Historia ({len(claude.history)} wiadomosci)")
    claude.new_session()


# ============================================================
# 3. Generowanie kodu
# ============================================================

def demo_generate_code():
    """Claude generuje czysty kod bez markdown."""
    header("3. Generowanie kodu")

    claude = ClaudeCode()

    prompts = [
        "Funkcje fibonacci(n) zwracajaca n-ty wyraz ciagu Fibonacciego (iteracyjnie)",
        "Dekorator @timer ktory mierzy czas wykonania funkcji i printuje wynik",
        "Context manager TempDir ktory tworzy tymczasowy katalog i usuwa go po wyjsciu",
    ]

    for i, prompt in enumerate(prompts, 1):
        print(f"--- Generowanie {i}: {prompt[:50]}... ---")
        code = claude.generate_code(prompt)
        print(code)
        print()


# ============================================================
# 4. Code review
# ============================================================

def demo_code_review():
    """Wyslij kod do review przez Claude."""
    header("4. Code review")

    claude = ClaudeCode()

    bad_code = '''\
import os

def read_data(path):
    f = open(path)
    data = f.read()
    result = eval(data)
    return result

def process(items):
    output = []
    for i in range(len(items)):
        if items[i] != None:
            output.append(items[i] * 2)
    return output

class db:
    def __init__(self):
        self.conn = None
    def query(self, sql):
        import sqlite3
        self.conn = sqlite3.connect("app.db")
        return self.conn.execute(sql).fetchall()
'''

    print("Kod do review:")
    print(bad_code)
    print("--- Review od Claude: ---")

    resp = claude.review_code(bad_code)
    print_response(resp)


# ============================================================
# 5. Automatyczne naprawianie bledow
# ============================================================

def demo_fix_errors():
    """Claude naprawia kod ktory powoduje blad."""
    header("5. Automatyczne naprawianie bledow")

    claude = ClaudeCode()

    buggy_code = '''\
def merge_dicts(a, b):
    """Polacz dwa slowniki, wartosci z b nadpisuja a."""
    result = a.copy
    for k, v in b:
        result[k] = v
    return result

data = merge_dicts({"a": 1, "b": 2}, {"b": 3, "c": 4})
print(f"Wynik: {data}")
'''

    print("Oryginalny kod (z bledami):")
    print(buggy_code)

    stdout, error = run_python(buggy_code)
    print(f"Blad przy uruchomieniu:\n{error}")

    print("--- Naprawianie przez Claude... ---")
    fixed = claude.fix_code(buggy_code, error)
    print("Naprawiony kod:")
    print(fixed)
    print()

    stdout2, error2 = run_python(fixed)
    if error2:
        print(f"Nadal jest blad: {error2}")
    else:
        print(f"Wynik po naprawie: {stdout2}")


# ============================================================
# 6. Pipeline: generuj -> uruchom -> napraw
# ============================================================

def demo_pipeline():
    """Pelny pipeline: generuj kod, uruchom, napraw jesli trzeba."""
    header("6. Pipeline: generuj -> uruchom -> napraw")

    claude = ClaudeCode()
    task = (
        "Napisz funkcje analyze_text(text) ktora zwraca slownik z kluczami: "
        "'words' (liczba slow), 'chars' (liczba znakow), 'lines' (liczba linii), "
        "'most_common' (najczesciej wystepujace slowo). "
        "Na koncu wywolaj ja z przykladowym tekstem i wyswietl wynik."
    )

    print(f"Zadanie: {task}\n")
    code = claude.generate_code(task)
    print("Wygenerowany kod:")
    print(code)
    print()

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        print(f"--- Proba uruchomienia {attempt}/{max_attempts} ---")
        stdout, error = run_python(code)

        if not error:
            print(f"Sukces! Wynik:\n{stdout}")
            return
        else:
            print(f"Blad:\n{error}")
            if attempt < max_attempts:
                print("Naprawiam...")
                code = claude.fix_code(code, error)
                print(f"Poprawiony kod:\n{code}\n")

    print("Nie udalo sie naprawic kodu po 3 probach.")


# ============================================================
# 7. Zapytania rownolegle (batch)
# ============================================================

def demo_batch():
    """Wyslij wiele pytan na raz (rownolegle)."""
    header("7. Zapytania rownolegle (batch)")

    claude = ClaudeCode()

    questions = [
        "W jednym zdaniu: co to jest dekorator w Pythonie?",
        "W jednym zdaniu: co to jest generator w Pythonie?",
        "W jednym zdaniu: co to jest context manager w Pythonie?",
        "W jednym zdaniu: co to jest metaclass w Pythonie?",
    ]

    print(f"Wysylam {len(questions)} pytan rownolegle...\n")
    t0 = time.time()
    results = claude.batch_parallel(questions, max_workers=4)
    elapsed = time.time() - t0

    for q, r in zip(questions, results):
        print(f"Q: {q}")
        print(f"A: {r.text}\n")

    print(f"Czas laczny: {elapsed:.1f}s (rownolegle)")


# ============================================================
# 8. Structured output (JSON schema)
# ============================================================

def demo_structured():
    """Uzyskaj odpowiedz w scislym formacie JSON."""
    header("8. Structured output (JSON schema)")

    claude = ClaudeCode()

    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Nazwa biblioteki"},
            "category": {
                "type": "string",
                "enum": ["web", "data", "ml", "cli", "testing", "other"],
            },
            "description": {"type": "string", "description": "Krotki opis (1 zdanie)"},
            "difficulty": {
                "type": "string",
                "enum": ["beginner", "intermediate", "advanced"],
            },
        },
        "required": ["name", "category", "description", "difficulty"],
    }

    prompt = "Opisz biblioteke FastAPI w formacie JSON zgodnym ze schematem."
    print(f"Prompt: {prompt}")
    print(f"Schema: {schema}\n")

    result = claude.ask_structured(prompt, schema)
    print(f"Wynik (dict): {result}")
    print()

    if isinstance(result, dict) and "name" in result:
        print(f"  Nazwa:       {result.get('name')}")
        print(f"  Kategoria:   {result.get('category')}")
        print(f"  Opis:        {result.get('description')}")
        print(f"  Trudnosc:    {result.get('difficulty')}")


# ============================================================
# 9. Iteracyjna refaktoryzacja (pipe)
# ============================================================

def demo_refactor():
    """Iteracyjnie ulepszaj kod w kilku krokach."""
    header("9. Iteracyjna refaktoryzacja")

    claude = ClaudeCode()

    starter_code = '''\
def f(l):
    r = []
    for i in l:
        if i > 0:
            r.append(i * i)
    return r

data = [3, -1, 4, -1, 5, 9, -2, 6]
print(f(data))
'''

    print("Oryginalny kod:")
    print(starter_code)

    steps = [
        "Zmien nazwy zmiennych na opisowe (nie uzywaj jednoliterowych nazw)",
        "Zamien petle na list comprehension tam gdzie to mozliwe",
        "Dodaj type hints do sygnatury funkcji",
    ]

    current = starter_code
    for i, step in enumerate(steps, 1):
        print(f"--- Krok {i}: {step} ---")
        current = claude.pipe(current, step)
        print(current)
        print()

    print("Weryfikacja - uruchamiam koncowy kod:")
    stdout, error = run_python(current)
    if error:
        print(f"Blad: {error}")
    else:
        print(f"Wynik: {stdout}")


# ============================================================
# 10. Asystent do nauki
# ============================================================

def demo_tutor():
    """Claude jako tutor - wyjasnij kod krok po kroku."""
    header("10. Asystent do nauki")

    claude = ClaudeCode()

    mystery_code = '''\
from functools import reduce

def compose(*fns):
    return reduce(lambda f, g: lambda *a, **kw: f(g(*a, **kw)), fns)

pipeline = compose(
    lambda x: x ** 2,
    lambda x: x + 3,
    lambda x: x * 2,
)

print(pipeline(5))
'''

    print("Kod do wyjasnienia:")
    print(mystery_code)

    resp = claude.explain_code(mystery_code)
    print("--- Wyjasnienie od Claude: ---")
    print_response(resp)

    stdout, _ = run_python(mystery_code)
    print(f"Rzeczywisty wynik kodu: {stdout}")


# ============================================================
# 11. Multi-model porownanie
# ============================================================

def demo_multi_model():
    """Porownaj odpowiedzi roznych modeli Claude."""
    header("11. Porownanie modeli")

    models = ["haiku", "sonnet"]
    question = "Napisz jednoliniowa lambda w Pythonie sortujaca liste tupli po drugim elemencie malejaco. Odpowiedz TYLKO kodem."

    print(f"Pytanie: {question}\n")

    for model_name in models:
        claude = ClaudeCode(model=model_name)
        print(f"--- Model: {model_name} ---")
        resp = claude.ask(question)
        print(f"Odpowiedz: {resp.text}")
        if resp.cost_usd:
            print(f"Koszt: ${resp.cost_usd:.6f}")
        print()


# ============================================================
# 12. System prompt - rozne persony
# ============================================================

def demo_personas():
    """Uzyj roznych system promptow do roznch zadan."""
    header("12. Rozne persony (system prompts)")

    personas = {
        "Senior Python Dev": ClaudeCode(
            system_prompt=(
                "Jestes doswiadczonym Python developerem z 15-letnim doswiadczeniem. "
                "Odpowiadasz zwiezle, z naciskiem na best practices i wydajnosc."
            )
        ),
        "Nauczyciel programowania": ClaudeCode(
            system_prompt=(
                "Jestes cierpliwym nauczycielem programowania dla poczatkujacych. "
                "Tlumaczysz wszystko prostym jezykiem z przykladami z zycia codziennego."
            )
        ),
        "Code golfer": ClaudeCode(
            system_prompt=(
                "Jestes mistrzem code golfa. Piszesz najkrotszy mozliwy kod w Pythonie. "
                "Odpowiadasz TYLKO kodem, bez wyjasnien."
            )
        ),
    }

    question = "Jak odwrocic string w Pythonie? Odpowiedz krotko."

    for name, claude in personas.items():
        print(f"--- {name} ---")
        resp = claude.ask(question)
        print(f"{resp.text}\n")


# ============================================================
# MENU GLOWNE
# ============================================================

DEMOS = {
    "1": ("Proste pytanie", demo_simple_question),
    "2": ("Rozmowa z kontekstem", demo_conversation),
    "3": ("Generowanie kodu", demo_generate_code),
    "4": ("Code review", demo_code_review),
    "5": ("Naprawianie bledow", demo_fix_errors),
    "6": ("Pipeline: generuj->uruchom->napraw", demo_pipeline),
    "7": ("Zapytania rownolegle", demo_batch),
    "8": ("Structured output (JSON)", demo_structured),
    "9": ("Iteracyjna refaktoryzacja", demo_refactor),
    "10": ("Asystent do nauki", demo_tutor),
    "11": ("Porownanie modeli", demo_multi_model),
    "12": ("Rozne persony", demo_personas),
    "all": ("Uruchom wszystkie", None),
}


def main():
    print("\n" + "=" * 60)
    print("   Claude Code - Rozbudowane przyklady uzycia")
    print("=" * 60)

    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        print("\nDostepne demo:\n")
        for key, (name, _) in DEMOS.items():
            print(f"  [{key:>3}]  {name}")
        print()
        choice = input("Wybierz numer (lub 'all'): ").strip()

    if choice == "all":
        for key, (name, func) in DEMOS.items():
            if func:
                try:
                    func()
                except KeyboardInterrupt:
                    print("\n\nPrzerwano.")
                    break
                except Exception as e:
                    print(f"\nBlad w demo {key}: {e}\n")
    elif choice in DEMOS and DEMOS[choice][1]:
        DEMOS[choice][1]()
    else:
        print(f"Nieznany wybor: {choice}")
        sys.exit(1)

    print("\nGotowe!")


if __name__ == "__main__":
    main()
