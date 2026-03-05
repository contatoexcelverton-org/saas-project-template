# set_kv_settings.ps1 — Configura App Settings do Function App com referências ao Key Vault
#
# Uso:
#   pwsh infra/set_kv_settings.ps1
#   pwsh infra/set_kv_settings.ps1 -KvName kv-meu-projeto -AppName func-meu-projeto -ResourceGroup rg-meu-projeto
#
# Por que PowerShell e não bash?
#   O comando `az functionapp config appsettings set` tem um bug histórico no bash
#   quando o valor contém parênteses — ex: @Microsoft.KeyVault(...) — que causa
#   "command not found" silencioso. PowerShell lida com parênteses sem problema.
#
# Pré-requisitos:
#   1. az login (ou Connect-AzAccount)
#   2. Managed Identity do Function App já configurada
#   3. Key Vault já populado (via setup_keyvault.sh ou manualmente)

param(
    [Parameter(Mandatory=$false)]
    [string]$KvName = $env:KV_NAME,

    [Parameter(Mandatory=$false)]
    [string]$AppName = $env:FUNCTION_APP_NAME,

    [Parameter(Mandatory=$false)]
    [string]$ResourceGroup = $env:RESOURCE_GROUP,

    [Parameter(Mandatory=$false)]
    [string]$Slot = "production",   # Use "staging" para o slot de staging

    [switch]$DryRun                 # Exibe as settings sem aplicar
)

# ---------------------------------------------------------------------------
# Validação de parâmetros
# ---------------------------------------------------------------------------
if (-not $KvName) {
    Write-Error "Parâmetro -KvName ou variável de ambiente KV_NAME é obrigatório."
    exit 1
}
if (-not $AppName) {
    Write-Error "Parâmetro -AppName ou variável de ambiente FUNCTION_APP_NAME é obrigatório."
    exit 1
}
if (-not $ResourceGroup) {
    Write-Error "Parâmetro -ResourceGroup ou variável de ambiente RESOURCE_GROUP é obrigatório."
    exit 1
}

$KvBaseUrl = "https://$KvName.vault.azure.net/secrets"

# ---------------------------------------------------------------------------
# Função auxiliar para construir referência KV
# ---------------------------------------------------------------------------
function KvRef($SecretName) {
    # Converte UPPER_SNAKE_CASE → lower-kebab-case
    $normalized = $SecretName.ToLower().Replace("_", "-")
    return "@Microsoft.KeyVault(SecretUri=$KvBaseUrl/$normalized/)"
}

# ---------------------------------------------------------------------------
# Definição de todas as App Settings
# ---------------------------------------------------------------------------
$settings = [ordered]@{
    # --- Banco de dados ---
    "POSTGRES_HOST"             = KvRef "POSTGRES_HOST"
    "POSTGRES_PORT"             = KvRef "POSTGRES_PORT"
    "POSTGRES_DB"               = KvRef "POSTGRES_DB"
    "POSTGRES_USER"             = KvRef "POSTGRES_USER"
    "POSTGRES_PASSWORD"         = KvRef "POSTGRES_PASSWORD"
    "POSTGRES_SSLMODE"          = KvRef "POSTGRES_SSLMODE"

    # --- Auth ---
    "JWT_SECRET"                = KvRef "JWT_SECRET"
    "JWT_ALGORITHM"             = KvRef "JWT_ALGORITHM"

    # --- Pagamentos ---
    "STRIPE_SECRET_KEY"         = KvRef "STRIPE_SECRET_KEY"
    "STRIPE_PUBLISHABLE_KEY"    = KvRef "STRIPE_PUBLISHABLE_KEY"
    "STRIPE_WEBHOOK_SECRET"     = KvRef "STRIPE_WEBHOOK_SECRET"
    "MERCADOPAGO_ACCESS_TOKEN"  = KvRef "MERCADOPAGO_ACCESS_TOKEN"
    "MERCADOPAGO_WEBHOOK_SECRET" = KvRef "MERCADOPAGO_WEBHOOK_SECRET"

    # --- Azure OpenAI ---
    "AZURE_OPENAI_ENDPOINT"     = KvRef "AZURE_OPENAI_ENDPOINT"
    "AZURE_OPENAI_KEY"          = KvRef "AZURE_OPENAI_KEY"
    "AZURE_OPENAI_DEPLOYMENT"   = KvRef "AZURE_OPENAI_DEPLOYMENT"

    # --- Comunicação ---
    "SENDGRID_API_KEY"          = KvRef "SENDGRID_API_KEY"
    "GOOGLE_CLIENT_ID"          = KvRef "GOOGLE_CLIENT_ID"
    "GOOGLE_CLIENT_SECRET"      = KvRef "GOOGLE_CLIENT_SECRET"

    # --- Observabilidade ---
    "APPLICATIONINSIGHTS_CONNECTION_STRING" = KvRef "APPINSIGHTS_CONNECTION_STRING"

    # --- KV self-reference (para o SDK azure-keyvault-secrets) ---
    "AZURE_KEYVAULT_URL"        = "https://$KvName.vault.azure.net/"

    # --- Runtime (não vão para KV) ---
    "FUNCTIONS_WORKER_RUNTIME"  = "python"
    "ENVIRONMENT"               = "production"
    "LOG_LEVEL"                 = "INFO"
}

# ---------------------------------------------------------------------------
# Exibe em modo DryRun ou aplica
# ---------------------------------------------------------------------------
if ($DryRun) {
    Write-Host "`n[DRY RUN] Settings que seriam aplicadas ao $AppName ($Slot):" -ForegroundColor Cyan
    $settings.GetEnumerator() | ForEach-Object {
        Write-Host "  $($_.Key) = $($_.Value)" -ForegroundColor DarkGray
    }
    Write-Host "`n  Use sem -DryRun para aplicar." -ForegroundColor Yellow
    exit 0
}

# Constrói array de pares NAME=VALUE para a az CLI
$settingsList = $settings.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }

Write-Host "Aplicando $($settingsList.Count) settings ao Function App '$AppName' (slot: $Slot)..." -ForegroundColor Cyan

$slotArgs = if ($Slot -ne "production") { @("--slot", $Slot) } else { @() }

az functionapp config appsettings set `
    --name $AppName `
    --resource-group $ResourceGroup `
    --settings $settingsList `
    @slotArgs `
    --output table

if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao configurar App Settings. Verifique o az login e permissões."
    exit 1
}

Write-Host "`n✅ App Settings configuradas com sucesso." -ForegroundColor Green
Write-Host "   Next: Reinicie o Function App para carregar as novas settings." -ForegroundColor DarkGray
Write-Host "   $ az functionapp restart --name $AppName --resource-group $ResourceGroup" -ForegroundColor DarkGray
