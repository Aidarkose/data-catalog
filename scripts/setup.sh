#!/usr/bin/env bash
# ===========================================================
# setup.sh — First-time setup: install Docker + start stack
# Run as: bash scripts/setup.sh
# ===========================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=================================================="
echo "  Data Catalog Setup"
echo "  Stack: OpenMetadata + Airflow + dbt + Postgres16"
echo "=================================================="
echo ""

# 1. Install Docker Engine if not present
if ! command -v docker &>/dev/null; then
  echo "==> Installing Docker Engine..."
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  sudo systemctl enable docker
  sudo systemctl start docker
  echo "==> Docker installed. You may need to log out and back in."
  echo "    Or run: newgrp docker"
  echo ""
else
  echo "✅ Docker already installed: $(docker --version)"
fi

# 2. Ensure docker compose v2
if ! docker compose version &>/dev/null; then
  echo "==> Installing docker compose plugin..."
  sudo apt-get update -q
  sudo apt-get install -y docker-compose-plugin
else
  echo "✅ Docker Compose: $(docker compose version)"
fi

# 3. System tunables required by OpenSearch
echo "==> Setting vm.max_map_count for OpenSearch..."
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf > /dev/null

# 4. Copy env template
cd "$PROJECT_DIR"
if [[ ! -f .env ]]; then
  cp env.example .env
  echo "==> Created .env from env.example"
fi

# 5. Make scripts executable
chmod +x scripts/*.sh

# 6. Build custom Airflow image
echo ""
echo "==> Building custom Airflow image (dbt + OM ingestion)..."
echo "    This may take 5-10 minutes on first run."
docker compose build airflow-webserver

echo ""
echo "=================================================="
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Start services:  docker compose up -d"
echo "  2. Check health:    docker compose ps"
echo "  3. Load dump:       bash scripts/load_dump.sh"
echo "  4. Open UIs:"
echo "     - OpenMetadata:  http://localhost:8585"
echo "     - Airflow:       http://localhost:8080"
echo "=================================================="
