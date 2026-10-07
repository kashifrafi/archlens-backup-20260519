#!/usr/bin/env bash
# setup_schema_cron.sh
# ====================
# Installs a monthly cron job that refreshes the Terraform provider schema
# ChromaDB collection from the official Terraform Registry.
#
# Run once:
#     bash scripts/setup_schema_cron.sh
#
# The cron runs at 02:00 on the first day of every month.
# Remove with:
#     crontab -l | grep -v ingest_provider_schemas | crontab -

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON="${BACKEND_DIR}/.venv/bin/python"
INGEST_SCRIPT="${BACKEND_DIR}/scripts/ingest_provider_schemas.py"
LOG_FILE="/var/log/archlens-schema-ingest.log"

# Validate paths
if [[ ! -x "${PYTHON}" ]]; then
    echo "ERROR: Python venv not found at ${PYTHON}"
    echo "       Run: python -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

if [[ ! -f "${INGEST_SCRIPT}" ]]; then
    echo "ERROR: Ingest script not found at ${INGEST_SCRIPT}"
    exit 1
fi

# Ensure log directory is writable; fall back to user's home if /var/log is not
if ! touch "${LOG_FILE}" 2>/dev/null; then
    LOG_FILE="${BACKEND_DIR}/logs/schema-ingest.log"
    mkdir -p "$(dirname "${LOG_FILE}")"
    echo "NOTE: /var/log not writable — logging to ${LOG_FILE}"
fi

# Build the cron entry
CRON_ENTRY="0 2 1 * *  cd \"${BACKEND_DIR}\" && \"${PYTHON}\" \"${INGEST_SCRIPT}\" >> \"${LOG_FILE}\" 2>&1"

# Install: strip old entry (if any), add new one
(
    crontab -l 2>/dev/null | grep -v "ingest_provider_schemas"
    echo "${CRON_ENTRY}"
) | crontab -

echo "Cron job installed successfully."
echo ""
echo "  Schedule : 02:00 on the 1st of every month"
echo "  Command  : ${PYTHON} ${INGEST_SCRIPT}"
echo "  Log      : ${LOG_FILE}"
echo ""
echo "To trigger a manual run:"
echo "  cd ${BACKEND_DIR} && ${PYTHON} ${INGEST_SCRIPT} --providers aws"
echo ""
echo "To remove:"
echo "  crontab -l | grep -v ingest_provider_schemas | crontab -"
