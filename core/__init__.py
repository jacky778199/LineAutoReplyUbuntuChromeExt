"""
Core modules for LINE Auto-Reply Bot.
Includes automatic .env environment variable loader.
"""

import os

def load_dotenv(dotenv_path: str = ".env"):
    """
    Lightweight .env loader that populates os.environ without external dependencies.
    Supports comments, quotes, and populates both uppercase and lowercase keys.
    """
    candidates = [
        dotenv_path,
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")),
        os.path.abspath(os.path.join(os.getcwd(), ".env"))
    ]
    target = None
    for p in candidates:
        if os.path.exists(p):
            target = p
            break

    if not target:
        return

    try:
        with open(target, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k:
                    # Set exact key
                    if k not in os.environ:
                        os.environ[k] = v
                    # Set uppercase and lowercase aliases
                    k_upper = k.upper()
                    if k_upper not in os.environ:
                        os.environ[k_upper] = v
                    k_lower = k.lower()
                    if k_lower not in os.environ:
                        os.environ[k_lower] = v
    except Exception:
        pass

# Automatically load .env on package import
load_dotenv()
