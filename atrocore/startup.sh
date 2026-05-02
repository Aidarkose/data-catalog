#!/bin/sh

set -e

# Если конфиг уже существует, перезаписываем host:port из env (на случай,
# если контейнер пересоздан со свежим volume/новой БД).
CFG="/var/www/${PRODUCTION_DOMAIN:-localhost}/data/config.php"
if [ -f "$CFG" ] && [ -n "$DB_HOST" ]; then
  sed -i "s/'host' => '[^']*'/'host' => '$DB_HOST'/g" "$CFG"
  sed -i "s/'port' => '[^']*'/'port' => '${DB_PORT:-5432}'/g" "$CFG"
fi

cron
apache2-foreground
