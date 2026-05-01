"""
OMEGA-3 AI Chat backend.

Гибридный сервис: FastAPI + Gemini + tools.
Tools — комбинация:
  1) MCP-сервера OpenMetadata (если включён MCP App и есть OM_BOT_JWT)
  2) Встроенных REST-инструментов поверх OM API (всегда работают)

Если MCP недоступен — отвечаем на REST-tools, без потери функциональности.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("ai-chat")

OM_BASE = os.environ.get("OM_BASE_URL", "http://openmetadata-server:8585").rstrip("/")
OM_API = f"{OM_BASE}/api"
OM_MCP_URL = os.environ.get("OM_MCP_URL", f"{OM_BASE}/mcp")
OM_MCP_TRANSPORT = os.environ.get("OM_MCP_TRANSPORT", "streamable_http").lower()
OM_BOT_JWT = os.environ.get("OM_BOT_JWT", "").strip()
OM_ADMIN_EMAIL = os.environ.get("OM_ADMIN_EMAIL", "admin@open-metadata.org")
OM_ADMIN_PASSWORD = os.environ.get("OM_ADMIN_PASSWORD", "admin")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

MAX_TOOL_TURNS = 8


SYSTEM_PROMPT = (
    "Ты — AI-помощник по корпоративному каталогу данных OpenMetadata в проекте OMEGA-3. "
    "Помогаешь пользователям находить таблицы, схемы, dashboards, lineage, тесты качества, "
    "глоссарии, метрики и владельцев данных. Используй доступные tools, чтобы найти точную "
    "информацию в каталоге, прежде чем отвечать. Если запрос неоднозначен — задавай уточняющие "
    "вопросы. Отвечай по-русски, кратко и по существу. При упоминании сущностей каталога "
    "указывай их fullyQualifiedName (FQN) в обратных кавычках."
)


# ---------------------------------------------------------------------------
# OpenMetadata REST helpers (admin login fallback + tools)
# ---------------------------------------------------------------------------

class OMClient:
    def __init__(self) -> None:
        self._token: str | None = OM_BOT_JWT or None
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(base_url=OM_API, timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def _ensure_token(self) -> str:
        async with self._lock:
            if self._token:
                return self._token
            log.info("OM_BOT_JWT not set — falling back to admin login")
            pwd_b64 = base64.b64encode(OM_ADMIN_PASSWORD.encode()).decode()
            r = await self._client.post(
                "/v1/users/login",
                json={"email": OM_ADMIN_EMAIL, "password": pwd_b64},
            )
            r.raise_for_status()
            self._token = r.json()["accessToken"]
            return self._token

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        token = await self._ensure_token()
        headers = kwargs.pop("headers", {}) or {}
        headers["Authorization"] = f"Bearer {token}"
        return await self._client.request(method, path, headers=headers, **kwargs)

    async def get_json(self, path: str, params: dict | None = None) -> Any:
        r = await self.request("GET", path, params=params)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Built-in REST tools (always available; mimic MCP tool surface)
# ---------------------------------------------------------------------------

REST_TOOLS = [
    {
        "name": "search_metadata",
        "description": (
            "Полнотекстовый поиск по каталогу OpenMetadata. Ищет таблицы, дашборды, "
            "topics, pipelines, glossary terms, users по строке запроса. Возвращает "
            "топ-N результатов c FQN, типом и описанием."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Текст поискового запроса"},
                "index": {
                    "type": "string",
                    "description": (
                        "Какой индекс искать. По умолчанию all. Допустимые: "
                        "table_search_index, dashboard_search_index, "
                        "pipeline_search_index, topic_search_index, "
                        "glossary_term_search_index, user_search_index, all."
                    ),
                    "default": "all",
                },
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_table",
        "description": (
            "Возвращает полную информацию о таблице по её FQN: колонки, описание, "
            "владельцы, теги, sampleData, profile."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fqn": {"type": "string", "description": "FQN таблицы, напр. demo_postgres.demo.bookings.flights"},
                "fields": {
                    "type": "string",
                    "description": "Какие поля вернуть (CSV)",
                    "default": "columns,owners,tags,description,domain,profile",
                },
            },
            "required": ["fqn"],
        },
    },
    {
        "name": "get_lineage",
        "description": (
            "Возвращает lineage сущности (откуда данные пришли и куда идут). "
            "Указывается FQN таблицы/дашборда и глубина (1-3)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fqn": {"type": "string"},
                "entity_type": {"type": "string", "default": "table"},
                "upstream_depth": {"type": "integer", "default": 2},
                "downstream_depth": {"type": "integer", "default": 2},
            },
            "required": ["fqn"],
        },
    },
    {
        "name": "list_glossary_terms",
        "description": "Список терминов из бизнес-глоссария (по имени глоссария или всего).",
        "parameters": {
            "type": "object",
            "properties": {
                "glossary": {"type": "string", "description": "Имя глоссария (опционально)"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "get_test_results",
        "description": "Список последних результатов тестов качества данных по таблице (FQN).",
        "parameters": {
            "type": "object",
            "properties": {
                "table_fqn": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
            "required": ["table_fqn"],
        },
    },
    {
        "name": "list_databases",
        "description": "Список зарегистрированных database services / databases / схем.",
        "parameters": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "enum": ["services", "databases", "schemas"],
                    "default": "services",
                },
                "parent_fqn": {
                    "type": "string",
                    "description": "FQN родителя (нужно для databases/schemas)",
                },
                "limit": {"type": "integer", "default": 100},
            },
        },
    },
]


async def run_rest_tool(om: OMClient, name: str, args: dict) -> str:
    try:
        if name == "search_metadata":
            q = args.get("query", "")
            idx = args.get("index", "all")
            limit = int(args.get("limit", 10))
            params = {"q": q or "*", "from": 0, "size": limit}
            if idx and idx != "all":
                params["index"] = idx
            data = await om.get_json("/v1/search/query", params=params)
            hits = data.get("hits", {}).get("hits", [])
            out = []
            for h in hits[:limit]:
                src = h.get("_source", {})
                out.append({
                    "fqn": src.get("fullyQualifiedName"),
                    "type": src.get("entityType") or h.get("_index"),
                    "name": src.get("name"),
                    "description": (src.get("description") or "")[:300],
                })
            return json.dumps({"results": out, "total": data.get("hits", {}).get("total", {}).get("value")}, ensure_ascii=False)

        if name == "get_table":
            fqn = args["fqn"]
            fields = args.get("fields", "columns,owners,tags,description,domain")
            data = await om.get_json(f"/v1/tables/name/{fqn}", params={"fields": fields})
            slim = {
                "fqn": data.get("fullyQualifiedName"),
                "name": data.get("name"),
                "description": data.get("description"),
                "owners": [o.get("name") for o in data.get("owners", []) or []],
                "tags": [t.get("tagFQN") for t in data.get("tags", []) or []],
                "columns": [
                    {
                        "name": c.get("name"),
                        "dataType": c.get("dataType"),
                        "description": c.get("description"),
                    }
                    for c in data.get("columns", []) or []
                ][:200],
                "rowCount": (data.get("profile") or {}).get("rowCount"),
            }
            return json.dumps(slim, ensure_ascii=False)

        if name == "get_lineage":
            fqn = args["fqn"]
            etype = args.get("entity_type", "table")
            up = int(args.get("upstream_depth", 2))
            down = int(args.get("downstream_depth", 2))
            data = await om.get_json(
                f"/v1/lineage/{etype}/name/{fqn}",
                params={"upstreamDepth": up, "downstreamDepth": down},
            )
            nodes = data.get("nodes", [])
            edges = data.get("edges", []) + data.get("downstreamEdges", []) + data.get("upstreamEdges", [])
            return json.dumps(
                {
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                    "nodes": [{"fqn": n.get("fullyQualifiedName"), "type": n.get("type")} for n in nodes][:50],
                    "edges": [{"from": e.get("fromEntity"), "to": e.get("toEntity")} for e in edges][:80],
                },
                ensure_ascii=False,
            )

        if name == "list_glossary_terms":
            limit = int(args.get("limit", 50))
            params = {"limit": limit}
            data = await om.get_json("/v1/glossaryTerms", params=params)
            terms = data.get("data", [])
            wanted = args.get("glossary")
            if wanted:
                terms = [t for t in terms if (t.get("glossary") or {}).get("name") == wanted]
            out = [
                {
                    "name": t.get("name"),
                    "fqn": t.get("fullyQualifiedName"),
                    "glossary": (t.get("glossary") or {}).get("name"),
                    "description": (t.get("description") or "")[:200],
                }
                for t in terms
            ]
            return json.dumps({"terms": out}, ensure_ascii=False)

        if name == "get_test_results":
            fqn = args["table_fqn"]
            limit = int(args.get("limit", 20))
            data = await om.get_json(
                "/v1/dataQuality/testCases",
                params={"entityLink": f"<#E::table::{fqn}>", "limit": limit, "fields": "testCaseResult"},
            )
            tests = data.get("data", [])
            out = [
                {
                    "name": t.get("name"),
                    "test_definition": (t.get("testDefinition") or {}).get("name"),
                    "last_status": (t.get("testCaseResult") or {}).get("testCaseStatus"),
                    "last_timestamp": (t.get("testCaseResult") or {}).get("timestamp"),
                    "result": (t.get("testCaseResult") or {}).get("result"),
                }
                for t in tests
            ]
            return json.dumps({"tests": out}, ensure_ascii=False)

        if name == "list_databases":
            level = args.get("level", "services")
            limit = int(args.get("limit", 100))
            if level == "services":
                data = await om.get_json("/v1/services/databaseServices", params={"limit": limit})
                items = [{"name": s.get("name"), "type": s.get("serviceType")} for s in data.get("data", [])]
            elif level == "databases":
                params = {"limit": limit}
                if args.get("parent_fqn"):
                    params["service"] = args["parent_fqn"]
                data = await om.get_json("/v1/databases", params=params)
                items = [{"name": d.get("name"), "fqn": d.get("fullyQualifiedName")} for d in data.get("data", [])]
            else:  # schemas
                params = {"limit": limit}
                if args.get("parent_fqn"):
                    params["database"] = args["parent_fqn"]
                data = await om.get_json("/v1/databaseSchemas", params=params)
                items = [{"name": s.get("name"), "fqn": s.get("fullyQualifiedName")} for s in data.get("data", [])]
            return json.dumps({level: items}, ensure_ascii=False)

        return json.dumps({"error": f"Unknown tool: {name}"})
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"HTTP {e.response.status_code}", "body": e.response.text[:300]})
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Optional MCP client (best-effort; if it fails — REST tools take over)
# ---------------------------------------------------------------------------

async def list_mcp_tools() -> list[dict] | None:
    """Try to list tools from OM MCP. Returns None if MCP не доступен."""
    if not OM_BOT_JWT:
        log.info("OM_BOT_JWT not set — MCP отключён")
        return None
    try:
        from mcp import ClientSession
        if OM_MCP_TRANSPORT == "sse":
            from mcp.client.sse import sse_client as transport_ctx
        else:
            from mcp.client.streamable_http import streamablehttp_client as transport_ctx
    except Exception as e:  # noqa: BLE001
        log.warning("MCP SDK import failed: %s", e)
        return None

    headers = {"Authorization": f"Bearer {OM_BOT_JWT}"}
    try:
        async with transport_ctx(OM_MCP_URL, headers=headers) as ctx:
            read, write = ctx[0], ctx[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.list_tools()
                return [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema or {"type": "object", "properties": {}},
                    }
                    for t in resp.tools
                ]
    except Exception as e:  # noqa: BLE001
        log.warning("MCP list_tools failed (%s) — fallback на REST", e)
        return None


async def call_mcp_tool(name: str, args: dict) -> str:
    from mcp import ClientSession
    if OM_MCP_TRANSPORT == "sse":
        from mcp.client.sse import sse_client as transport_ctx
    else:
        from mcp.client.streamable_http import streamablehttp_client as transport_ctx

    headers = {"Authorization": f"Bearer {OM_BOT_JWT}"}
    async with transport_ctx(OM_MCP_URL, headers=headers) as ctx:
        read, write = ctx[0], ctx[1]
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            chunks = []
            for c in result.content:
                if hasattr(c, "text") and c.text:
                    chunks.append(c.text)
            return "\n".join(chunks) or json.dumps({"ok": True})


# ---------------------------------------------------------------------------
# Gemini integration
# ---------------------------------------------------------------------------

def gemini_client():
    if not GEMINI_API_KEY:
        raise HTTPException(500, "GEMINI_API_KEY не настроен")
    from google import genai
    return genai


def _format_gemini_error(exc: Exception) -> str:
    """Превращает исключения google.genai в дружелюбное сообщение для чата."""
    name = type(exc).__name__
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    raw = str(exc)

    if code == 429 or "RESOURCE_EXHAUSTED" in raw or "quota" in raw.lower():
        retry = ""
        m = re.search(r"retry in ([\d.]+)s", raw, re.IGNORECASE)
        if m:
            retry = f" Попробуйте через ~{int(float(m.group(1)))} с."
        # limit: 0 в ответе = у проекта вовсе нет free-tier-квоты на эту модель
        zero_quota = "limit: 0" in raw
        if zero_quota:
            return (
                f"⚠️ У вашего AI Studio проекта нет free-tier-квоты на модель `{GEMINI_MODEL}` "
                f"(`limit: 0` в ответе Gemini). Пересоздание API key не поможет — квота "
                f"привязана к проекту, а не к ключу.\n\n"
                f"Смените модель в `.env` на одну из доступных, например "
                f"`GEMINI_MODEL=gemini-2.5-flash-lite` или `GEMINI_MODEL=gemini-flash-latest`, "
                f"и перезапустите: `docker compose up -d ai-chat`."
            )
        return (
            f"⚠️ Лимит Gemini API исчерпан для модели `{GEMINI_MODEL}`.{retry}\n\n"
            f"Если ошибка повторяется, смените модель в `.env` "
            f"(например, `GEMINI_MODEL=gemini-2.5-flash-lite`) и выполните "
            f"`docker compose up -d ai-chat`."
        )
    if code in (401, 403) or "API key" in raw or "API_KEY_INVALID" in raw:
        return "⚠️ Gemini отклонил API-ключ. Проверьте `GEMINI_API_KEY` в `.env`."
    if code == 404 or "not found" in raw.lower() and "model" in raw.lower():
        return f"⚠️ Модель `{GEMINI_MODEL}` не найдена в Gemini API. Проверьте `GEMINI_MODEL` в `.env`."
    return f"⚠️ Ошибка Gemini ({name}): {raw[:400]}"


def tool_schemas_to_gemini_config(schemas: list[dict]):
    """Convert OpenAPI-ish JSON Schema into a Gemini Tool config."""
    from google.genai import types as gt

    decls = []
    for s in schemas:
        decls.append(
            gt.FunctionDeclaration(
                name=s["name"],
                description=s.get("description", ""),
                parameters=_clean_schema(s.get("parameters") or {"type": "object", "properties": {}}),
            )
        )
    return [gt.Tool(function_declarations=decls)]


_GEMINI_ALLOWED_KEYS = {
    "type", "properties", "required", "items", "enum", "description",
    "format", "minimum", "maximum", "default", "nullable",
}


def _clean_schema(node: Any, is_root: bool = True) -> dict:
    """
    Нормализует JSON-Schema из MCP-tools под требования Gemini:
      * выбрасывает неподдерживаемые ключи ($schema, additionalProperties, oneOf, ...);
      * на корне принудительно type=object;
      * рекурсивно чистит properties и items;
      * required — оставляет только ключи, реально присутствующие в properties.
    """
    if not isinstance(node, dict):
        return {"type": "object", "properties": {}} if is_root else {}

    out: dict = {}
    for k, v in node.items():
        if k in _GEMINI_ALLOWED_KEYS:
            out[k] = v

    if is_root and "type" not in out:
        out["type"] = "object"

    if "properties" in out and isinstance(out["properties"], dict):
        out["properties"] = {
            pk: _clean_schema(pv, is_root=False) for pk, pv in out["properties"].items()
        }
    elif out.get("type") == "object":
        out["properties"] = {}

    if "items" in out and isinstance(out["items"], dict):
        out["items"] = _clean_schema(out["items"], is_root=False)

    if "required" in out:
        if isinstance(out["required"], list):
            props = out.get("properties") or {}
            out["required"] = [r for r in out["required"] if isinstance(r, str) and r in props]
            if not out["required"]:
                del out["required"]
        else:
            del out["required"]

    return out


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str  # "user" | "model"
    text: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    reply: str
    used_tools: list[str] = []
    backend: str = "rest"  # "rest" | "mcp"


@asynccontextmanager
async def lifespan(app: FastAPI):
    om = OMClient()
    app.state.om = om
    # Best-effort discovery of MCP tools at startup
    app.state.mcp_tools = await list_mcp_tools()
    if app.state.mcp_tools:
        log.info("MCP enabled: %d tools loaded from OM MCP", len(app.state.mcp_tools))
    else:
        log.info("MCP disabled — using built-in REST tools (%d)", len(REST_TOOLS))
    try:
        yield
    finally:
        await om.close()


app = FastAPI(title="OMEGA-3 AI Chat", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/chat.html")


@app.get("/health")
async def health():
    return {
        "ok": True,
        "gemini_model": GEMINI_MODEL,
        "om_base": OM_BASE,
        "mcp_enabled": app.state.mcp_tools is not None,
        "mcp_tools": [t["name"] for t in (app.state.mcp_tools or [])],
        "rest_tools": [t["name"] for t in REST_TOOLS],
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Empty message")
    genai = gemini_client()
    from google.genai import types as gt

    use_mcp = app.state.mcp_tools is not None
    tool_schemas = app.state.mcp_tools if use_mcp else REST_TOOLS
    backend = "mcp" if use_mcp else "rest"

    client = genai.Client(api_key=GEMINI_API_KEY)
    tools_cfg = tool_schemas_to_gemini_config(tool_schemas)

    contents: list = []
    for h in req.history[-20:]:
        role = "model" if h.role == "model" else "user"
        contents.append(gt.Content(role=role, parts=[gt.Part(text=h.text)]))
    contents.append(gt.Content(role="user", parts=[gt.Part(text=req.message)]))

    used: list[str] = []
    config = gt.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools_cfg,
        temperature=0.4,
    )

    final_text = ""
    for turn in range(MAX_TOOL_TURNS):
        try:
            resp = await asyncio.to_thread(
                client.models.generate_content,
                model=GEMINI_MODEL,
                contents=contents,
                config=config,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("Gemini generate_content failed")
            return ChatResponse(
                reply=_format_gemini_error(e),
                used_tools=used,
                backend=backend,
            )

        cand = resp.candidates[0] if resp.candidates else None
        if not cand or not cand.content or not cand.content.parts:
            final_text = resp.text or "(пустой ответ)"
            break

        function_calls = [p.function_call for p in cand.content.parts if getattr(p, "function_call", None)]
        if not function_calls:
            final_text = resp.text or ""
            break

        contents.append(cand.content)
        tool_response_parts = []
        for fc in function_calls:
            args = dict(fc.args or {})
            used.append(fc.name)
            log.info("Tool call: %s(%s)", fc.name, json.dumps(args, ensure_ascii=False)[:200])
            try:
                if use_mcp:
                    result_text = await call_mcp_tool(fc.name, args)
                else:
                    result_text = await run_rest_tool(app.state.om, fc.name, args)
            except Exception as e:  # noqa: BLE001
                log.exception("Tool %s failed", fc.name)
                result_text = json.dumps({"error": str(e)})

            # Truncate very large tool outputs to keep context tight
            if len(result_text) > 8000:
                result_text = result_text[:8000] + "...(truncated)"

            tool_response_parts.append(
                gt.Part(
                    function_response=gt.FunctionResponse(
                        name=fc.name,
                        response={"result": result_text},
                    )
                )
            )
        contents.append(gt.Content(role="user", parts=tool_response_parts))
    else:
        final_text = "Превышен лимит инструмент-вызовов. Уточни запрос, пожалуйста."

    return ChatResponse(reply=final_text or "(нет ответа)", used_tools=used, backend=backend)
