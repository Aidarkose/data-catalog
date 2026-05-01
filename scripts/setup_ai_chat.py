#!/usr/bin/env python3
"""
OMEGA-3 — настройка AI чата.

Что делает:
  1. Логинится в OpenMetadata как admin (пароль base64).
  2. Получает JWT для bot-пользователя (по умолчанию ingestion-bot).
  3. Записывает OM_BOT_JWT в .env (создаёт/обновляет строку).
  4. Печатает подсказку, как включить MCP Application в OM (если ещё не включён).

После запуска: docker compose up -d ai-chat nginx  (или docker compose restart ai-chat).
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

OM_BASE = os.environ.get("OM_BASE", "http://localhost:8585")
ADMIN_EMAIL = os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org")
ADMIN_PASSWORD = os.environ.get("OM_ADMIN_PASSWORD", "admin")
BOT_NAME = os.environ.get("OM_BOT_NAME", "ingestion-bot")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ENV_FILE = os.path.join(ROOT, ".env")


def http(method: str, path: str, token: str | None = None, body: dict | None = None):
    url = f"{OM_BASE}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read() or b"{}")
        except Exception:
            payload = {}
        return e.code, payload
    except urllib.error.URLError as e:
        print(f"[ERROR] Не могу достучаться до {url}: {e}", file=sys.stderr)
        sys.exit(2)


def login() -> str:
    pwd = base64.b64encode(ADMIN_PASSWORD.encode()).decode()
    code, resp = http("POST", "/api/v1/users/login", body={"email": ADMIN_EMAIL, "password": pwd})
    if code != 200 or "accessToken" not in resp:
        print(f"[ERROR] Login failed ({code}): {resp}", file=sys.stderr)
        sys.exit(3)
    return resp["accessToken"]


def get_bot_jwt(admin_token: str) -> str:
    code, bot = http("GET", f"/api/v1/bots/name/{BOT_NAME}", token=admin_token)
    if code != 200:
        print(f"[ERROR] Bot '{BOT_NAME}' не найден ({code}): {bot}", file=sys.stderr)
        sys.exit(4)
    bot_user = bot.get("botUser") or {}
    bot_user_id = bot_user.get("id")
    if not bot_user_id:
        print(f"[ERROR] У bot '{BOT_NAME}' нет связанного user.id", file=sys.stderr)
        sys.exit(5)

    code, mech = http("GET", f"/api/v1/users/auth-mechanism/{bot_user_id}", token=admin_token)
    if code != 200:
        print(f"[ERROR] Не получить auth-mechanism для bot ({code}): {mech}", file=sys.stderr)
        sys.exit(6)
    jwt = (mech.get("config") or {}).get("JWTToken")
    if not jwt:
        print(f"[ERROR] JWT отсутствует в auth-mechanism: {mech}", file=sys.stderr)
        sys.exit(7)
    return jwt


def update_env(jwt: str, gemini_key: str | None) -> None:
    lines: list[str] = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()

    def set_kv(key: str, value: str) -> None:
        nonlocal lines
        pat = re.compile(rf"^{re.escape(key)}=")
        lines = [ln for ln in lines if not pat.match(ln)]
        lines.append(f"{key}={value}")

    set_kv("OM_BOT_JWT", jwt)
    if gemini_key:
        set_kv("GEMINI_API_KEY", gemini_key)

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    print(f"[OK] {ENV_FILE} обновлён (OM_BOT_JWT{', GEMINI_API_KEY' if gemini_key else ''}).")


def check_mcp_app(admin_token: str) -> None:
    # У OM 1.7+ есть "MCP Application" в Marketplace. В 1.12 он по умолчанию
    # НЕ установлен — пользователь включает его в UI:
    #   Settings → Applications → Add Apps → MCP → Install.
    # Проверим текущий статус.
    for candidate in ("McpApplication", "MCPApplication", "mcp-application", "Mcp"):
        code, _ = http("GET", f"/api/v1/apps/name/{candidate}", token=admin_token)
        if code == 200:
            print(f"[OK] MCP Application установлен в OM ({candidate}).")
            return
    print(
        "[INFO] MCP Application пока НЕ установлен в OpenMetadata.\n"
        "       Чат будет работать в режиме REST-tools (то же покрытие, чуть проще схемы).\n"
        "       Чтобы включить MCP — открой http://localhost:8585 → \n"
        "         Settings → Applications → Add Apps → найти 'MCP' → Install → Schedule\n"
        "       Затем перезапусти сервис: docker compose restart ai-chat"
    )


def main() -> None:
    gemini_key = None
    if "--gemini-key" in sys.argv:
        i = sys.argv.index("--gemini-key")
        if i + 1 < len(sys.argv):
            gemini_key = sys.argv[i + 1]

    print(f"[..] Логинимся в OM ({OM_BASE}) как {ADMIN_EMAIL}")
    admin_token = login()
    print(f"[..] Получаем JWT bot '{BOT_NAME}'")
    bot_jwt = get_bot_jwt(admin_token)
    update_env(bot_jwt, gemini_key)
    check_mcp_app(admin_token)
    print("[OK] Готово. Теперь:  docker compose up -d ai-chat nginx")


if __name__ == "__main__":
    main()
