#!/bin/bash
# setup_cloudflare.sh — Automação de configuração DNS Cloudflare
#
# Configura registros DNS no Cloudflare para apontar para Azure Functions
# Uso: ./setup_cloudflare.sh
#
# Requer variáveis de ambiente:
#   CLOUDFLARE_API_TOKEN — Token de API com permissões de DNS
#   CLOUDFLARE_ZONE_ID — ID da zona (obtido no Cloudflare Dashboard)
#   AZURE_FUNCTION_APP_NAME — Nome do Function App no Azure
#   CUSTOM_DOMAINS — Lista de domínios separados por espaço (ex: "api.app.com www.app.com")

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=========================================="
echo "  Configuração DNS Cloudflare → Azure"
echo "=========================================="
echo ""

# ---------------------------------------------------------------------------
# Validação de variáveis obrigatórias
# ---------------------------------------------------------------------------

REQUIRED_VARS=(
    "CLOUDFLARE_API_TOKEN"
    "CLOUDFLARE_ZONE_ID"
    "AZURE_FUNCTION_APP_NAME"
    "CUSTOM_DOMAINS"
)

MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo -e "${RED}❌ Variáveis obrigatórias não encontradas:${NC}"
    for var in "${MISSING_VARS[@]}"; do
        echo "   - $var"
    done
    echo ""
    echo "Configure no .env ou exporte antes de executar:"
    echo "  export CLOUDFLARE_API_TOKEN='seu_token'"
    echo "  export CLOUDFLARE_ZONE_ID='seu_zone_id'"
    echo "  export AZURE_FUNCTION_APP_NAME='nome-func'"
    echo "  export CUSTOM_DOMAINS='api.app.com www.app.com'"
    exit 1
fi

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

API_BASE="https://api.cloudflare.com/client/v4"
ZONE_ID="${CLOUDFLARE_ZONE_ID}"
API_TOKEN="${CLOUDFLARE_API_TOKEN}"
AZURE_CNAME="${AZURE_FUNCTION_APP_NAME}.azurewebsites.net"

# Converte string de domínios em array
IFS=' ' read -r -a DOMAINS <<< "$CUSTOM_DOMAINS"

echo "Zona Cloudflare: ${ZONE_ID}"
echo "Azure CNAME: ${AZURE_CNAME}"
echo "Domínios a configurar: ${#DOMAINS[@]}"
for domain in "${DOMAINS[@]}"; do
    echo "  - $domain"
done
echo ""

# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

# Obtém ID de um registro DNS existente por nome
get_dns_record_id() {
    local domain=$1
    local response=$(curl -s -X GET \
        "${API_BASE}/zones/${ZONE_ID}/dns_records?name=${domain}" \
        -H "Authorization: Bearer ${API_TOKEN}" \
        -H "Content-Type: application/json")

    local record_id=$(echo "$response" | grep -oP '"id":"\K[^"]+' | head -1)
    echo "$record_id"
}

# Cria ou atualiza registro CNAME no Cloudflare
create_or_update_cname() {
    local domain=$1
    local existing_id=$(get_dns_record_id "$domain")

    # Extrai apenas o nome (sem domínio raiz)
    local name_only="${domain%%.*}"
    if [ "$domain" = "$name_only" ]; then
        name_only="@"
    fi

    local payload=$(cat <<EOF
{
  "type": "CNAME",
  "name": "${name_only}",
  "content": "${AZURE_CNAME}",
  "ttl": 1,
  "proxied": false
}
EOF
)

    if [ -n "$existing_id" ]; then
        # Atualiza registro existente
        echo -e "${YELLOW}⚠️  Registro $domain já existe (ID: $existing_id) — atualizando...${NC}"
        local response=$(curl -s -X PUT \
            "${API_BASE}/zones/${ZONE_ID}/dns_records/${existing_id}" \
            -H "Authorization: Bearer ${API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "$payload")
    else
        # Cria novo registro
        echo -e "${GREEN}➕ Criando registro $domain...${NC}"
        local response=$(curl -s -X POST \
            "${API_BASE}/zones/${ZONE_ID}/dns_records" \
            -H "Authorization: Bearer ${API_TOKEN}" \
            -H "Content-Type: application/json" \
            -d "$payload")
    fi

    # Verifica se teve sucesso
    local success=$(echo "$response" | grep -oP '"success":\K\w+')
    if [ "$success" = "true" ]; then
        echo -e "${GREEN}✅ $domain configurado${NC}"
        echo "   CNAME: $domain → $AZURE_CNAME"
        echo "   Proxy: OFF (necessário para custom domains Azure)"
        echo ""
        return 0
    else
        echo -e "${RED}❌ Falha ao configurar $domain${NC}"
        echo "   Response: $response"
        echo ""
        return 1
    fi
}

# Valida resolução de DNS
validate_dns_resolution() {
    local domain=$1
    echo "Validando resolução DNS para $domain..."

    # Aguarda propagação (máximo 30 segundos)
    local max_attempts=6
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if nslookup "$domain" > /dev/null 2>&1; then
            local resolved_to=$(nslookup "$domain" | grep -A1 "Name:" | tail -1 | awk '{print $2}')
            echo -e "${GREEN}✅ DNS resolve: $domain → $resolved_to${NC}"
            return 0
        fi
        echo "   Tentativa $attempt/$max_attempts — aguardando propagação..."
        sleep 5
        ((attempt++))
    done

    echo -e "${YELLOW}⚠️  DNS ainda não propagou para $domain (pode levar até 24h)${NC}"
    return 1
}

# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

TOTAL_DOMAINS=${#DOMAINS[@]}
SUCCESS_COUNT=0
FAILED_DOMAINS=()

for domain in "${DOMAINS[@]}"; do
    echo "=========================================="
    echo "Configurando: $domain"
    echo "=========================================="

    if create_or_update_cname "$domain"; then
        ((SUCCESS_COUNT++))

        # Valida DNS (apenas informativo — não bloqueia)
        validate_dns_resolution "$domain" || true
    else
        FAILED_DOMAINS+=("$domain")
    fi
done

# ---------------------------------------------------------------------------
# Resumo
# ---------------------------------------------------------------------------

echo ""
echo "=========================================="
echo "  RESUMO DA CONFIGURAÇÃO"
echo "=========================================="
echo ""
echo "Total de domínios: $TOTAL_DOMAINS"
echo -e "${GREEN}Configurados com sucesso: $SUCCESS_COUNT${NC}"

if [ ${#FAILED_DOMAINS[@]} -gt 0 ]; then
    echo -e "${RED}Falharam: ${#FAILED_DOMAINS[@]}${NC}"
    for domain in "${FAILED_DOMAINS[@]}"; do
        echo "  - $domain"
    done
    echo ""
    echo "Verifique:"
    echo "  1. Token de API tem permissões de DNS (Edit)"
    echo "  2. Zone ID está correto"
    echo "  3. Domínio existe na zona Cloudflare"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ CONFIGURAÇÃO CONCLUÍDA${NC}"
echo ""
echo "Próximos passos:"
echo ""
echo "1. Adicione custom domains no Azure Function App:"
for domain in "${DOMAINS[@]}"; do
    echo "   az functionapp config hostname add \\"
    echo "     --webapp-name ${AZURE_FUNCTION_APP_NAME} \\"
    echo "     --resource-group \${AZURE_RESOURCE_GROUP} \\"
    echo "     --hostname ${domain}"
    echo ""
done

echo "2. Aguarde Azure emitir certificado SSL (5-10 minutos)"
echo ""
echo "3. Valide o acesso:"
for domain in "${DOMAINS[@]}"; do
    echo "   curl https://${domain}/api/health"
done
echo ""
echo "4. Se tudo estiver ok, reative o proxy Cloudflare (ícone laranja) para CDN"
echo ""

exit 0
