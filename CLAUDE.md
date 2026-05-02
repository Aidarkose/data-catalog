# OMEGA-3 — Data Catalog

## Что это

Локальный Data Catalog с Data Lineage на WSL2 Ubuntu (Windows).
Стек: **OpenMetadata 1.12.5 + Airflow 3.0.2 + dbt 1.11.7 + PostgreSQL 16 + OpenSearch 2.19.1**.

Весь стек поднимается одной командой: `docker compose up -d`.

---

## Среда выполнения

- WSL2 Ubuntu, user `daurena2609`, проект в `/home/daurena2609/OMEGA-3`
- Docker Desktop с WSL2 integration (не `sudo service docker start`)
- Если `docker` команды падают с permission denied — используй `sg docker -c "..."` или `newgrp docker`
- Дампы лежат в `/home/daurena2609/dumps/` (не в репозитории)

---

## Сервисы и порты

| Контейнер | URL | Логин / Пароль |
|-----------|-----|----------------|
| `omega3-nginx` (фронт OM + AI-виджет) | http://localhost:8585 | admin@open-metadata.org / admin |
| `omega3-openmetadata` (внутри сети) | http://openmetadata-server:8585 | — |
| `omega3-ai-chat` (через nginx) | http://localhost:8585/omega3-ai/ | — |
| `omega3-airflow-apiserver` | http://localhost:8080 | admin / admin |
| dbt docs serve | http://localhost:8090 | — |
| `omega3-postgres` | localhost:5432 | postgres / postgres_secret_2024 |
| `omega3-opensearch` | http://localhost:9200 | без auth |
| `omega3-atrocore` (RDM/MDM) | http://localhost:8087 | admin / admin (после установки) |

OpenMetadata healthcheck: http://localhost:8586/healthcheck

Airflow 3.0 использует `SimpleAuthManager` (`AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_ALL_ADMINS=true`) —
все пользователи считаются админами, пароль admin/admin для UI/API.

---

## Базы данных PostgreSQL

```
postgres (superuser)
├── demo                ← источник данных (загружен из demo-20250901-2y.sql.gz)
│   ├── schema: bookings        (Postgres Pro airline demo, 9 таблиц, ~30M строк)
│   │   ├── flights             214 867 строк
│   │   ├── tickets             2 949 857 строк
│   │   ├── bookings            2 111 110 строк
│   │   └── boarding_passes, seats, airports_data, airplanes_data, ticket_flights
│   ├── schema: public_staging  (dbt views)
│   └── schema: public_marts    (dbt tables — daily_flight_stats, 1225 строк)
├── airflow_db          ← метаданные Airflow (user: airflow)
├── openmetadata_db     ← метаданные OM     (user: openmetadata)
└── atrocore_db         ← AtroCore RDM/MDM (user: atrocore / atrocore_secret_2026)
    └── schema: public  (Country, Currency, AirportRefData + служебные таблицы)
```

---

## dbt проект

**Профиль:** `omega3` → target `prod` → БД `demo` через env vars из docker-compose.
Threads = 8 (`DBT_THREADS=8`).

**Модели:**
```
bookings.flights  (source)
    └─► public_staging.stg_flights         (VIEW)
            └─► public_marts.daily_flight_stats  (TABLE)
                Метрика: кол-во рейсов + средний/макс delay по (flight_date, status)
            └─► public_marts.metricflow_time_spine  (TABLE)
                Time spine для MetricFlow: 2015-01-01..2027-12-31 (daily)
```

**MetricFlow семантический слой** (`dbt/models/marts/metrics.yml`):
- Semantic model `flights_semantic` на `stg_flights` — entity: flight, dims: flight_date/status/hour
- Metric `total_flights` (COUNT, DAY) — COUNT(flight_id)
- Metric `avg_departure_delay_minutes` (AVERAGE, DAY) — AVG(departure_delay_min)
- `semantic_manifest.json` генерируется при `dbt parse`

**dbt-metricflow CLI** (`mf`) — версия 0.11.0, требует dbt-core~=1.10:
```bash
# Список метрик
docker exec omega3-airflow-apiserver bash -lc 'cd /opt/airflow/dbt && mf list metrics'

# Запрос метрики по месяцам
docker exec omega3-airflow-apiserver bash -lc '
  cd /opt/airflow/dbt && mf query \
    --metrics total_flights \
    --group-by metric_time__month \
    --order metric_time__month --limit 12'

# Запрос средней задержки по статусу и месяцу
docker exec omega3-airflow-apiserver bash -lc '
  cd /opt/airflow/dbt && mf query \
    --metrics avg_departure_delay_minutes \
    --group-by flight__status,metric_time__month \
    --order metric_time__month --limit 12'
```

**Ingestion метрик в OpenMetadata** (`airflow/scripts/ingest_dbt_metrics.py`):
- Читает `semantic_manifest.json`, создаёт/обновляет Metric entities через OM REST API (PUT upsert)
- Запускается в DAG `om_ingestion_dag` после `ingest_dbt_lineage`
- Ручной запуск: `docker exec omega3-airflow-apiserver python3 /opt/airflow/scripts/ingest_dbt_metrics.py`

**Запуск dbt вручную:**
```bash
docker exec omega3-airflow-apiserver bash -lc '
  cd /opt/airflow/dbt && dbt deps --no-use-colors
  dbt run --no-use-colors --threads 8
  dbt test --no-use-colors
  dbt docs generate --no-use-colors
'
```

**dbt docs serve (фоново, порт 8090):**
```bash
docker exec -d omega3-airflow-apiserver bash -lc '
  cd /opt/airflow/dbt && dbt docs serve --port 8090 --host 0.0.0.0
'
```

Папки `dbt/logs/`, `dbt/target/`, `dbt/dbt_packages/` должны быть записываемы от uid 50000.
Если не пишется — `docker exec -u 0 omega3-airflow-apiserver chmod -R 777 /opt/airflow/dbt`.

---

## Airflow DAGs

| DAG | Расписание | Что делает |
|-----|-----------|------------|
| `dbt_daily_run`  | `0 6 * * *` | deps → run staging → run marts → test → docs generate |
| `om_ingestion_dag` | `0 7 * * *` | ingest Postgres metadata → ingest dbt lineage в OM |

Airflow 3.0 особенности:
- Оператор `api-server` (не `webserver`) + отдельный `dag-processor`
- Операторы берём из `airflow.providers.standard.operators.*`
- В DAG-ах `schedule=` (не `schedule_interval=`)

---

## OpenMetadata ingestion

Запуск через обёртки (они инжектят свежий JWT перед стартом workflow):

```bash
# Метаданные таблиц PostgreSQL
docker exec omega3-airflow-apiserver python3 /opt/airflow/scripts/run_om_ingestion.py \
  -c /opt/airflow/ingestion/postgres_service.yaml

# dbt lineage
docker exec omega3-airflow-apiserver python3 /opt/airflow/scripts/run_dbt_ingestion.py \
  -c /opt/airflow/ingestion/dbt_lineage.yaml
```

JWT берётся из `$OM_JWT_TOKEN` либо через login `/api/v1/users/login`
(`admin@open-metadata.org` / `admin`, пароль base64).

OpenLineage от Airflow → OM настроен через `AIRFLOW__OPENLINEAGE__TRANSPORT` на
`http://openmetadata-server:8585/api/v1/lineage/openlineage`, namespace = `omega3`.

---

## Критичные зависимости

- **`openmetadata-ingestion[postgres]==1.12.5.3`** — ставит `dbt-core==1.11.7`
  поверх наших пинов 1.9.4. Это нормально: dbt 1.11 манифесты парсятся OM 1.12.
- **`collate-dbt-artifacts-parser>=0.1`** — ОБЯЗАТЕЛЕН для dbt lineage в OM 1.12.
  Публичный `dbt-artifacts-parser` НЕ работает, несмотря на похожее имя.
- **`AIRFLOW__CORE__AUTH_MANAGER`** — должен быть
  `airflow.api_fastapi.auth.managers.simple.simple_auth_manager.SimpleAuthManager`,
  иначе UI Airflow 3.0 не стартует.
- **`SimpleAuthManager`** кидает админа на любой логин; если `SIMPLE_AUTH_MANAGER_ALL_ADMINS=true`.

---

## Загрузка дампа

```bash
bash scripts/load_dump.sh /home/daurena2609/dumps/demo-20250901-2y.sql.gz
```

Скрипт:
1. Определяет формат (plain SQL / pg_dump custom) по первым байтам
2. Грузит в БД `demo` (plain SQL создаёт её сам через CREATE DATABASE)
3. Даёт права `demo_user` на схему `bookings` и создаёт `public_staging` + `public_marts`
4. Показывает топ-10 таблиц по размеру

Warnings про `transaction_timeout` в логах дампа — безобидны (дамп из Postgres 17+).

---

## Внешний проект KRISHA_DWH (Postgres + dbt)

Параллельно стек OMEGA-3 каталогизирует второй проект, лежащий в `~/KRISHA_DWH`
(собственный postgres на хосте `:5433`, собственный dbt-проект на dbt-core 1.9).

Подключение:
- KRISHA postgres достижим из контейнеров OMEGA-3 по `host.docker.internal:5433`
  (см. `ingestion/krisha_*.yaml`).
- Каталог `~/KRISHA_DWH/dbt` примонтирован read-only в `/opt/airflow/krisha_dbt`
  во все airflow-сервисы (см. `docker-compose.yml`, секция `x-airflow-common.volumes`).
  Так `krisha_dbt_lineage.yaml` читает свежий `target/manifest.json` +
  `target/catalog.json`, сгенерированные на хосте через `dbt parse` +
  `dbt docs generate` в venv `~/.venvs/krisha-dbt`.

DAG `krisha_om_ingestion_dag` (07:30 UTC ежедневно) гоняет:
1. `run_om_ingestion.py -c /opt/airflow/ingestion/krisha_postgres_metadata.yaml` —
   таблицы из схем `raw / stg / marts / marts_dbt / marts_dv`.
2. `run_dbt_ingestion.py -c /opt/airflow/ingestion/krisha_dbt_lineage.yaml` —
   dbt models + связи между ними.

Ручной запуск идентичен OMEGA-3-овскому — те же скрипты, другие YAML-конфиги:

```bash
docker exec omega3-airflow-apiserver python3 \
  /opt/airflow/scripts/run_om_ingestion.py \
  -c /opt/airflow/ingestion/krisha_postgres_metadata.yaml

docker exec omega3-airflow-apiserver python3 \
  /opt/airflow/scripts/run_dbt_ingestion.py \
  -c /opt/airflow/ingestion/krisha_dbt_lineage.yaml
```

В OM этот источник появляется как Database Service `krisha_dwh` (Postgres).
Lineage от `stg.listings` идёт через DV-stage views в `marts_dv.{hub,lnk,sat}_*`
и в dbt-views `marts_dbt.{listings_current, listing_price_events}`.
Таблицы `marts.dim_listing` / `marts.fact_listing_price_history` строятся
Airflow-ом самого KRISHA_DWH (не dbt) — для lineage по ним подключай
`krisha_postgres_lineage.yaml` (требует pg_stat_statements в БД krisha) либо
OpenLineage от krisha-airflow.

---

## Структура проекта

```
OMEGA-3/
├── CLAUDE.md                   ← этот файл
├── docker-compose.yml          ← весь стек (7 сервисов)
├── Dockerfile.airflow          ← Airflow 3.0.2 + dbt + OM ingestion + collate parser
├── env.example                 ← скопировать в .env перед запуском
├── dbt/
│   ├── dbt_project.yml / profiles.yml / packages.yml
│   └── models/
│       ├── staging/  stg_flights.sql, sources.yml, schema.yml
│       └── marts/    daily_flight_stats.sql, schema.yml
├── airflow/
│   ├── dags/         dbt_daily_run.py, om_ingestion_dag.py
│   ├── plugins/
│   └── scripts/      run_om_ingestion.py, run_dbt_ingestion.py
├── ingestion/
│   ├── postgres_service.yaml
│   └── dbt_lineage.yaml
└── scripts/
    ├── init-db.sql             ← создание users/БД при первом старте postgres
    ├── load_dump.sh            ← загрузка дампа + гранты
    └── reset_om_password.py    ← сброс пароля OM admin (при необходимости)
```

---

## AtroCore — Reference Data Management

**AtroCore** (https://github.com/atrocore/atrocore) — open-source платформа MDM/RDM/PIM
на PHP 8.4 + Apache. В OMEGA-3 используется как централизованный store справочников
(коды стран, валюты, IATA-коды аэропортов, ETL-статусы, бизнес-таксономии),
которые потом каталогизируются в OpenMetadata через ingestion.

**Базовые координаты:**

| Параметр | Значение |
|----------|----------|
| URL | http://localhost:8087 |
| Логин (после первичной установки) | `admin` / `admin` (можно поменять при installer'е) |
| БД | `omega3-postgres` → `atrocore_db` (user: `atrocore` / `atrocore_secret_2026`) |
| Skeleton-вариант | `atrocore` (чистое ядро, без PIM) |
| REST API | `http://localhost:8087/api/v1/{Entity}` (Basic Auth) |

**Архитектура:**

```
Browser → http://localhost:8087 → omega3-atrocore (Apache + PHP 8.4)
                                         │
                                         ▼ pdo_pgsql
                                  omega3-postgres:5432
                                         │
                                         ▼ atrocore_db
                                  schema: public
                                  ├── country (RDM-сущность)
                                  ├── currency (RDM-сущность)
                                  ├── airport_ref_data (RDM-сущность)
                                  └── user/team/role/note/... (служебные)
```

Каждая сущность (Entity), созданная через UI **Settings → Entity Manager** или через
REST API `POST /api/v1/EntityManager`, автоматически получает таблицу в `public`-схеме
с автогенерируемой схемой колонок. AtroCore делает миграции через свой console.

**Подключение к БД (psql):**

```bash
# Из контейнера postgres
docker exec -it omega3-postgres psql -U atrocore -d atrocore_db

# С хоста (порт 5432 проброшен наружу)
PGPASSWORD=atrocore_secret_2026 psql -h localhost -p 5432 -U atrocore -d atrocore_db

# Список справочных таблиц
docker exec omega3-postgres psql -U atrocore -d atrocore_db -c "\dt"

# Содержимое справочника
docker exec omega3-postgres psql -U atrocore -d atrocore_db -c "SELECT * FROM country LIMIT 10;"
```

**REST API (примеры):**

```bash
# Список стран
curl -u admin:admin http://localhost:8087/api/v1/Country?maxSize=10

# Создать запись
curl -u admin:admin -X POST http://localhost:8087/api/v1/Country \
  -H 'Content-Type: application/json' \
  -d '{"name":"Kazakhstan","code":"KZ","phoneCode":"+7"}'

# Обновить (PATCH по id)
curl -u admin:admin -X PATCH http://localhost:8087/api/v1/Country/{id} \
  -H 'Content-Type: application/json' \
  -d '{"phoneCode":"+7"}'
```

**Сборка/пересборка:**

```bash
docker compose build atrocore   # 5–10 минут (apt-get + composer install)
docker compose up -d atrocore
```

После старта зайти на http://localhost:8087, пройти веб-installer (`data/config.php`
уже преднастроен на `omega3-postgres:5432/atrocore_db`).

**Ingestion в OpenMetadata:**

```bash
docker exec omega3-airflow-apiserver python3 \
  /opt/airflow/scripts/run_om_ingestion.py \
  -c /opt/airflow/ingestion/atrocore_postgres_metadata.yaml
```

DAG `atrocore_om_ingestion_dag` (08:00 UTC ежедневно) делает то же по расписанию.
В OM появится Database Service `atrocore` → `atrocore_db` → схема `public` с таблицами
справочников.

**Файлы:**
- `atrocore/Dockerfile` — кастомный билд (адаптация официального с
  https://gitlab.atrocore.com/atrocore/docker)
- `atrocore/scripts/{prepare-pim.sh,prepare-pim.php,skeleton-check.sh}` — клонирование
  skeleton-репозитория и `composer install` на этапе сборки
- `atrocore/startup.sh` — runtime-перезапись `data/config.php`-host из env
- `scripts/init-atrocore-db.sql` — идемпотентное создание `atrocore_db` + пользователя
- `ingestion/atrocore_postgres_metadata.yaml` — OM ingestion-конфиг
- `airflow/dags/atrocore_om_ingestion_dag.py` — DAG расписания

---

## AI Chat (Gemini + OpenMetadata MCP)

В UI OpenMetadata встроен плавающий AI-виджет (правый нижний угол, кнопка «AI»),
который не требует переключения вкладок. Ассистент отвечает на вопросы про
каталог: ищет таблицы, lineage, тесты качества, термины глоссария, владельцев.

**Архитектура:**

```
Browser → http://localhost:8585 (nginx)
  ├── /                  → openmetadata-server:8585 (HTML + inject widget.js)
  ├── /omega3-ai/widget.js → static (плавающая кнопка + iframe)
  └── /omega3-ai/        → ai-chat:8500 (FastAPI)
                              ├─► Gemini API (gemini-2.0-flash, бесплатно)
                              └─► OM MCP (если включён) или OM REST (fallback)
```

**LLM:** Google Gemini 2.0 Flash (бесплатный tier — 1M токенов/сутки, 15 RPM).
Ключ в `.env` как `GEMINI_API_KEY`. Модель меняется через `GEMINI_MODEL`.

**Tools:** ai-chat пытается использовать MCP-сервер OpenMetadata (`/mcp`). Если
MCP App в OM не установлен или JWT нет — автоматически переключается на
встроенные REST-tools (search_metadata, get_table, get_lineage, list_glossary_terms,
get_test_results, list_databases). Тег в шапке чата показывает текущий backend.

**Первичная настройка:**

```bash
# 1) Скопировать env.example → .env и вписать GEMINI_API_KEY
cp env.example .env
# отредактировать .env (GEMINI_API_KEY=AIza...)

# 2) Поднять стек (ai-chat сразу работает в REST-режиме через admin login)
docker compose up -d

# 3) Получить JWT для bot-юзера и записать в .env (опционально, для MCP)
python3 scripts/setup_ai_chat.py
docker compose restart ai-chat

# 4) (Опционально) Включить MCP Application в OM:
#    Settings → Applications → Add Apps → MCP → Install → Schedule
#    После этого ai-chat подхватит MCP-tools автоматически.
```

**Использование:** открыть http://localhost:8585 → кнопка «AI» в правом нижнем
углу → задать вопрос на русском, например:
- «Какие таблицы есть в схеме bookings?»
- «Покажи lineage daily_flight_stats на 2 уровня вглубь»
- «Какой статус у тестов качества по таблице flights?»

**Файлы:**
- `ai-chat/main.py` — FastAPI + Gemini + MCP/REST tools
- `ai-chat/static/chat.{html,css,js}` — UI iframe
- `nginx/nginx.conf` + `nginx/widget.js` — proxy + плавающий виджет
- `scripts/setup_ai_chat.py` — выдача bot-JWT, проверка MCP App

---

## Git

Проект готов к разработке в GitHub. Секреты (`.env`, `*.env`, дампы) в `.gitignore`.
Пароли в `docker-compose.yml` — dev-дефолты; для продакшена вынести в `.env`.
