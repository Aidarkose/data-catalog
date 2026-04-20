# OMEGA-3 — Data Catalog

## Что это

Локальный Data Catalog с Data Lineage на WSL2 Ubuntu (Windows).
Стек: **OpenMetadata 1.6.3 + Airflow 2.9.3 + dbt 1.8.7 + PostgreSQL 16 + OpenSearch 2.19.1**.

Все сервисы поднимаются одной командой: `docker compose up -d`

---

## Среда выполнения

- WSL2 Ubuntu 20.04, hostname `enigma`, user `daurena2609`
- Docker Desktop 28.5.1 (Windows) с WSL2 integration — **не** `sudo service docker start`
- Docker команды требуют `sg docker -c "..."` если сессия открыта без `newgrp docker`
- VS Code: `code .` из WSL открывает Remote WSL

---

## Сервисы и порты

| Контейнер | URL | Логин / Пароль |
|-----------|-----|----------------|
| `dc-openmetadata` | http://localhost:8585 | admin / Admin@1234 |
| `dc-airflow-webserver` | http://localhost:8080 | admin / admin |
| dbt docs (ручной запуск) | http://localhost:8090 | — |
| `dc-postgres` | localhost:5432 | postgres / postgres_secret_2024 |
| `dc-opensearch` | http://localhost:9200 | без auth |

OpenMetadata admin API (healthcheck): http://localhost:8586/healthcheck

---

## Базы данных PostgreSQL

```
postgres (superuser)
├── demo            ← источник данных (загружен из дампа demo-20250901-2y.sql.gz)
│   └── schema: bookings
│       ├── flights        135 571 строк
│       ├── tickets      21 095 265 строк
│       ├── bookings      9 706 657 строк
│       ├── boarding_passes, seats, routes, airports_data, airplanes_data, segments
│       └── (dbt создаёт: public_staging.*, public_marts.*)
├── airflow_db      ← метаданные Airflow  (user: airflow / airflow_secret_2024)
└── openmetadata_db ← метаданные OM       (user: openmetadata / openmetadata_secret_2024)
```

demo_db (пустая, не используется — дамп создал отдельную БД `demo`).

---

## dbt проект

**Профиль:** `data_catalog` → target `prod` → подключается к БД `demo` через env vars.

**Модели (8 потоков):**
```
bookings.flights  (source)
    └─► staging.stg_flights       (VIEW)
            └─► marts.daily_flight_stats  (TABLE, 1225 строк)
                Метрика: количество рейсов по статусу и дате
```

**Запуск dbt вручную:**
```bash
docker exec dc-airflow-webserver dbt --no-use-colors run \
  --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt --threads 8
```

**dbt docs serve:**
```bash
docker exec -d dc-airflow-webserver dbt docs serve \
  --project-dir /opt/airflow/dbt --profiles-dir /opt/airflow/dbt \
  --port 8090 --host 0.0.0.0
```

Папки `dbt/logs/` и `dbt/target/` должны быть `chmod 777` — иначе Airflow (uid 50000) не пишет.

---

## Airflow DAGs

| DAG | Расписание | Что делает |
|-----|-----------|------------|
| `dbt_daily_run` | `0 6 * * *` | deps → run staging → run marts → test → docs generate |
| `om_ingestion_dag` | `0 7 * * *` | ingest postgres metadata → ingest dbt lineage в OM |

---

## OpenMetadata ingestion

Ingestion запускается через патч-скрипты (не через `metadata ingest` напрямую):

```bash
# Метаданные таблиц PostgreSQL → OpenMetadata
docker exec dc-airflow-webserver python3 /opt/airflow/scripts/run_om_ingestion.py \
  -c /opt/airflow/ingestion/postgres_service.yaml

# dbt lineage → OpenMetadata
docker exec dc-airflow-webserver python3 /opt/airflow/scripts/run_dbt_ingestion.py \
  -c /opt/airflow/ingestion/dbt_lineage.yaml
```

JWT токен в `ingestion/*.yaml` истекает через ~1 час. Получить новый:
```bash
B64=$(python3 -c "import base64; print(base64.b64encode(b'Admin@1234').decode())")
curl -s -X POST http://localhost:8585/api/v1/users/login \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"admin@open-metadata.org\",\"password\":\"$B64\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])"
```

---

## Известные проблемы (не трогать без необходимости)

**cryptography конфликт** — Airflow 2.9.3 ставит `cryptography 46.x`, OM ingestion требует `<45` через `msal`. Патч в `airflow/scripts/run_om_ingestion.py` заменяет `inject_query_header` чтобы использовать `importlib.metadata` вместо `pkg_resources.require()`. Без патча ingestion падает на `CheckAccess`.

**dbt-artifacts-parser** — версия 0.13.1 не парсит `run_results.json` от dbt 1.8. Поле `dbtRunResultsFilePath` убрано из `ingestion/dbt_lineage.yaml`.

**OM admin пароль** — хранится bcrypt в `openmetadata_db`. Для сброса:
```bash
docker cp scripts/reset_om_password.py dc-airflow-webserver:/tmp/
docker exec dc-airflow-webserver python3 /tmp/reset_om_password.py
docker restart dc-openmetadata
```

**DNS в WSL2** — внешние HTTPS иногда не резолвятся при первом запуске. Повторить запрос. Docker настроен на `NetworkType: nat` в `C:\Users\daure\AppData\Roaming\Docker\settings-store.json`.

---

## Структура проекта

```
OMEGA-3/
├── CLAUDE.md                   ← этот файл
├── docker-compose.yml          ← весь стек
├── Dockerfile.airflow          ← Airflow + dbt 1.8.7 + OM ingestion 1.6.3
├── env.example                 ← скопировать в .env перед запуском
├── dbt/
│   ├── dbt_project.yml / profiles.yml / packages.yml
│   └── models/
│       ├── staging/  stg_flights.sql, stg_table_catalog.sql, sources.yml
│       └── marts/    daily_flight_stats.sql, daily_table_stats.sql
├── airflow/
│   ├── dags/         dbt_daily_run.py, om_ingestion_dag.py
│   └── scripts/      run_om_ingestion.py, run_dbt_ingestion.py
├── ingestion/
│   ├── postgres_service.yaml   ← OM connector: PostgreSQL
│   └── dbt_lineage.yaml        ← OM connector: dbt lineage
└── scripts/
    ├── init-db.sql             ← создаётся при первом старте postgres
    ├── load_dump.sh            ← bash scripts/load_dump.sh /path/to/dump.sql.gz
    ├── reset_om_password.py    ← сброс пароля OM admin
    └── discover_schema.sh      ← обновляет dbt/models/staging/sources.yml
```

---

## Git

```bash
git log --oneline        # один коммит: initial stack
git remote -v            # origin → https://github.com/Aidarkose/data-catalog.git
```
