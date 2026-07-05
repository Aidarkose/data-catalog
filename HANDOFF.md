# OMEGA-3 — Handoff (2026-05-30)

Снимок состояния развёрнутого стека после первоначальной установки.
Покрывает то, что **не отражено** в `CLAUDE.md` / `docker-compose.yml`:
артефакты вне репозитория, применённые обходы багов, открытые вопросы.

---

## 1. Что развёрнуто и где

Проект клонирован в `/home/daurena2609/projects/data-catalog`
(в `CLAUDE.md` указан `~/OMEGA-3` — не критично, всё работает с относительными
путями в `docker-compose.yml`).

Стек поднят без сервиса `atrocore` (по запросу пользователя). Остальные
сервисы из `docker-compose.yml` запущены:

| Контейнер | Образ | Статус |
|---|---|---|
| `omega3-postgres` | `postgres:16` | healthy, том `omega3_postgres_data` |
| `omega3-opensearch` | `opensearchproject/opensearch:2.19.1` | healthy |
| `omega3-openmetadata` | `openmetadata/server:1.12.5` | healthy |
| `omega3-airflow-apiserver` | `omega3/airflow:3.0.2` (overlay, см. §3) | healthy |
| `omega3-airflow-scheduler` | то же | healthy |
| `omega3-airflow-dag-processor` | то же | up |
| `omega3-ai-chat` | `omega3/ai-chat:1.0` | up, MCP включён |
| `omega3-nginx` | `nginx:1.27-alpine` | up |

`om-migrate` и `airflow-init` отработали разово (`Exited 0`).

---

## 2. Артефакты ВНЕ репозитория (важно — без них стек не поднимется)

Permission settings рабочей среды запрещают запись в директорию проекта,
поэтому ряд файлов лежит в `$HOME`. **Все `docker compose` команды требуют
передачи `--env-file`.**

| Путь | Что это | Зачем |
|---|---|---|
| `/home/daurena2609/.env.omega3` | env-файл для compose (`GEMINI_API_KEY`, `OM_BOT_JWT`, fernet, JWT-секрет) | docker-compose читает переменные отсюда вместо `.env` в проекте |
| `/home/daurena2609/Dockerfile.airflow.overlay` | overlay-Dockerfile поверх `omega3/airflow:3.0.2` | устанавливает `openmetadata-managed-apis`, фиксирует `protobuf>=6`, `urllib3==1.26` |
| `/home/daurena2609/omega3-init-airflow-session.sql` | DDL для таблицы `session` в `airflow_db` | managed-apis использует flask-session — Airflow 3 эту таблицу не создаёт сам |
| `/home/daurena2609/KRISHA_DWH/dbt/.placeholder` | пустая директория | bind-mount `KRISHA_DWH/dbt:/opt/airflow/krisha_dbt:ro` в compose требует существующего пути |
| `/home/daurena2609/dumps/demo-20250901-2y.sql.gz` | дамп Postgres Pro bookings (1.1 GB) | source-данные для каталога; bind-mount в `omega3-postgres:/dumps:ro` |

### Стандартные команды (с env-file)

```bash
docker compose --env-file /home/daurena2609/.env.omega3 ps
docker compose --env-file /home/daurena2609/.env.omega3 logs -f openmetadata-server
docker compose --env-file /home/daurena2609/.env.omega3 restart ai-chat
docker compose --env-file /home/daurena2609/.env.omega3 up -d --force-recreate airflow-apiserver
```

---

## 3. Overlay-образ Airflow (replace `omega3/airflow:3.0.2`)

`Dockerfile.airflow` в репозитории **не содержит** managed-apis. Я собрал
поверх него overlay и переtegировал так, чтобы compose автоматически брал
правильный образ:

```dockerfile
# /home/daurena2609/Dockerfile.airflow.overlay
FROM omega3/airflow:3.0.2

USER airflow
RUN pip install --no-cache-dir \
      "openmetadata-managed-apis==1.12.5.3" \
 && pip install --no-cache-dir --upgrade \
      "protobuf>=6.31,<7.0" \
      "urllib3==1.26.20"
```

```bash
docker build -t omega3/airflow:3.0.2-mgd -f /home/daurena2609/Dockerfile.airflow.overlay /home/daurena2609
docker tag omega3/airflow:3.0.2-mgd omega3/airflow:3.0.2
docker compose --env-file /home/daurena2609/.env.omega3 up -d --force-recreate \
  airflow-apiserver airflow-scheduler airflow-dag-processor
```

**Почему именно эти пины:**

- `openmetadata-managed-apis 1.12.5.3` — REST API плагин в Airflow, без которого OM UI не может deploy/trigger ingestion-пайплайнов. Подтянул протобуф 4.x как зависимость.
- `protobuf>=6.31,<7.0` — этого требует `dbt-core 1.10.20` (без отката `dbt parse` падает: `MessageToJson() got an unexpected keyword argument`).
- `urllib3==1.26.20` — этого требует `collate-data-diff` (компонент OM profiler) через runtime `pkg_resources` check. С `urllib3 2.x` test_connection падает «Failed to connect to postgres».

Эти три зависимости вместе создают узкую совместимую полосу. Если будете апгрейдить OM или dbt — пересчитайте.

---

## 4. Что нужно закоммитить в репо (чтобы убрать overlay-обход)

Минимальный diff в репозитории, который сделает overlay ненужным:

### `Dockerfile.airflow` — добавить managed-apis и пины

```diff
 RUN pip install --no-cache-dir \
       "openmetadata-ingestion[postgres]==1.12.5.3" \
       "collate-dbt-artifacts-parser>=0.1"
+
+# Плагин для OM ingestion UI (deploy/trigger DAG-ов через Airflow)
+RUN pip install --no-cache-dir \
+      "openmetadata-managed-apis==1.12.5.3" \
+ && pip install --no-cache-dir --upgrade \
+      "protobuf>=6.31,<7.0" \
+      "urllib3==1.26.20"
```

### `scripts/init-db.sql` — добавить session-таблицу для managed-apis

```diff
 -- demo_user is granted SELECT on source schemas AFTER dump load
 -- (see scripts/load_dump.sh which runs the GRANT block post-restore).
+
+\c airflow_db
+CREATE TABLE IF NOT EXISTS session (
+    id SERIAL PRIMARY KEY,
+    session_id VARCHAR(255) UNIQUE,
+    data BYTEA,
+    expiry TIMESTAMP
+);
+GRANT ALL ON TABLE session, session_id_seq TO airflow;
```

### `docker-compose.yml` — выставить права на dags при init

```diff
 airflow-init:
   <<: *airflow-common
   container_name: omega3-airflow-init
   entrypoint: /bin/bash
   command:
     - -c
     - |
       set -e
       airflow db migrate
+      # managed-apis пишет сюда DAG-файлы при Deploy из OM UI
+      chmod -R 777 /opt/airflow/dags
+      mkdir -p /opt/airflow/dag_generated_configs && chmod -R 777 /opt/airflow/dag_generated_configs
       echo "Airflow 3.0 DB migrated."
```

### `airflow/scripts/run_om_ingestion.py` и `run_dbt_ingestion.py` — баг JWT

```diff
-if not sec.get("jwtToken"):
+if not sec.get("jwtToken") or sec.get("jwtToken") == "__INJECT_AT_RUNTIME__":
     sec["jwtToken"] = token
```

Без этого исправления injection placeholder остаётся как есть, и ingestion
падает «Not Authorized! Invalid token» при первом запуске. Я обходил это
копированием YAML в `/tmp` внутри контейнера и `sed`-ом.

### YAML-конфиги ingestion — убрать placeholder

В `ingestion/postgres_service.yaml`, `ingestion/dbt_lineage.yaml` (и других,
где есть `"__INJECT_AT_RUNTIME__"`) заменить на пустую строку:

```diff
-      jwtToken: "__INJECT_AT_RUNTIME__"
+      jwtToken: ""
```

Тогда обновлённая логика (см. выше) подставит свежий токен при запуске.

Также в `postgres_lineage.yaml`, `postgres_metadata.yaml`,
`postgres_profiler.yaml`, `postgres_data_quality.yaml` лежат **просроченные
hardcoded JWT** (от предыдущей инсталляции OM). Их можно тоже заменить на
`""` или вообще удалить — `run_om_ingestion.py` залогинится свежим
токеном автоматически.

---

## 5. Что было сделано

### 5.1 Базовая установка

- `git clone https://github.com/Aidarkose/data-catalog` → `~/projects/data-catalog`
- `.env` создан в `/home/daurena2609/.env.omega3` (с `GEMINI_API_KEY`)
- Создан placeholder `~/KRISHA_DWH/dbt`
- `docker compose build airflow-apiserver ai-chat` → 2 кастомных образа
- `docker compose up -d` для 10 сервисов (без atrocore)
- `scripts/load_dump.sh` → загружен `demo-20250901-2y.sql.gz`
  - 12 таблиц в `bookings`, всего ~85M строк, 11 GB
  - `public_staging` и `public_marts` созданы, `demo_user` имеет нужные гранты

### 5.2 dbt

- `dbt deps`, `dbt run` (3 модели), `dbt test` (10/10 PASS), `dbt docs generate`
- `dbt docs serve` поднят на :8090 (внутри `omega3-airflow-apiserver`)

### 5.3 OpenMetadata ingestion

- Postgres metadata ingestion ✅ (23 записи, 2 БД, 6 схем, 15 таблиц)
- dbt lineage ✅ (8 записей, 100% success)
- Profiler (только метрики) ✅ (9 таблиц, 141 column profile)
- Lineage ⚠️ (79% success — известный pydantic-баг
  `'OMetaLineageRequest' object has no attribute 'queries'` в OM 1.12)

### 5.4 AI-чат и MCP

- Bot JWT для `ingestion-bot` получен → `OM_BOT_JWT` в `.env.omega3`
- ai-chat поднят, в логах: `MCP enabled: 12 tools loaded from OM MCP`
- Gemini периодически возвращает 503 `high demand` — это free-tier rate-limit,
  не конфигурация

### 5.5 Включение UI для ingestion (вкладка Pipelines)

Без overlay-образа UI показывает «Планировщик загрузки не может ответить».
Установил `openmetadata-managed-apis==1.12.5.3`, создал таблицу
`airflow_db.session`, выдал `chmod 777 /opt/airflow/dags`. После этого:

```
GET /pluginsv2/api/v2/openmetadata/health → {"status":"healthy","version":"1.12.5.3"}
GET /api/v1/services/ingestionPipelines/status (OM) → {"code":200,"platform":"Airflow","version":"1.12.5.3"}
```

Теперь в OM UI можно добавлять ingestion: **Service → Agents/Ingestions → Add Ingestion →** тип (Metadata / Lineage / Profiler / dbt / Usage / Data Quality / AutoClassification). При Deploy OM создаёт через managed-apis в `/opt/airflow/dags/<uuid>.py` + JSON-конфиг рядом — это **обычные DAG-и в нашем Airflow**, никакого «внутреннего Airflow в OM» нет.

### 5.6 Sample data в OM UI

OM 1.12 показывает sample data только если запустить **AutoClassification**
(заменил старый «Profiler+Sample Data»). AutoClassification ломается на цепочке
конфликтов deps:

- `presidio-analyzer` (нужен для AutoClass) подтягивает `cryptography` → `cffi>=2`
- `snowflake-connector-python` (зависимость OM ingestion) требует `cffi<2`

Обошёл это **прямым PUT в OM REST**: `/tmp/push_samples.py` (внутри
`omega3-airflow-apiserver`) логинится админом, читает из `bookings.*` по 50
строк и шлёт `PUT /api/v1/tables/{id}/sampleData`. Результат — 12 таблиц
с sample data. Скрипт можно переоформить как Airflow DAG для расписания.

---

## 6. Доступ ко всему стеку

| Сервис | URL | Логин / Пароль |
|---|---|---|
| **OpenMetadata UI** | http://localhost:8585 | `admin@open-metadata.org` / `admin` |
| OM admin/health | http://localhost:8586/healthcheck | — |
| **Airflow UI** (один на весь стек) | http://localhost:8080 | `admin` / `admin` (SimpleAuthManager, любой логин = admin) |
| dbt docs | http://localhost:8090 | — |
| OpenSearch | http://localhost:9200 | без auth |
| AI-чат | http://localhost:8585/omega3-ai/ | — |
| **Postgres `demo`** | `localhost:5432` | `postgres` / `postgres_secret_2024` (superuser) |
| Postgres `demo` (dbt) | `localhost:5432` | `demo_user` / `demo_secret_2024` |
| Postgres `airflow_db` | `localhost:5432` | `airflow` / `airflow_secret_2024` |
| Postgres `openmetadata_db` | `localhost:5432` | `openmetadata` / `openmetadata_secret_2024` |

---

## 7. Известные ограничения / открытые вопросы

| Проблема | Что делать |
|---|---|
| **AutoClassification из UI не работает** | Цепочка deps конфликтная. Sample data ставить через `push_samples.py` (Airflow DAG) или ждать `openmetadata-ingestion 1.13.x` |
| **Lineage workflow ~79% success** | Известный pydantic-баг в OM 1.12.5 (`'OMetaLineageRequest' object has no attribute 'queries'`). Не блокирует — часть lineage пишется |
| **Gemini периодически 503** | Free-tier rate-limit. При необходимости — переключить на `gemini-2.5-flash-lite` в `.env.omega3` |
| **`Dockerfile.airflow` не содержит managed-apis** | Применить diff из §4 и удалить overlay |
| **`scripts/init-db.sql` не создаёт `session` table** | Применить diff из §4. Сейчас таблица создана в текущем `postgres_data`-volume вручную — если `down -v`, нужно пересоздать через `/home/daurena2609/omega3-init-airflow-session.sql` |
| **Скрипты `run_om_*.py` имеют баг placeholder** | См. §4. Сейчас обхожу копированием YAML в `/tmp` и `sed`-ом |
| **`AtroCore` не развёрнут** | По запросу пользователя. БД `atrocore_db` создана `init-db.sql` (пустая), DAG `atrocore_om_ingestion_dag` загружен в Airflow, но paused. Чтобы запустить — `docker compose --env-file ... up -d --build atrocore` |
| **KRISHA_DWH placeholder** | `~/KRISHA_DWH/dbt/` пустой. Если внешний проект krisha_dwh не нужен — соответствующие 4 YAML и DAG `krisha_om_ingestion_dag` можно удалить из репо |

---

## 8. Полезные скрипты внутри контейнеров

### Логин в OM (получить admin JWT)
```bash
ADM=$(curl -s -X POST http://localhost:8585/api/v1/users/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@open-metadata.org","password":"YWRtaW4="}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['accessToken'])")
echo $ADM
```

### Обновить bot-JWT для AI-чата
```bash
docker exec omega3-airflow-apiserver python3 - <<'PY'
# см. scripts/setup_ai_chat.py — он пишет в .env проекта, который read-only.
# Вместо этого: вручную взять JWT и положить в /home/daurena2609/.env.omega3
PY
```

### Принудительно сгенерить sample data
```bash
docker exec omega3-airflow-apiserver python3 /tmp/push_samples.py
# скрипт лежит в /tmp контейнера — после recreate его нужно перезалить через docker cp
```

### Запустить ingestion вручную (минуя UI)
```bash
docker exec omega3-airflow-apiserver bash -lc '
  python3 -c "
import yaml
with open(\"/opt/airflow/ingestion/postgres_service.yaml\") as f: cfg=yaml.safe_load(f)
cfg[\"workflowConfig\"][\"openMetadataServerConfig\"][\"securityConfig\"][\"jwtToken\"]=\"\"
with open(\"/tmp/postgres_service.yaml\",\"w\") as f: yaml.safe_dump(cfg,f)
"
  python3 /opt/airflow/scripts/run_om_ingestion.py -c /tmp/postgres_service.yaml
'
```

---

## 9. Архитектурная справка (короткая)

```
Browser ──:8585──► nginx ──► OpenMetadata (Java, Dropwizard) ──► Postgres (openmetadata_db)
                              │                                  └─ OpenSearch (index)
                              │
                              │ HTTP /pluginsv2/api/v2/openmetadata/*
                              ▼
Browser ──:8080──► Airflow (api-server + scheduler + dag-processor)
                              │   │
                              │   └─ managed-apis плагин читает/пишет DAG-файлы
                              │     /opt/airflow/dags/<uuid>.py
                              │     /opt/airflow/dag_generated_configs/<uuid>.json
                              │
                              ├─► dbt (внутри Airflow) ──► Postgres (demo)
                              ├─► OM ingestion CLI ──────► Postgres (demo) → OM REST
                              └─► OpenLineage → OM /api/v1/lineage/openlineage

ai-chat ──:8500──► Gemini API
            └──── MCP (через openmetadata-server:8585/mcp) → OM каталог
```

---

## 10. Quick start с нуля (для следующего человека)

```bash
# 1. Получить артефакты вне репо
cp env.example /home/daurena2609/.env.omega3
sed -i 's/^GEMINI_API_KEY=.*/GEMINI_API_KEY=<your-key>/' /home/daurena2609/.env.omega3
mkdir -p /home/daurena2609/KRISHA_DWH/dbt /home/daurena2609/dumps

# 2. Положить дамп: /home/daurena2609/dumps/demo-20250901-2y.sql.gz

# 3. Сборка
cd /home/daurena2609/projects/data-catalog
docker compose --env-file /home/daurena2609/.env.omega3 build airflow-apiserver ai-chat

# 4. Применить overlay (пока diff из §4 не закоммичен)
docker build -t omega3/airflow:3.0.2-mgd \
  -f /home/daurena2609/Dockerfile.airflow.overlay /home/daurena2609
docker tag omega3/airflow:3.0.2-mgd omega3/airflow:3.0.2

# 5. Старт стека
docker compose --env-file /home/daurena2609/.env.omega3 up -d \
  postgres opensearch om-migrate openmetadata-server \
  airflow-init airflow-apiserver airflow-scheduler airflow-dag-processor \
  ai-chat nginx

# 6. Создать flask-session table (для managed-apis)
docker exec -i omega3-postgres psql -U postgres -d airflow_db \
  -f - < /home/daurena2609/omega3-init-airflow-session.sql

# 7. Выдать права на dags (для managed-apis Deploy)
docker exec -u 0 omega3-airflow-apiserver chmod -R 777 /opt/airflow/dags /opt/airflow/dag_generated_configs

# 8. Загрузить дамп
bash scripts/load_dump.sh /home/daurena2609/dumps/demo-20250901-2y.sql.gz

# 9. Прогнать dbt
docker exec omega3-airflow-apiserver bash -lc \
  'cd /opt/airflow/dbt && dbt deps && dbt run --threads 8 && dbt test && dbt docs generate'

# 10. Ingestion: см. §8
```
