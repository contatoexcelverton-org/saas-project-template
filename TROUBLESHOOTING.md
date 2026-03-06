# Troubleshooting — Guia de Resolução de Problemas

## 🎯 Visão Geral

Este guia cobre os problemas mais comuns enfrentados ao desenvolver e fazer deploy de micro-SaaS usando este template.

---

## 🔍 Diagnóstico Rápido

### Checklist inicial para qualquer problema

Execute estes comandos ANTES de investigar a fundo:

```bash
# 1. Valide configuração do projeto
python infra/validate_project.py

# 2. Rode testes localmente
cd backend && pytest tests/ -v

# 3. Verifique logs do Azure (últimos 30 min)
az monitor app-insights query \
  --app ${APPINSIGHTS_APP_ID} \
  --analytics-query "traces | where timestamp > ago(30m) | order by timestamp desc | take 50"

# 4. Verifique health check
curl https://${FUNCTION_APP_NAME}.azurewebsites.net/api/health
```

---

## 🐛 Problemas Comuns — Desenvolvimento Local

### 1. Testes falhando com `ModuleNotFoundError`

**Sintoma:**
```
ModuleNotFoundError: No module named 'services'
```

**Causa:** Virtual environment não ativado ou dependências não instaladas.

**Solução:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou
.venv\Scripts\activate     # Windows

pip install -r requirements.txt
pytest tests/ -v
```

### 2. Teste de regressão falhando com `ValueError: Secret obrigatória não encontrada`

**Sintoma:**
```
ValueError: Secret obrigatória não encontrada: 'POSTGRES-HOST'
```

**Causa:** Variáveis de ambiente não definidas.

**Solução:**
```bash
# Copie .env.example
cp .env.example .env

# Edite .env com valores reais
# Mínimo para testes:
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=testdb
POSTGRES_USER=testuser
POSTGRES_PASSWORD=testpass
POSTGRES_SSLMODE=disable

JWT_ALGORITHM=HS256
JWT_SECRET_FALLBACK=local-dev-secret-minimum-32-bytes-long

# Rode testes novamente
cd backend
pytest tests/unit/test_regression.py -v
```

### 3. `psycopg2` não instala no Windows

**Sintoma:**
```
ERROR: Could not build wheels for psycopg2
```

**Causa:** Compilador C++ não disponível.

**Solução:**
```bash
# Use versão binária pré-compilada
pip uninstall psycopg2
pip install psycopg2-binary

# Atualize requirements.txt
# Substitua: psycopg2==2.9.11
# Por:       psycopg2-binary==2.9.11
```

### 4. Azure Functions local não inicia

**Sintoma:**
```
func start
# Sem output ou erro "host.json not found"
```

**Causa:** Executando de diretório errado.

**Solução:**
```bash
# Sempre rode de backend/
cd backend
func start

# Se ainda falhar, verifique Azure Functions Core Tools
func --version
# Deve ser >= 4.0

# Se não instalado:
npm install -g azure-functions-core-tools@4 --unsafe-perm true
```

---

## 🚀 Problemas Comuns — Deploy e CI/CD

### 5. CI falhando com "credential-scan" bloqueado

**Sintoma:**
```
❌ CREDENCIAIS HARDCODED DETECTADAS — corrija antes de fazer merge.
```

**Causa:** Credencial hardcoded detectada no código.

**Solução:**
```bash
# 1. Identifique o arquivo com problema
grep -rn --include="*.py" -E "(sk_live_|pk_live_)" backend/

# 2. Substitua por acesso via services.config
# ERRADO:
stripe_key = "sk_live_abc123..."

# CERTO:
from services.config import get_secret_required
stripe_key = get_secret_required("STRIPE-SECRET-KEY")

# 3. Valide localmente antes de commit
.github/workflows/credential-scan.sh  # Se existir

# 4. Commit e push
git add .
git commit -m "fix: remove hardcoded credential"
git push
```

### 6. Deploy falha com "Health check falhou: HTTP 503"

**Sintoma:**
```
Deploy ok — HTTP 503
❌ Validação pós-deploy falhou
```

**Causa:** App Settings incorretas ou Key Vault inacessível.

**Diagnóstico:**
```bash
# 1. Verifique App Settings
az functionapp config appsettings list \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --query "[?name=='POSTGRES_HOST']"

# Se retornar vazio ou não for ref do Key Vault:
# Esperado: @Microsoft.KeyVault(SecretUri=https://kv-projeto.vault.azure.net/secrets/POSTGRES-HOST/)

# 2. Verifique Managed Identity
az functionapp identity show \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP}

# Se principalId for null, crie:
az functionapp identity assign \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP}
```

**Solução:**
```bash
# Execute script de configuração de Key Vault
cd infra
./setup_keyvault.sh
./set_kv_settings.ps1  # PowerShell

# Ou manualmente:
az functionapp config appsettings set \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --settings "POSTGRES_HOST=@Microsoft.KeyVault(SecretUri=https://kv-projeto.vault.azure.net/secrets/POSTGRES-HOST/)"

# Reinicie o Function App
az functionapp restart \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP}
```

### 7. Preview deploy falha com "Slot creation failed"

**Sintoma:**
```
Slot já existe
Deploy falhou
```

**Causa:** Function App está em plano Consumption (não suporta slots).

**Solução:**
```bash
# Opção 1: Use plano Premium ou Dedicated (recomendado para produção)
az functionapp plan update \
  --name ${APP_SERVICE_PLAN} \
  --resource-group ${RESOURCE_GROUP} \
  --sku EP1  # Elastic Premium

# Opção 2: Desabilite preview workflow (não recomendado)
# Remova .github/workflows/preview.yml
```

### 8. Deploy bem-sucedido mas endpoint retorna 404

**Sintoma:**
```
curl https://{app}.azurewebsites.net/api/my-endpoint
# 404 Not Found
```

**Causa:** Código desatualizado (pacote stale) ou método de deploy incorreto.

**Diagnóstico:**
```bash
# Verifique última modificação dos arquivos no Azure
az functionapp deployment list-publishing-profiles \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP}

# Baixe e inspecione o pacote deployado
az functionapp deployment source show \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP}
```

**Solução:**
```bash
# NUNCA use estes métodos (causam pacote stale):
# ❌ az functionapp deployment source config-zip
# ❌ WEBSITE_RUN_FROM_PACKAGE com blob URL

# SEMPRE use func publish --build remote:
cd backend
func azure functionapp publish ${FUNCTION_APP_NAME} --build remote --python

# Valide
curl https://${FUNCTION_APP_NAME}.azurewebsites.net/api/health
```

---

## 🌐 Problemas com DNS e Cloudflare

### 9. `DNS_PROBE_FINISHED_NXDOMAIN` após configurar domínio

**Sintoma:**
Ao acessar `https://api.meuapp.com`, browser retorna `DNS_PROBE_FINISHED_NXDOMAIN`.

**Causa:** Registro CNAME não criado no Cloudflare.

**Diagnóstico:**
```bash
# Teste resolução DNS
nslookup api.meuapp.com

# Se retornar "** server can't find...", CNAME não existe
```

**Solução:**
```bash
# Opção 1: Use script de automação
cd infra
export CLOUDFLARE_API_TOKEN="seu_token"
export CLOUDFLARE_ZONE_ID="seu_zone_id"
export AZURE_FUNCTION_APP_NAME="meuapp-func"
export CUSTOM_DOMAINS="api.meuapp.com www.meuapp.com"
./setup_cloudflare.sh

# Opção 2: Configure manualmente no Cloudflare Dashboard
# 1. Vá em dash.cloudflare.com → DNS
# 2. Adicione registro:
#    Tipo: CNAME
#    Nome: api
#    Valor: meuapp-func.azurewebsites.net
#    Proxy: OFF (ícone cinza) ← CRÍTICO
#    TTL: Auto

# Aguarde 1-5 minutos e teste novamente
nslookup api.meuapp.com
```

### 10. Custom domain com status "Validating" no Azure

**Sintoma:**
No Azure Portal → Custom domains, status fica "Validating" por mais de 10 minutos.

**Causa:** Proxy Cloudflare ativado (ícone laranja).

**Solução:**
```bash
# 1. No Cloudflare Dashboard, DESATIVE o proxy:
# Vá no registro CNAME → clique no ícone laranja até ficar cinza

# 2. Aguarde 5 minutos

# 3. No Azure Portal, remova e re-adicione custom domain:
az functionapp config hostname delete \
  --webapp-name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --hostname api.meuapp.com

az functionapp config hostname add \
  --webapp-name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --hostname api.meuapp.com

# 4. Após status mudar para "Ready", pode reativar proxy Cloudflare
```

### 11. Certificado SSL não sendo emitido

**Sintoma:**
Custom domain status "Ready" mas HTTPS retorna erro de certificado.

**Causa:** Azure ainda emitindo certificado (pode levar 10-30 min).

**Solução:**
```bash
# 1. Aguarde até 30 minutos após status "Ready"

# 2. Verifique status do certificado
az functionapp config ssl list \
  --resource-group ${RESOURCE_GROUP}

# 3. Se após 30 min ainda não emitiu:
# - Verifique que proxy Cloudflare está OFF
# - Verifique que DNS resolve corretamente (nslookup)
# - Remova e re-adicione custom domain

# 4. Teste HTTPS
curl -I https://api.meuapp.com
```

---

## 💳 Problemas com Pagamentos

### 12. Webhook Stripe não chega

**Sintoma:**
Pagamento aprovado no dashboard Stripe mas sistema não processa.

**Diagnóstico:**
```bash
# 1. Verifique logs de webhooks no Stripe Dashboard
# Eventos → Webhook endpoints → Ver tentativas

# 2. Verifique se endpoint está acessível
curl -X POST https://${FUNCTION_APP_NAME}.azurewebsites.net/api/webhook/stripe \
  -H "Content-Type: application/json" \
  -d '{"type":"test"}'

# Esperado: HTTP 400 (assinatura inválida) — endpoint está vivo
# Se 404: endpoint não existe
# Se 500/503: erro interno

# 3. Verifique segredo do webhook no Key Vault
az keyvault secret show \
  --vault-name kv-${PROJECT} \
  --name STRIPE-WEBHOOK-SECRET
```

**Solução:**
```bash
# Se endpoint não acessível:
# 1. Verifique que função foi deployada
ls backend/api/webhook_stripe.py

# 2. Re-deploy
cd backend
func azure functionapp publish ${FUNCTION_APP_NAME} --build remote --python

# Se segredo incorreto:
# 1. Obtenha segredo correto no Stripe Dashboard
# 2. Atualize Key Vault
az keyvault secret set \
  --vault-name kv-${PROJECT} \
  --name STRIPE-WEBHOOK-SECRET \
  --value "whsec_..."

# 3. Reinicie Function App
az functionapp restart --name ${FUNCTION_APP_NAME} --resource-group ${RESOURCE_GROUP}
```

### 13. PIX Mercado Pago não gera QR Code

**Sintoma:**
```python
result = create_mp_pix(...)
# KeyError: 'qr_code'
```

**Causa:** Resposta da API do MP diferente do esperado.

**Diagnóstico:**
```python
# Adicione log da resposta completa
import json
response = sdk.payment().create(data)
print(json.dumps(response, indent=2))
```

**Solução:**
```python
# Atualize services/payment.py para ser mais defensivo:
def create_mp_pix(email, amount, description, external_reference):
    # ... código existente ...
    response = sdk.payment().create(data)

    if response["status"] != 201:
        raise ValueError(f"MP API error: {response.get('response', {})}")

    payment_data = response["response"]

    # Acesso defensivo
    transaction_data = (
        payment_data
        .get("point_of_interaction", {})
        .get("transaction_data", {})
    )

    if not transaction_data.get("qr_code"):
        raise ValueError(f"MP não retornou QR code: {payment_data}")

    return {
        "payment_id": payment_data["id"],
        "status": payment_data["status"],
        "qr_code": transaction_data["qr_code"],
        "qr_code_base64": transaction_data.get("qr_code_base64", ""),
    }
```

---

## 🤖 Problemas com Azure OpenAI

### 14. `DeploymentNotFound` ao chamar LLM

**Sintoma:**
```
openai.NotFoundError: The deployment 'gpt-4o' does not exist
```

**Causa:** Deployment não existe no recurso Azure OpenAI provisionado.

**Diagnóstico:**
```bash
# Liste deployments disponíveis
az cognitiveservices account deployment list \
  --name ${OPENAI_RESOURCE_NAME} \
  --resource-group ${RESOURCE_GROUP}
```

**Solução:**
```python
# Use fallback chain em vez de hardcode:
_DEPLOYMENTS = [
    os.environ.get("AZURE_OPENAI_DEPLOYMENT", ""),
    "gpt-4o-mini",
    "gpt-35-turbo",
]
_DEPLOYMENTS = [d for d in _DEPLOYMENTS if d]

for deployment in _DEPLOYMENTS:
    try:
        response = client.chat.completions.create(
            model=deployment,
            messages=[...],
        )
        logger.info("Deployment usado: %s", deployment)
        break
    except openai.NotFoundError:
        logger.warning("Deployment %s não encontrado, tentando próximo", deployment)
        continue
else:
    # Todos falharam
    logger.error("Nenhum deployment disponível")
    return json_response({"error": "servico_indisponivel"}, status=503)
```

### 15. Rate limit (429) do Azure OpenAI

**Sintoma:**
```
openai.RateLimitError: Rate limit reached for gpt-4o-mini
```

**Causa:** TPM (tokens por minuto) excedido.

**Solução:**
```python
# Implemente retry com backoff exponencial:
import time
from openai import RateLimitError

def call_openai_with_retry(client, deployment, messages, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=deployment,
                messages=messages,
            )
        except RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt  # 1s, 2s, 4s
            logger.warning("Rate limit, aguardando %ds (tentativa %d/%d)",
                          wait_time, attempt + 1, max_retries)
            time.sleep(wait_time)
```

---

## 📊 Problemas com Observabilidade

### 16. Application Insights não mostra logs

**Sintoma:**
Logs não aparecem no Application Insights após deploy.

**Diagnóstico:**
```bash
# 1. Verifique instrumentation key
az monitor app-insights component show \
  --app ${APPINSIGHTS_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --query instrumentationKey

# 2. Verifique se está configurada no Function App
az functionapp config appsettings list \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --query "[?name=='APPINSIGHTS_INSTRUMENTATIONKEY']"
```

**Solução:**
```bash
# Se não configurada:
INSTRUMENTATION_KEY=$(az monitor app-insights component show \
  --app ${APPINSIGHTS_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --query instrumentationKey -o tsv)

az functionapp config appsettings set \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --settings "APPINSIGHTS_INSTRUMENTATIONKEY=${INSTRUMENTATION_KEY}"

# Reinicie
az functionapp restart --name ${FUNCTION_APP_NAME} --resource-group ${RESOURCE_GROUP}

# Aguarde 5 minutos e verifique logs
az monitor app-insights query \
  --app ${APPINSIGHTS_APP_ID} \
  --analytics-query "traces | where timestamp > ago(5m) | take 10"
```

---

## 🆘 Quando Tudo Mais Falhar

### Rollback para versão anterior

```bash
# Liste deployments recentes
az functionapp deployment list \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP}

# Rollback para commit específico
az functionapp deployment source sync \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP}
```

### Reiniciar do zero

```bash
# 1. Backup do código atual
git push origin $(git branch --show-current)

# 2. Delete resource group (⚠️  CUIDADO — apaga TUDO)
az group delete --name ${RESOURCE_GROUP} --yes

# 3. Re-crie do template
# Siga SETUP_README.md desde o início
```

### Obter ajuda

1. **Logs completos**: `az monitor app-insights query ...` (veja MONITORING_GUIDE.md)
2. **Valide configuração**: `python infra/validate_project.py`
3. **Abra issue**: https://github.com/contatoexcelverton-org/saas-project-template/issues
4. **Inclua na issue**:
   - Output de `validate_project.py`
   - Logs relevantes do Application Insights
   - Passos para reproduzir o problema
   - O que já tentou

---

## 📚 Referências

- [AI Agent Dev Guide](AI_AGENT_DEV_GUIDE.md)
- [Monitoring Guide](MONITORING_GUIDE.md)
- [Setup Guide](SETUP_README.md)
- [Copilot Instructions](.github/copilot-instructions.md)
