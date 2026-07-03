#!/usr/bin/env bash
# Bootstrap the local services and run the end-to-end smoke test.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi

CONDA_ENV="argus"
PY_VERSION="3.11"

DB_NAME="${POSTGRES_DB:?Set POSTGRES_DB in .env}"
DB_USER="${POSTGRES_USER:?Set POSTGRES_USER in .env}"
DB_PASS="${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}"
DB_PORT="${POSTGRES_PORT:-5432}"
AUTH_PASSWORD="${DEV_AUTH_PASSWORD:?Set DEV_AUTH_PASSWORD in .env}"

RAG_PORT=8081
SQL_PORT=8082
API_PORT=8083
GW_PORT=8080

SYNTHESIS_MODEL="${SYNTHESIS_MODEL:-command-r:35b}"
PLANNER_MODEL="${PLANNER_MODEL:-command-r:35b}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434/v1/chat/completions}"

LOG_DIR="$REPO_ROOT/logs"
mkdir -p "$LOG_DIR"

info()  { echo "  [INFO]  $*"; }
ok()    { echo "  [ OK ]  $*"; }
die()   { echo "  [FAIL]  $*" >&2; exit 1; }

wait_port() {
  local port=$1 label=$2 tries=30
  for i in $(seq 1 $tries); do
    if curl -sf "http://localhost:$port/health" >/dev/null 2>&1; then
      ok "$label is up"
      return 0
    fi
    sleep 3
  done
  die "$label did not become healthy on port $port after $((tries*3))s"
}

echo ""
echo "=== 1. Conda environment ==="

if conda env list | grep -q "^$CONDA_ENV "; then
  info "conda env '$CONDA_ENV' already exists, skipping create"
else
  info "Creating conda env '$CONDA_ENV' (Python $PY_VERSION) ..."
  conda create -y -n "$CONDA_ENV" python="$PY_VERSION"
fi

# Conda is not initialized in non-interactive shells by default.
eval "$(conda shell.bash hook)"
conda activate "$CONDA_ENV"

info "Installing all Python dependencies ..."
pip install --quiet -r "$REPO_ROOT/requirements.txt"
ok "Dependencies installed"

echo ""
echo "=== 2. PostgreSQL ==="

if ! pg_isready -U "$DB_USER" -p "$DB_PORT" >/dev/null 2>&1; then
  info "Starting PostgreSQL ..."
  sudo service postgresql start || sudo pg_ctlcluster 16 main start || die "Cannot start PostgreSQL"
fi
ok "PostgreSQL running"

# Existing local roles may not have a password yet.
sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" \
  | grep -q 1 || sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"

info "Running schema init ..."
sudo -u postgres psql "$DB_NAME" < "$REPO_ROOT/infra/postgres-init/init.sql"
ok "Schema ready"

echo ""
echo "=== 3. Redis ==="

if ! redis-cli ping >/dev/null 2>&1; then
  info "Starting Redis ..."
  sudo service redis-server start || sudo redis-server --daemonize yes
fi
ok "Redis running"

echo ""
echo "=== 4. JWT keys ==="

if [ ! -f "$REPO_ROOT/gateway/private.pem" ]; then
  openssl genrsa -out "$REPO_ROOT/gateway/private.pem" 2048
  openssl rsa -in "$REPO_ROOT/gateway/private.pem" -pubout -out "$REPO_ROOT/gateway/public.pem"
  ok "Keys generated"
else
  ok "Keys already exist"
fi

echo ""
echo "=== 5. Starting services ==="

# Avoid binding over stale local service processes.
pkill -f "uvicorn app.main" 2>/dev/null || true
sleep 1

DB_SYNC="postgresql+psycopg2://$DB_USER:$DB_PASS@localhost:$DB_PORT/$DB_NAME"
DB_ASYNC="postgresql+asyncpg://$DB_USER:$DB_PASS@localhost:$DB_PORT/$DB_NAME"
DB_PLAIN="postgresql://$DB_USER:$DB_PASS@localhost:$DB_PORT/$DB_NAME"
REDIS_URL="redis://localhost:6379/0"

(cd "$REPO_ROOT/mcp_servers/rag" && \
  DATABASE_URL="$DB_SYNC" \
  nohup uvicorn app.main:app --host 0.0.0.0 --port $RAG_PORT \
  > "$LOG_DIR/rag.log" 2>&1) &
echo $! > "$LOG_DIR/rag.pid"

# The service directories are their Python import roots.
(cd "$REPO_ROOT/mcp_servers/sql" && \
  DATABASE_URL="$DB_PLAIN" \
  nohup uvicorn app.main:app --host 0.0.0.0 --port $SQL_PORT \
  > "$LOG_DIR/sql.log" 2>&1) &
echo $! > "$LOG_DIR/sql.pid"

(cd "$REPO_ROOT/mcp_servers/external_api" && \
  REDIS_URL="$REDIS_URL" \
  nohup uvicorn app.main:app --host 0.0.0.0 --port $API_PORT \
  > "$LOG_DIR/api.log" 2>&1) &
echo $! > "$LOG_DIR/api.pid"

info "Waiting 10s for MCP services to start ..."
sleep 10

# The gateway also imports the top-level agent package.
(cd "$REPO_ROOT/gateway" && \
  PYTHONPATH="$REPO_ROOT" \
  DATABASE_URL="$DB_ASYNC" \
  REDIS_URL="$REDIS_URL" \
  DOC_MCP_URL="http://localhost:$RAG_PORT" \
  SQL_MCP_URL="http://localhost:$SQL_PORT" \
  EXTERNAL_API_MCP_URL="http://localhost:$API_PORT" \
  JWT_PRIVATE_KEY_PATH="$REPO_ROOT/gateway/private.pem" \
  JWT_PUBLIC_KEY_PATH="$REPO_ROOT/gateway/public.pem" \
  DEV_AUTH_PASSWORD="$AUTH_PASSWORD" \
  OPENAI_API_KEY="${OPENAI_API_KEY:-ollama}" \
  OPENAI_CHAT_COMPLETIONS_URL="$OLLAMA_URL" \
  SYNTHESIS_MODEL="$SYNTHESIS_MODEL" \
  PLANNER_MODEL="$PLANNER_MODEL" \
  nohup uvicorn app.main:app --host 0.0.0.0 --port $GW_PORT \
  > "$LOG_DIR/gateway.log" 2>&1) &
echo $! > "$LOG_DIR/gateway.pid"

echo ""
echo "=== 6. Waiting for services ==="

wait_port $RAG_PORT "RAG MCP"
wait_port $SQL_PORT "SQL MCP"
wait_port $API_PORT "External API MCP"
wait_port $GW_PORT  "Gateway"

echo ""
echo "=== 7. Smoke test ==="
cd "$REPO_ROOT"
bash smoke_test.sh

echo ""
echo "Logs are in: $LOG_DIR/"
echo "To stop all services: pkill -f 'uvicorn app.main'"
