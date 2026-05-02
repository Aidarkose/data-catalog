#!/usr/bin/env bash
# Создаёт три справочника AtroCore (Country, Currency, AirportRefData)
# и заполняет их через REST API. Запускать ПОСЛЕ установки AtroCore через UI
# (т.к. installer создаёт admin-пользователя).
#
# Usage:
#   AUTH=admin:admin BASE=http://localhost:8087 bash seed_reference_data.sh

set -euo pipefail

BASE="${BASE:-http://localhost:8087}"
AUTH="${AUTH:-admin:admin}"

post() {
  local entity="$1"; shift
  local payload="$1"
  curl -fsS -u "$AUTH" -X POST "$BASE/api/v1/$entity" \
    -H 'Content-Type: application/json' \
    -d "$payload" | jq -r '.id // .name // .'
}

# --- Country -----------------------------------------------------------------
echo ">>> Seed Country"
for row in \
  '{"name":"Kazakhstan","code":"KZ","phoneCode":"+7","currencyCode":"KZT"}' \
  '{"name":"Russia","code":"RU","phoneCode":"+7","currencyCode":"RUB"}' \
  '{"name":"United States","code":"US","phoneCode":"+1","currencyCode":"USD"}' \
  '{"name":"Germany","code":"DE","phoneCode":"+49","currencyCode":"EUR"}' \
  '{"name":"Turkey","code":"TR","phoneCode":"+90","currencyCode":"TRY"}' \
  '{"name":"China","code":"CN","phoneCode":"+86","currencyCode":"CNY"}' \
  '{"name":"United Kingdom","code":"GB","phoneCode":"+44","currencyCode":"GBP"}'
do
  post Country "$row"
done

# --- Currency ----------------------------------------------------------------
echo ">>> Seed Currency"
for row in \
  '{"name":"Kazakhstani Tenge","code":"KZT","symbol":"₸"}' \
  '{"name":"Russian Ruble","code":"RUB","symbol":"₽"}' \
  '{"name":"US Dollar","code":"USD","symbol":"$"}' \
  '{"name":"Euro","code":"EUR","symbol":"€"}' \
  '{"name":"Turkish Lira","code":"TRY","symbol":"₺"}' \
  '{"name":"Chinese Yuan","code":"CNY","symbol":"¥"}' \
  '{"name":"British Pound","code":"GBP","symbol":"£"}'
do
  post Currency "$row"
done

# --- AirportRefData ----------------------------------------------------------
echo ">>> Seed AirportRefData"
for row in \
  '{"name":"Almaty Intl","iata":"ALA","icao":"UAAA","cityRu":"Алматы","cityEn":"Almaty","countryCode":"KZ"}' \
  '{"name":"Astana Intl","iata":"NQZ","icao":"UACC","cityRu":"Астана","cityEn":"Astana","countryCode":"KZ"}' \
  '{"name":"Sheremetyevo","iata":"SVO","icao":"UUEE","cityRu":"Москва","cityEn":"Moscow","countryCode":"RU"}' \
  '{"name":"JFK","iata":"JFK","icao":"KJFK","cityRu":"Нью-Йорк","cityEn":"New York","countryCode":"US"}' \
  '{"name":"Frankfurt Main","iata":"FRA","icao":"EDDF","cityRu":"Франкфурт","cityEn":"Frankfurt","countryCode":"DE"}' \
  '{"name":"Istanbul","iata":"IST","icao":"LTFM","cityRu":"Стамбул","cityEn":"Istanbul","countryCode":"TR"}' \
  '{"name":"Beijing Capital","iata":"PEK","icao":"ZBAA","cityRu":"Пекин","cityEn":"Beijing","countryCode":"CN"}' \
  '{"name":"Heathrow","iata":"LHR","icao":"EGLL","cityRu":"Лондон","cityEn":"London","countryCode":"GB"}'
do
  post AirportRefData "$row"
done

echo ">>> Done."
