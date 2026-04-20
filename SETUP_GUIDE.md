# Data Catalog — Руководство по запуску

## Архитектура

```
                    ┌──────────────────────────────────┐
                    │    data-catalog-net (Docker)     │
                    │                                  │
  ┌─────────────┐   │  ┌─────────────────────────┐    │
  │ VS Code     │   │  │   OpenMetadata :8585     │    │
  │ (Windows)   │   │  │   Data Catalog UI & API  │    │
  │ Remote WSL ─┼───┼─▶│   admin / Admin@1234     │    │
  └─────────────┘   │  └─────────┬───────────────┘    │
                    │            │                     │
  ┌─────────────┐   │  ┌─────────▼───────────────┐    │
  │ Browser     │   │  │   Airflow :8080          │    │
  │             │◀──┼──│   admin / admin          │    │
  └─────────────┘   │  │   ├─ om_ingestion_dag    │    │
                    │  │   └─ dbt_daily_run        │    │
                    │  └─────────┬───────────────┘    │
                    │            │ runs dbt            │
                    │  ┌─────────▼───────────────┐    │
                    │  │   PostgreSQL 16 :5432    │    │
                    │  │   ├─ demo_db  (source)   │    │
                    │  │   ├─ airflow_db           │    │
                    │  │   └─ openmetadata_db      │    │
                    │  └─────────────────────────-┘    │
                    │                                  │
                    │  ┌──────────────────────────┐    │
                    │  │   OpenSearch :9200        │    │
                    │  └──────────────────────────┘    │
                    └──────────────────────────────────┘

Data Lineage flow:
  PostgreSQL (demo_db) → dbt (staging → marts) → OpenMetadata lineage graph
  OpenLineage events: Airflow → OpenMetadata API
```

## Шаги запуска

### Шаг 1: Установка Docker

```bash
cd ~/data-catalog
bash scripts/setup.sh
# После установки:
newgrp docker   # или выйти и войти снова
```

### Шаг 2: Инициализация .env

```bash
cp env.example .env
cp gitignore.txt .gitignore
git init && git add . && git commit -m "feat: initial data catalog project"
```

### Шаг 3: Запуск стека

```bash
cd ~/data-catalog
docker compose up -d

# Следить за логами:
docker compose logs -f openmetadata-server
docker compose logs -f airflow-webserver
```

Проверка готовности (займёт 3-7 минут):
```bash
docker compose ps
```

### Шаг 4: Загрузка дампа

```bash
bash scripts/load_dump.sh /home/daurena2609/dumps/demo-20250901-2y.sql.gz
bash scripts/discover_schema.sh
```

### Шаг 5: Запуск dbt

```bash
# Ручной запуск dbt внутри airflow-контейнера:
docker exec dc-airflow-webserver bash -c "
  cd /opt/airflow/dbt &&
  dbt deps &&
  dbt run --threads 8 &&
  dbt docs generate
"
```

### Шаг 6: Просмотр dbt lineage

```bash
# Запуск dbt docs serve (на хосте WSL):
docker exec -it dc-airflow-webserver bash -c "
  dbt docs serve --project-dir /opt/airflow/dbt --port 8090 --host 0.0.0.0
"
# Открыть: http://localhost:8090
```

### Шаг 7: Ингestion в OpenMetadata

Через Airflow UI (http://localhost:8080):
1. Включить DAG `om_ingestion_dag`
2. Нажать "Trigger DAG"

Или вручную:
```bash
docker exec dc-airflow-webserver metadata ingest -c /opt/airflow/ingestion/postgres_service.yaml
docker exec dc-airflow-webserver metadata ingest -c /opt/airflow/ingestion/dbt_lineage.yaml
```

### Шаг 8: Проверка lineage в OpenMetadata

1. Открыть http://localhost:8585
2. Войти: admin / Admin@1234
3. Перейти: Explore → Tables → demo_db → поискать `daily_table_stats`
4. Вкладка "Lineage" — граф зависимостей

## Credentials

| Service        | URL                    | Login         | Password    |
|----------------|------------------------|---------------|-------------|
| OpenMetadata   | http://localhost:8585  | admin         | Admin@1234  |
| Airflow        | http://localhost:8080  | admin         | admin       |
| PostgreSQL     | localhost:5432         | postgres      | postgres_secret_2024 |
| dbt docs       | http://localhost:8090  | —             | —           |

## VS Code

```bash
# В WSL2 терминале:
cd ~/data-catalog
code .
# VS Code откроется с Remote WSL и загрузит рекомендованные расширения
```

## GitHub

```bash
cd ~/data-catalog
git init
git add .
git commit -m "feat: initial data catalog stack"
# Создать репозиторий на GitHub и:
git remote add origin https://github.com/YOUR_USER/data-catalog.git
git push -u origin main
```
