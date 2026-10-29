import itertools
import json
import os
import shutil
import sys
import textwrap
import threading
import time

import requests

FILE = "tickets.json"

# ---------- Providers ----------
# Each provider says which environment variable holds its API key.
# Groq and OpenRouter share the OpenAI-compatible chat format, so they only
# need a URL. Gemini has its own format and its own function below.
PROVIDERS = {
    "gemini": {"env": "GEMINI_API_KEY"},
    "groq": {
        "env": "GROQ_API_KEY",
        "url": "https://api.groq.com/openai/v1/chat/completions",
    },
    "openrouter": {
        "env": "OPENROUTER_API_KEY",
        "url": "https://openrouter.ai/api/v1/chat/completions",
    },
}

# Models the user can choose from: menu number -> provider, model ID, short note.
# To add or swap a model, edit this dictionary only.
# Check each provider's model list for exact IDs, since they change often.
MODELS = {
    "1": {"provider": "gemini", "model": "gemini-3.1-flash-lite", "note": "fast and lightweight (recommended)"},
    "2": {"provider": "gemini", "model": "gemini-3.5-flash-lite", "note": "newer lightweight model"},
    "3": {"provider": "groq", "model": "openai/gpt-oss-20b", "note": "fast open model, via Groq"},
    "4": {"provider": "openrouter", "model": "google/gemma-4-31b-it:free", "note": "free Gemma model via OpenRouter"},
    }

# ---------- Colours ----------
USE_COLOR = sys.stdout.isatty()

BLUE = "1;94"
GREEN = "92"
BRIGHT_GREEN = "1;92"
YELLOW = "93"
PURPLE = "1;95"
RED = "91"
GRAY = "90"
WHITE = "97"

BOX_COLOR = YELLOW   # colour of the box outline
BOX_TEXT = WHITE     # colour of the text inside the box


def paint(text, code):
    """Wrap text in a colour code (plain text if the terminal has no colour)."""
    if not USE_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def print_yellow_box(text):
    """Print text inside a yellow outlined rectangle."""
    max_width = min(70, shutil.get_terminal_size().columns - 8)

    lines = []
    for raw in text.splitlines():
        lines.extend(textwrap.wrap(raw, max_width, subsequent_indent="   ") or [""])

    inner = max(len(line) for line in lines)

    print(paint("┌" + "─" * (inner + 2) + "┐", BOX_COLOR))
    for line in lines:
        print(
            paint("│ ", BOX_COLOR)
            + paint(line.ljust(inner), BOX_TEXT)
            + paint(" │", BOX_COLOR)
        )
    print(paint("└" + "─" * (inner + 2) + "┘", BOX_COLOR))


# ---------- Loading spinner ----------
class Spinner:
    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, message):
        self.message = message
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        for frame in itertools.cycle(self.FRAMES):
            if self._stop_event.is_set():
                break
            print(f"\r{paint(frame + ' ' + self.message, YELLOW)}", end="", flush=True)
            time.sleep(0.1)

    def start(self):
        self._thread.start()

    def stop(self, success, final_message):
        self._stop_event.set()
        self._thread.join()
        if success:
            line = paint("✔ " + final_message, BRIGHT_GREEN)
        else:
            line = paint("✖ " + final_message, RED)
        print("\r\033[K" + line)


# ---------- AI ----------
def build_prompt(ticket):
    """The same prompt is used for every provider."""
    return (
        "You are an IT support assistant for a university campus helpdesk.\n"
        "A user submitted this support ticket:\n\n"
        f"Title: {ticket['title']}\n"
        f"Description: {ticket['description']}\n\n"
        "Suggest 3 to 5 practical ways to fix or investigate this problem. "
        "Reply as a short numbered list, one step per line, with no extra introduction."
    )


def call_gemini(api_key, model, prompt):
    """Gemini uses its own request and response format."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, headers=headers, json=body, timeout=60)
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def call_openai_compatible(url, api_key, model, prompt):
    """Works for Groq, OpenRouter, and most other providers."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    response = requests.post(url, headers=headers, json=body, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()

1
def get_ai_suggestions(ticket, choice):
    """choice is one entry from MODELS.
    Returns (suggestions, None) on success or (None, error_message) on failure."""
    provider = choice["provider"]
    model = choice["model"]
    config = PROVIDERS[provider]

    api_key = os.environ.get(config["env"])
    if not api_key:
        return None, f"{config['env']} is not set. Add it to ~/.zshrc and try again."

    prompt = build_prompt(ticket)

    try:
        if provider == "gemini":
            return call_gemini(api_key, model, prompt), None
        return call_openai_compatible(config["url"], api_key, model, prompt), None

    except requests.exceptions.ConnectionError:
        return None, "Could not connect. Please check your internet connection."
    except requests.exceptions.Timeout:
        return None, f"The request to {model} timed out. Try again or choose another model."
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code
        if status in (400, 401, 403):
            return None, f"The {provider} API key was rejected. Check {config['env']}."
        if status == 404:
            return None, f"Model '{model}' was not found on {provider}. Try a different model."
        if status == 429:
            return None, "Too many requests (rate limit). Wait a moment and try again."
        if status in (500, 502, 503):
            return None, f"{model} is unavailable or overloaded. Try another model."
        return None, f"The API request failed (status {status})."
    except (KeyError, IndexError, ValueError):
        return None, "The AI returned a response in an unexpected format."
    except requests.exceptions.RequestException as e:
        return None, f"Request failed: {e}"


def choose_model():
    """Ask the user which AI model to use. Returns the MODELS entry, or None to skip."""
    print(paint("\nChoose an AI model:", BLUE))
    for key, m in MODELS.items():
        print(f"{key}. {m['model']} ({m['provider']}) - {paint(m['note'], GRAY)}")
    print("0. Skip AI suggestions")

    highest = max(int(k) for k in MODELS)
    while True:
        choice = input(
            paint(f"Choose a model (0-{highest}, press Enter for 1): ", GREEN)
        ).strip() or "1"
        if choice == "0":
            return None
        if choice in MODELS:
            return MODELS[choice]
        print(paint(f"Invalid choice. Please enter a number from 0 to {highest}.", RED))


# ---------- Tickets ----------
def create_ticket():
    title = input(paint("Enter ticket title: ", GREEN)).strip()
    description = input(paint("Enter ticket description: ", GREEN)).strip()

    if not title or not description:
        print(paint("Title and description cannot be empty.", RED))
        return None

    try:
        if os.path.exists(FILE):
            with open(FILE, "r") as f:
                tickets = json.load(f)
        else:
            tickets = []

        ticket = {
            "id": f"A{len(tickets) + 1:03d}",
            "title": title,
            "description": description,
        }

        tickets.append(ticket)

        with open(FILE, "w") as f:
            json.dump(tickets, f, indent=4)

        print(paint("\n✔ Ticket created successfully.", BRIGHT_GREEN))
        print(paint("ID:", GRAY), paint(ticket["id"], WHITE))
        print(paint("Description:", GRAY), paint(ticket["description"], WHITE))
        return ticket

    except (OSError, json.JSONDecodeError) as e:
        print(paint(f"Error: {e}", RED))
        return None


def create_ticket_with_suggestions():
    ticket = create_ticket()
    if ticket is None:
        return

    choice = choose_model()
    if choice is None:
        print(paint("\nSkipped AI suggestions. Your ticket is saved.", GRAY))
        return

    print()
    spinner = Spinner(f"Getting AI suggestions from {choice['model']}...")
    spinner.start()
    suggestions, error = get_ai_suggestions(ticket, choice)

    if error:
        spinner.stop(False, error)
        print(paint("The ticket was saved, but no AI suggestions are available right now.", GRAY))
    else:
        spinner.stop(True, "Got AI suggestions")
        print(paint("\nSuggestions:", PURPLE))
        print_yellow_box(suggestions)


# ---------- Menu ----------
def menu():
    while True:
        print(paint("\n===== CampusFlow Ticket Creator =====", BLUE))
        print("1. Create a ticket")
        print("2. Exit")

        choice = input(paint("Choose an option (1-2): ", GREEN))

        if choice == "1":
            create_ticket_with_suggestions()
        elif choice == "2":
            print(paint("Goodbye!", GRAY))
            break
        else:
            print(paint("Invalid choice. Please select 1 or 2.", RED))


if __name__ == "__main__":
    menu()