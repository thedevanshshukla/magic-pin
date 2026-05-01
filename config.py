from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file()


APP_ENV = os.getenv("APP_ENV", "development")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
TEAM_NAME = os.getenv("TEAM_NAME", "Codex")
TEAM_MEMBERS = [member.strip() for member in os.getenv("TEAM_MEMBERS", "OpenAI Codex").split(",") if member.strip()]
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "noreply@example.com")
BOT_VERSION = os.getenv("BOT_VERSION", "1.0.0")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "")

