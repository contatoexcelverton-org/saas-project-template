#!/bin/bash
# monitor_ci_status.sh — Script para agente local monitorar status do CI/CD
#
# O agente de IA local (VS Code + Claude) usa este script para:
# 1. Verificar se o CI/CD passou
# 2. Obter feedback de falhas
# 3. Decidir se precisa iterar ou se pode prosseguir
#
# Uso:
#   ./monitor_ci_status.sh [branch-name]
#
# Exemplo:
#   ./monitor_ci_status.sh feature/new-payment
#
# Retorna:
#   0 - Todos os workflows passaram
#   1 - Algum workflow falhou
#   2 - Workflows ainda rodando (aguarde)

set -e

BRANCH="${1:-$(git branch --show-current)}"
REPO_FULL_NAME=$(gh repo view --json nameWithOwner -q .nameWithOwner)

echo "=========================================="
echo "  Monitor CI/CD — Branch: $BRANCH"
echo "=========================================="
echo ""

# Obtém último commit da branch
LAST_COMMIT=$(git rev-parse HEAD)
SHORT_COMMIT=$(git rev-parse --short HEAD)

echo "Último commit: $SHORT_COMMIT"
echo "Repositório: $REPO_FULL_NAME"
echo ""

# Lista workflows em execução ou concluídos para este commit
echo "Buscando workflows para commit $SHORT_COMMIT..."
WORKFLOWS=$(gh run list \
  --repo "$REPO_FULL_NAME" \
  --commit "$LAST_COMMIT" \
  --json databaseId,name,status,conclusion,createdAt,url \
  --limit 20)

if [ "$(echo "$WORKFLOWS" | jq '. | length')" -eq 0 ]; then
  echo "⚠️  Nenhum workflow encontrado para este commit"
  echo ""
  echo "Possíveis causas:"
  echo "  1. Push ainda não disparou workflows (aguarde 10-30s)"
  echo "  2. Branch não tem workflows configurados"
  echo "  3. Commit não foi enviado ao GitHub"
  echo ""
  echo "Solução: Execute 'git push origin $BRANCH' e aguarde"
  exit 2
fi

echo ""
echo "Workflows encontrados:"
echo "$WORKFLOWS" | jq -r '.[] | "  - \(.name): \(.status) (\(.conclusion // "em andamento"))"'
echo ""

# Analisa status de cada workflow
ALL_COMPLETED=true
ANY_FAILED=false
FAILED_WORKFLOWS=()

while read -r workflow; do
  NAME=$(echo "$workflow" | jq -r .name)
  STATUS=$(echo "$workflow" | jq -r .status)
  CONCLUSION=$(echo "$workflow" | jq -r .conclusion)
  URL=$(echo "$workflow" | jq -r .url)
  RUN_ID=$(echo "$workflow" | jq -r .databaseId)

  if [ "$STATUS" != "completed" ]; then
    ALL_COMPLETED=false
    echo "⏳ $NAME ainda rodando..."
  elif [ "$CONCLUSION" != "success" ] && [ "$CONCLUSION" != "skipped" ]; then
    ANY_FAILED=true
    FAILED_WORKFLOWS+=("$NAME")
    echo "❌ $NAME falhou (conclusão: $CONCLUSION)"
    echo "   URL: $URL"

    # Obtém logs de falha
    echo ""
    echo "   Logs de falha:"
    gh run view "$RUN_ID" --repo "$REPO_FULL_NAME" --log-failed | head -50 | sed 's/^/   /'
    echo ""
  else
    echo "✅ $NAME passou"
  fi
done < <(echo "$WORKFLOWS" | jq -c '.[]')

echo ""
echo "=========================================="
echo "  RESULTADO"
echo "=========================================="
echo ""

if [ "$ALL_COMPLETED" = false ]; then
  echo "⏳ WORKFLOWS AINDA RODANDO"
  echo ""
  echo "Aguarde a conclusão dos workflows antes de prosseguir."
  echo "Execute este script novamente em 1-2 minutos."
  exit 2
fi

if [ "$ANY_FAILED" = true ]; then
  echo "❌ WORKFLOWS FALHARAM"
  echo ""
  echo "Os seguintes workflows falharam:"
  for workflow in "${FAILED_WORKFLOWS[@]}"; do
    echo "  - $workflow"
  done
  echo ""
  echo "O AGENTE DEVE:"
  echo "  1. Ler os logs de falha acima"
  echo "  2. Identificar o problema (teste falhando, credencial, padrão incorreto)"
  echo "  3. Corrigir o código"
  echo "  4. Rodar testes localmente: cd backend && pytest tests/ -v"
  echo "  5. Commit + push"
  echo "  6. Executar este script novamente"
  echo ""
  echo "⚠️  NÃO PROSSIGA PARA PRODUÇÃO ATÉ QUE TODOS OS WORKFLOWS PASSEM"
  exit 1
fi

echo "✅ TODOS OS WORKFLOWS PASSARAM"
echo ""
echo "O agente pode prosseguir para o próximo passo:"
echo "  - Se em PR: aguardar validação manual do preview"
echo "  - Se validado: fazer merge para main"
echo "  - Deploy automático para produção acontecerá após merge"
echo ""

exit 0
