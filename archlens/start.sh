#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          ArchLens — Local Development            ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${NC}"

# ── Backend .env check ────────────────────────────────────────────────────────
if [[ ! -f "$BACKEND_DIR/.env" ]]; then
  echo -e "${YELLOW}WARNING: $BACKEND_DIR/.env not found${NC}"
  echo "  Copying .env.example → .env"
  cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
  echo -e "${YELLOW}  Please edit $BACKEND_DIR/.env and add your API keys, then re-run.${NC}"
  exit 1
fi

# ── Backend venv ──────────────────────────────────────────────────────────────
if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
  echo -e "${BLUE}Creating Python virtual environment...${NC}"
  python3 -m venv "$BACKEND_DIR/.venv"
fi

echo -e "${BLUE}Installing backend dependencies...${NC}"
"$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

# ── Frontend node_modules ─────────────────────────────────────────────────────
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo -e "${BLUE}Installing frontend dependencies...${NC}"
  (cd "$FRONTEND_DIR" && npm install --silent)
fi

# ── Start backend ─────────────────────────────────────────────────────────────
echo -e "${GREEN}Starting backend on http://localhost:8000 ...${NC}"
(cd "$BACKEND_DIR" && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
BACKEND_PID=$!

# ── Start frontend ────────────────────────────────────────────────────────────
sleep 2
echo -e "${GREEN}Starting frontend on http://localhost:5173 ...${NC}"
(cd "$FRONTEND_DIR" && npm run dev -- --host) &
FRONTEND_PID=$!

# ── Trap for clean shutdown ───────────────────────────────────────────────────
cleanup() {
  echo -e "\n${YELLOW}Shutting down...${NC}"
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  exit 0
}
trap cleanup SIGINT SIGTERM

echo ""
echo -e "${GREEN}ArchLens is running!${NC}"
echo -e "  Frontend: ${BLUE}http://localhost:5173${NC}"
echo -e "  Backend:  ${BLUE}http://localhost:8000${NC}"
echo -e "  API Docs: ${BLUE}http://localhost:8000/api/docs${NC}"
echo ""
echo "Press Ctrl+C to stop."

wait
