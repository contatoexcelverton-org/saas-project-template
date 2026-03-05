#!/usr/bin/env bash
# setup_keyvault.sh — Cria e popula o Key Vault do projeto
#
# Uso:
#   chmod +x infra/setup_keyvault.sh
#   ./infra/setup_keyvault.sh
#
# Pré-requisitos:
#   1. az login executado (ou az login --use-device-code para WSL/pipeline)
#   2. .env preenchido com os valores reais
#   3. Managed Identity do Function App já criada (provisionar infra/ primeiro)
#
# O que faz:
#   1. Cria o Key Vault (se não existir)
#   2. Atribui role Key Vault Secrets Officer para o usuário atual
#   3. Atribui role Key Vault Secrets User para a Managed Identity do app
#   4. Popula todos os secrets a partir do .env
#   5. Exibe a URL de cada secret para uso em App Settings (referências KV)
#
# SEGURANÇA:
#   - Never commit este script com valores reais — use apenas com .env local
#   - Os secrets são lidos do .env, nunca passados como argumento na linha de comando

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuração — ajuste por projeto
# ---------------------------------------------------------------------------
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-meu-projeto}"
LOCATION="${LOCATION:-brazilsouth}"
KV_NAME="${KV_NAME:-kv-meu-projeto}"                    # máx 24 chars, globalmente único
FUNCTION_APP_NAME="${FUNCTION_APP_NAME:-}"               # para atribuir role à MI
ENV_FILE="${ENV_FILE:-.env}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { echo "ℹ️  $*"; }
ok()    { echo "✅ $*"; }
warn()  { echo "⚠️  $*"; }
fail()  { echo "❌ $*"; exit 1; }

# ---------------------------------------------------------------------------
# Validações iniciais
# ---------------------------------------------------------------------------
[[ ! -f "$ENV_FILE" ]] && fail "Arquivo .env não encontrado: $ENV_FILE"
az account show --query "id" -o tsv > /dev/null 2>&1 || fail "Execute 'az login' primeiro."

SUBSCRIPTION_ID=$(az account show --query "id" -o tsv)
CURRENT_USER_OBJECT_ID=$(az ad signed-in-user show --query "id" -o tsv 2>/dev/null || echo "")

info "Subscription: $SUBSCRIPTION_ID"
info "Key Vault:    $KV_NAME"
info "Localização:  $LOCATION"

# ---------------------------------------------------------------------------
# 1. Resource Group
# ---------------------------------------------------------------------------
info "Criando Resource Group (se não existir)..."
az group create \
    --name "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none
ok "Resource Group: $RESOURCE_GROUP"

# ---------------------------------------------------------------------------
# 2. Key Vault
# ---------------------------------------------------------------------------
info "Criando Key Vault (se não existir)..."
KV_EXISTS=$(az keyvault list --resource-group "$RESOURCE_GROUP" \
    --query "[?name=='$KV_NAME'].name" -o tsv)

if [[ -z "$KV_EXISTS" ]]; then
    az keyvault create \
        --name "$KV_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --sku standard \
        --enable-rbac-authorization true \
        --output none
    ok "Key Vault criado: $KV_NAME"
else
    info "Key Vault já existe: $KV_NAME (pulando criação)"
fi

KV_ID=$(az keyvault show --name "$KV_NAME" --resource-group "$RESOURCE_GROUP" \
    --query "id" -o tsv)

# ---------------------------------------------------------------------------
# 3. Permissões — usuário atual (admin)
# ---------------------------------------------------------------------------
if [[ -n "$CURRENT_USER_OBJECT_ID" ]]; then
    info "Atribuindo Key Vault Secrets Officer ao usuário atual..."
    az role assignment create \
        --assignee-object-id "$CURRENT_USER_OBJECT_ID" \
        --assignee-principal-type "User" \
        --role "Key Vault Secrets Officer" \
        --scope "$KV_ID" \
        --output none 2>/dev/null || warn "Role já atribuída (ignorando)"
    ok "Permissão de admin configurada"
fi

# ---------------------------------------------------------------------------
# 4. Permissões — Managed Identity do Function App (se configurado)
# ---------------------------------------------------------------------------
if [[ -n "$FUNCTION_APP_NAME" ]]; then
    info "Obtendo Managed Identity do Function App: $FUNCTION_APP_NAME..."
    MI_PRINCIPAL_ID=$(az functionapp identity show \
        --name "$FUNCTION_APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --query "principalId" -o tsv 2>/dev/null || echo "")

    if [[ -n "$MI_PRINCIPAL_ID" ]]; then
        az role assignment create \
            --assignee-object-id "$MI_PRINCIPAL_ID" \
            --assignee-principal-type "ServicePrincipal" \
            --role "Key Vault Secrets User" \
            --scope "$KV_ID" \
            --output none 2>/dev/null || warn "Role MI já atribuída (ignorando)"
        ok "Managed Identity com acesso a secrets: $MI_PRINCIPAL_ID"
    else
        warn "Function App '$FUNCTION_APP_NAME' não encontrado ou sem MI. Provisione a infra primeiro."
    fi
fi

# ---------------------------------------------------------------------------
# 5. Popula secrets a partir do .env
# ---------------------------------------------------------------------------
info "Populando secrets no Key Vault a partir do .env..."

# Secrets que devem ir para o KV (excluir vars não-sensíveis)
SKIP_VARS=("ENVIRONMENT" "LOG_LEVEL" "SITE_URL" "RESOURCE_GROUP" "LOCATION" \
           "KV_NAME" "FUNCTION_APP_NAME" "AZURE_KEYVAULT_URL" "ENV_FILE")

declare -a kv_ref_lines=()

while IFS= read -r line || [[ -n "$line" ]]; do
    # Ignora comentários e linhas vazias
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line//[[:space:]]/}" ]] && continue
    [[ "$line" != *=* ]] && continue

    KEY="${line%%=*}"
    VALUE="${line#*=}"
    # Remove aspas
    VALUE="${VALUE%\"}"
    VALUE="${VALUE#\"}"
    VALUE="${VALUE%\'}"
    VALUE="${VALUE#\'}"

    # Pula vars da lista de exclusão
    SKIP=false
    for skip_var in "${SKIP_VARS[@]}"; do
        [[ "$KEY" == "$skip_var" ]] && SKIP=true && break
    done
    $SKIP && continue

    # Pula se vazio
    [[ -z "$VALUE" ]] && warn "  Ignorando $KEY — valor vazio" && continue

    # Converte underscores para hífens (KV aceita apenas letras, dígitos e hífens)
    SECRET_NAME="${KEY//_/-}"
    SECRET_NAME="${SECRET_NAME,,}"  # lowercase

    az keyvault secret set \
        --vault-name "$KV_NAME" \
        --name "$SECRET_NAME" \
        --value "$VALUE" \
        --output none 2>/dev/null
    ok "  $SECRET_NAME"

    # Monta referência para App Settings
    SECRET_URI="https://${KV_NAME}.vault.azure.net/secrets/${SECRET_NAME}/"
    kv_ref_lines+=("  \"$KEY\": \"@Microsoft.KeyVault(SecretUri=${SECRET_URI})\",")

done < "$ENV_FILE"

# ---------------------------------------------------------------------------
# 6. Exibe referências para copiar no appsettings
# ---------------------------------------------------------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  App Settings — copie para o portal Azure ou use set_kv_settings.ps1"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "{"
for line in "${kv_ref_lines[@]}"; do
    echo "$line"
done
echo "  \"AZURE_KEYVAULT_URL\": \"https://${KV_NAME}.vault.azure.net/\""
echo "}"
echo ""
ok "Key Vault configurado: https://${KV_NAME}.vault.azure.net/"
echo ""
echo "Próximos passos:"
echo "  1. Copie as App Settings acima para o Function App"
echo "  2. Ou execute: pwsh infra/set_kv_settings.ps1"
echo "  3. Valide: python infra/validate_project.py"
