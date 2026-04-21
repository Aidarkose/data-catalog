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
| `omega3-openmetadata` | http://localhost:8585 | admin@open-metadata.org / admin |
| `omega3-airflow-apiserver` | http://localhost:8080 | admin / admin |
| dbt docs serve | http://localhost:8090 | — |
| `omega3-postgres` | localhost:5432 | postgres / postgres_secret_2024 |
| `omega3-opensearch` | http://localhost:9200 | без auth |

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
└── openmetadata_db     ← метаданные OM     (user: openmetadata)
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
```

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

## Git

Проект готов к разработке в GitHub. Секреты (`.env`, `*.env`, дампы) в `.gitignore`.
Пароли в `docker-compose.yml` — dev-дефолты; для продакшена вынести в `.env`.
