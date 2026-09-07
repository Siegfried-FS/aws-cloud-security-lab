#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CDK_DIR="${SCRIPT_DIR}/../cdk"

echo "[*] [STAGE 1] Iniciando despliegue de infraestructura con AWS CDK..."
cd "${CDK_DIR}"

npx cdk deploy --require-approval never

echo "[OK] Despliegue de AWS CDK completado con éxito."
