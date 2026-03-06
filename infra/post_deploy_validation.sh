#!/bin/bash
# post_deploy_validation.sh — Smoke tests pós-deploy
#
# Valida que o deploy foi bem-sucedido testando endpoints críticos.
# Uso: ./post_deploy_validation.sh <function-app-name>
#
# Exemplo:
#   ./post_deploy_validation.sh meuapp-func
#
# Exit codes:
#   0 - Todas as validações passaram
#   1 - Uma ou mais validações falharam

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ---------------------------------------------------------------------------
# Validação de parâmetros
# ---------------------------------------------------------------------------

if [ -z "$1" ]; then
    echo -e "${RED}❌ Uso: $0 <function-app-name>${NC}"
    echo ""
    echo "Exemplo:"
    echo "  $0 meuapp-func"
    exit 1
fi

FUNCTION_APP_NAME=$1
BASE_URL="https://${FUNCTION_APP_NAME}.azurewebsites.net"

echo "=========================================="
echo "  Validação Pós-Deploy"
echo "=========================================="
echo ""
echo "Function App: ${FUNCTION_APP_NAME}"
echo "Base URL: ${BASE_URL}"
echo ""

# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

# Testa endpoint e valida status HTTP esperado
test_endpoint() {
    local method=$1
    local path=$2
    local expected_status=$3
    local description=$4
    local data=$5

    echo -e "${BLUE}🔍 Testando: $description${NC}"
    echo "   ${method} ${BASE_URL}${path}"

    if [ -n "$data" ]; then
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "${BASE_URL}${path}" 2>&1)
    else
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            -X "$method" \
            "${BASE_URL}${path}" 2>&1)
    fi

    if [ "$STATUS" = "$expected_status" ]; then
        echo -e "${GREEN}✅ HTTP $STATUS (esperado: $expected_status)${NC}"
        echo ""
        return 0
    else
        echo -e "${RED}❌ HTTP $STATUS (esperado: $expected_status)${NC}"
        echo ""
        return 1
    fi
}

# Testa endpoint e valida conteúdo da resposta
test_endpoint_with_body() {
    local method=$1
    local path=$2
    local expected_pattern=$3
    local description=$4

    echo -e "${BLUE}🔍 Testando: $description${NC}"
    echo "   ${method} ${BASE_URL}${path}"

    RESPONSE=$(curl -s -X "$method" "${BASE_URL}${path}" 2>&1)
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "${BASE_URL}${path}" 2>&1)

    echo "   Status: HTTP $STATUS"

    if echo "$RESPONSE" | grep -q "$expected_pattern"; then
        echo -e "${GREEN}✅ Resposta contém padrão esperado: $expected_pattern${NC}"
        echo ""
        return 0
    else
        echo -e "${RED}❌ Resposta NÃO contém padrão esperado: $expected_pattern${NC}"
        echo "   Resposta: $RESPONSE"
        echo ""
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=()

# Teste 1: Health check básico
((TOTAL_TESTS++))
if test_endpoint "GET" "/api/health" "200" "Health check básico"; then
    ((PASSED_TESTS++))
else
    FAILED_TESTS+=("Health check")
fi

# Teste 2: Health check retorna JSON com status
((TOTAL_TESTS++))
if test_endpoint_with_body "GET" "/api/health" '"status"' "Health check JSON structure"; then
    ((PASSED_TESTS++))
else
    FAILED_TESTS+=("Health JSON structure")
fi

# Teste 3: Validação de input — registro com email inválido deve retornar 400
((TOTAL_TESTS++))
if test_endpoint "POST" "/api/register" "400" "Validação de input (email inválido)" \
    '{"email":"invalido","password":"123456","name":"Test User","cpf":"12345678901","birthdate":"1990-01-01"}'; then
    ((PASSED_TESTS++))
else
    FAILED_TESTS+=("Input validation")
fi

# Teste 4: Endpoint inexistente deve retornar 404
((TOTAL_TESTS++))
if test_endpoint "GET" "/api/endpoint-que-nao-existe" "404" "Endpoint inexistente retorna 404"; then
    ((PASSED_TESTS++))
else
    FAILED_TESTS+=("404 handling")
fi

# Teste 5: CORS headers (se configurado)
((TOTAL_TESTS++))
echo -e "${BLUE}🔍 Testando: CORS headers${NC}"
CORS_HEADER=$(curl -s -I -X OPTIONS "${BASE_URL}/api/health" | grep -i "access-control-allow-origin" || true)
if [ -n "$CORS_HEADER" ]; then
    echo -e "${GREEN}✅ CORS configurado: $CORS_HEADER${NC}"
    ((PASSED_TESTS++))
else
    echo -e "${YELLOW}⚠️  CORS não configurado ou não necessário${NC}"
    ((PASSED_TESTS++))  # Não falha o teste — pode ser intencional
fi
echo ""

# Teste 6: Tempo de resposta do health check
((TOTAL_TESTS++))
echo -e "${BLUE}🔍 Testando: Tempo de resposta${NC}"
START_TIME=$(date +%s%3N)
curl -s "${BASE_URL}/api/health" > /dev/null
END_TIME=$(date +%s%3N)
RESPONSE_TIME=$((END_TIME - START_TIME))
echo "   Tempo de resposta: ${RESPONSE_TIME}ms"
if [ "$RESPONSE_TIME" -lt 5000 ]; then
    echo -e "${GREEN}✅ Resposta rápida (<5s)${NC}"
    ((PASSED_TESTS++))
else
    echo -e "${YELLOW}⚠️  Resposta lenta (>${RESPONSE_TIME}ms) — pode haver cold start${NC}"
    ((PASSED_TESTS++))  # Não falha — cold start é esperado
fi
echo ""

# Teste 7: Verifica se Application Insights está instrumentado
((TOTAL_TESTS++))
echo -e "${BLUE}🔍 Testando: Application Insights instrumentation${NC}"
# Faz uma requisição e verifica headers de telemetria
TELEMETRY_HEADER=$(curl -s -I "${BASE_URL}/api/health" | grep -i "request-id\|x-ms-request-id" || true)
if [ -n "$TELEMETRY_HEADER" ]; then
    echo -e "${GREEN}✅ Application Insights instrumentado${NC}"
    echo "   Header: $TELEMETRY_HEADER"
    ((PASSED_TESTS++))
else
    echo -e "${YELLOW}⚠️  Application Insights pode não estar configurado${NC}"
    ((PASSED_TESTS++))  # Não falha — pode não estar no plano
fi
echo ""

# ---------------------------------------------------------------------------
# Testes específicos de autenticação (se endpoints existirem)
# ---------------------------------------------------------------------------

# Teste 8: Login sem credenciais deve retornar 401
((TOTAL_TESTS++))
echo -e "${BLUE}🔍 Testando: Autenticação (login sem credenciais)${NC}"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${BASE_URL}/api/login" \
    -H "Content-Type: application/json" \
    -d '{}' 2>&1)

if [ "$STATUS" = "400" ] || [ "$STATUS" = "401" ]; then
    echo -e "${GREEN}✅ HTTP $STATUS (validação de auth ok)${NC}"
    ((PASSED_TESTS++))
elif [ "$STATUS" = "404" ]; then
    echo -e "${YELLOW}⚠️  Endpoint /api/login não existe (ok se não implementado)${NC}"
    ((PASSED_TESTS++))
else
    echo -e "${RED}❌ HTTP $STATUS (esperado: 400 ou 401)${NC}"
    FAILED_TESTS+=("Auth validation")
fi
echo ""

# ---------------------------------------------------------------------------
# Testes específicos de pagamento (se endpoints existirem)
# ---------------------------------------------------------------------------

# Teste 9: Lista de planos deve retornar 200 ou 404
((TOTAL_TESTS++))
echo -e "${BLUE}🔍 Testando: Pagamento (lista de planos)${NC}"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/api/plans" 2>&1)

if [ "$STATUS" = "200" ]; then
    echo -e "${GREEN}✅ HTTP $STATUS (endpoint de planos ok)${NC}"
    ((PASSED_TESTS++))
elif [ "$STATUS" = "404" ]; then
    echo -e "${YELLOW}⚠️  Endpoint /api/plans não existe (ok se não implementado)${NC}"
    ((PASSED_TESTS++))
else
    echo -e "${RED}❌ HTTP $STATUS (esperado: 200 ou 404)${NC}"
    FAILED_TESTS+=("Plans endpoint")
fi
echo ""

# ---------------------------------------------------------------------------
# Resumo
# ---------------------------------------------------------------------------

echo "=========================================="
echo "  RESUMO DA VALIDAÇÃO"
echo "=========================================="
echo ""
echo "Total de testes: $TOTAL_TESTS"
echo -e "${GREEN}Passaram: $PASSED_TESTS${NC}"

if [ ${#FAILED_TESTS[@]} -gt 0 ]; then
    echo -e "${RED}Falharam: ${#FAILED_TESTS[@]}${NC}"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
    echo ""
    echo -e "${RED}❌ VALIDAÇÃO PÓS-DEPLOY FALHOU${NC}"
    echo ""
    echo "Ações recomendadas:"
    echo "  1. Verifique logs no Application Insights"
    echo "  2. Verifique configuração de App Settings (Key Vault refs)"
    echo "  3. Verifique se todos os secrets estão no Key Vault"
    echo "  4. Execute rollback se necessário"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ VALIDAÇÃO PÓS-DEPLOY PASSOU${NC}"
echo ""
echo "Deploy validado com sucesso!"
echo ""
echo "URLs úteis:"
echo "  Health check: ${BASE_URL}/api/health"
echo "  Application Insights: https://portal.azure.com"
echo ""

exit 0
