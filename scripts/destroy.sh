#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[!] Ejecutando destrucción de infraestructura y barrido total de recursos..."
python3 "${SCRIPT_DIR}/cloudsec_wizard.py" --destroy
