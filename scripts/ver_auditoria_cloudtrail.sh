#!/usr/bin/env bash
# [ AUDITORIA FORENSE & TELEMETRIA EN VIVO // AWS CLOUDTRAIL ]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${SCRIPT_DIR}/../presentacion/demo-config.json"

CYAN="\033[96m"
GREEN="\033[92m"
YELLOW="\033[93m"
RESET="\033[0m"
BOLD="\033[1m"

REGION="us-east-1"
if [ -f "$CONFIG_PATH" ]; then
  REGION=$(python3 -c "import json; print(json.load(open('$CONFIG_PATH')).get('region', 'us-east-1'))" 2>/dev/null || echo "us-east-1")
fi

echo -e "\n${CYAN}${BOLD}╔════════════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${CYAN}${BOLD}║   :: RADAR FORENSE EN VIVO // TELEMETRIA AWS CLOUDTRAIL ::         ║${RESET}"
echo -e "${CYAN}${BOLD}╚════════════════════════════════════════════════════════════════════╝${RESET}\n"

echo -e "${YELLOW}[*] Consultando ultimos eventos de seguridad en region ${BOLD}${REGION}${RESET}...\n"

export AWS_PAGER=""

PROFILE_ARG=""
if [ -n "$AWS_PROFILE" ]; then
  PROFILE_ARG="--profile $AWS_PROFILE"
elif [ -f "$CONFIG_PATH" ]; then
  P=$(python3 -c "import json; print(json.load(open('$CONFIG_PATH')).get('profile', ''))" 2>/dev/null || true)
  [ -n "$P" ] && PROFILE_ARG="--profile $P"
fi

# Fallback si profile está en workshops
if [ -z "$PROFILE_ARG" ]; then
  if aws configure get region --profile workshops &>/dev/null; then
    PROFILE_ARG="--profile workshops"
  fi
fi

aws cloudtrail lookup-events \
  --region "$REGION" \
  $PROFILE_ARG \
  --lookup-attributes AttributeKey=ReadOnly,AttributeValue=false \
  --max-results 10 \
  --query 'Events[*].{Fecha:EventTime,Evento:EventName,Usuario:Username,Recurso:Resources[0].ResourceName}' \
  --output table

echo -e "\n${GREEN}[INFO] Explicacion tecnica para la audiencia:${RESET}"
echo -e "Filtramos por ${BOLD}ReadOnly=false${RESET} para ignorar el 'ruido' de simples consultas de lectura."
echo -e "Aqui vemos los cambios reales en caliente: ${CYAN}DeleteRolePolicy${RESET} (corte IAM) y ${CYAN}Authorize/RevokeSecurityGroupIngress${RESET} (Firewall)."

