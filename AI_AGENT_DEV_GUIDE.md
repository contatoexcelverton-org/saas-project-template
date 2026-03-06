# Guia de Desenvolvimento com Agentes de IA — Excelverton SaaS Template

## 🎯 Visão Geral

Este guia otimiza o fluxo de desenvolvimento usando GitHub Copilot (Claude) ou outros agentes de IA para construir micro-SaaS seguros e robustos.

**Princípio fundamental**: Código gerado por IA deve ter a mesma qualidade e segurança que código escrito manualmente.

---

## 📋 Checklist Antes de Começar Qualquer Feature

**SEMPRE execute este checklist antes de pedir ao agente para implementar algo:**

### 1. Leia as instruções do projeto
```bash
cat .github/copilot-instructions.md
```
O agente lê este arquivo automaticamente, mas você deve entendê-lo também.

### 2. Rode os testes ANTES de qualquer mudança
```bash
cd backend
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Se **algum teste já estiver quebrando**, corrija ANTES de adicionar código novo.
Nunca adicione funcionalidade sobre uma base quebrada.

### 3. Valide o alinhamento código ↔ infra

- [ ] O deployment Azure OpenAI existe? (verifique no Azure Portal)
- [ ] Constraints do banco refletem as regras de negócio?
- [ ] `.env.example` está atualizado com todas as variáveis?
- [ ] Secrets estão no Key Vault (produção) ou `.env` (local)?

---

## 🤖 Como Pedir Features ao Agente de IA

### ✅ CORRETO — Pedido claro e alinhado com a arquitetura

```
Implementar endpoint POST /api/verify-otp que:
1. Recebe email e código OTP
2. Valida OTP contra o hash no banco
3. Se válido: marca email_verified = TRUE e emite JWT access + refresh
4. Se inválido: retorna 401

Requisitos de segurança:
- Usar services.config.get_secret() para segredos
- Padrão defensivo: conn = None antes do try
- Logar tentativas no Application Insights

Escreva os testes PRIMEIRO em tests/unit/test_auth.py
```

**Por quê funciona:**
- Especifica TODAS as regras de negócio
- Menciona padrões de segurança explícitos
- Pede testes antes de implementação (TDD)
- Define erro handling esperado

### ❌ ERRADO — Pedido vago

```
Faz um endpoint de verificação de OTP
```

**Por quê falha:**
- Não especifica validação
- Não define comportamento de erro
- Não menciona segurança
- Não pede testes

---

## 🛡️ Regras de Segurança — NUNCA NEGOCIE

### 1. Credenciais centralizadas

**ERRADO:**
```python
# ❌ NUNCA
stripe_key = os.environ.get("STRIPE_SECRET_KEY", "sk_live_abc123")
```

**CERTO:**
```python
# ✅ SEMPRE
from services.config import get_secret_required
stripe_key = get_secret_required("STRIPE-SECRET-KEY")
```

### 2. Conexões de banco defensivas

**ERRADO:**
```python
# ❌ Crash em finally se get_pg_connection falhar
def meu_endpoint(req):
    try:
        conn = get_pg_connection()  # se falhar aqui
        # ...
    finally:
        return_pg_connection(conn)  # UnboundLocalError
```

**CERTO:**
```python
# ✅ conn = None ANTES do try
def meu_endpoint(req):
    conn = None
    try:
        conn = get_pg_connection()
        # ...
    except psycopg2.OperationalError as e:
        logger.error("DB indisponível: %s", e)
        return json_response({"error": "servico_indisponivel"}, status=503)
    finally:
        if conn:
            return_pg_connection(conn)
```

### 3. Fallback chain para Azure OpenAI

**ERRADO:**
```python
# ❌ Hardcoded deployment
client.chat.completions.create(model="gpt-4o", ...)
```

**CERTO:**
```python
# ✅ Fallback chain
_DEPLOYMENTS = [
    os.environ.get("AZURE_OPENAI_DEPLOYMENT", ""),
    "gpt-4o-mini",
    "gpt-35-turbo",
]
_DEPLOYMENTS = [d for d in _DEPLOYMENTS if d]

for deployment in _DEPLOYMENTS:
    try:
        response = client.chat.completions.create(model=deployment, ...)
        logger.info("Deployment usado: %s", deployment)
        break
    except openai.NotFoundError:
        continue
else:
    return json_response({"error": "servico_indisponivel"}, status=503)
```

---

## 🧪 TDD com Agentes de IA — Fluxo Obrigatório

### Passo 1: Escreva o teste
```python
# tests/unit/test_verify_otp.py
def test_otp_valido_marca_email_verified(mock_db):
    """Após OTP correto, email_verified deve ser TRUE."""
    # Arrange
    mock_db.set_user("user@test.com", otp_hash=hash_otp("123456"), email_verified=False)

    # Act
    response = verify_otp_endpoint(email="user@test.com", otp="123456")

    # Assert
    assert response.status_code == 200
    user = mock_db.get_user("user@test.com")
    assert user["email_verified"] is True
```

### Passo 2: Implemente a funcionalidade
```python
# api/verify_otp.py
def verify_otp_endpoint(req):
    conn = None
    try:
        data = req.get_json()
        email = data["email"]
        otp = data["otp"]

        conn = get_pg_connection()
        cur = conn.cursor()
        cur.execute("SELECT otp_hash FROM users WHERE email = %s", (email,))
        row = cur.fetchone()

        if not row or hash_otp(otp) != row[0]:
            return json_response({"error": "otp_invalido"}, status=401)

        cur.execute(
            "UPDATE users SET email_verified = TRUE WHERE email = %s",
            (email,)
        )
        conn.commit()

        # Emitir tokens...
        return json_response({"ok": True}, status=200)

    except Exception as e:
        logger.exception("Erro ao verificar OTP")
        return json_response({"error": "erro_interno"}, status=500)
    finally:
        if conn:
            return_pg_connection(conn)
```

### Passo 3: Valide
```bash
# Rode APENAS o novo teste
pytest tests/unit/test_verify_otp.py -v

# Rode regressão para garantir que nada quebrou
pytest tests/unit/test_regression.py -v

# Cobertura
pytest tests/ -v -k "verify_otp" --cov=api --cov-report=term-missing
```

---

## 🚨 Armadilhas Comuns com Agentes de IA

### Armadilha 1: Agente remove testes de regressão

**Sintoma:**
```
Claude: "Removi testes duplicados de test_regression.py para limpar o código"
```

**Solução:**
```
NÃO! test_regression.py é INTOCÁVEL. Nunca remova ou desabilite testes deste arquivo.
Se um teste está falhando, corrija o código, não o teste.
```

### Armadilha 2: Agente hardcoda credenciais de teste

**Sintoma:**
```python
# ❌ Gerado pelo agente
stripe.api_key = "sk_test_abc123..."
```

**Solução:**
```
Use mock ou fixture. Nunca hardcode credenciais, mesmo de teste.

@pytest.fixture
def mock_stripe():
    with patch("stripe.Customer.create") as mock:
        mock.return_value = MagicMock(id="cus_test")
        yield mock
```

### Armadilha 3: Agente cria endpoint sem validação

**Sintoma:**
```python
# ❌ Gerado pelo agente — não valida input
def endpoint(req):
    email = req.get_json()["email"]  # KeyError se email faltando
```

**Solução:**
```
SEMPRE valide entrada com try/except ou biblioteca de validação.

def endpoint(req):
    try:
        data = req.get_json()
        email = data.get("email")
        if not email:
            return json_response({"error": "email_obrigatorio"}, status=400)
        # ...
    except Exception as e:
        logger.exception("Erro ao processar request")
        return json_response({"error": "request_invalido"}, status=400)
```

### Armadilha 4: Agente usa método de deploy incorreto

**Sintoma:**
```yaml
# ❌ Gerado pelo agente no CI
- name: Deploy
  run: az functionapp deployment source config-zip ...
```

**Solução:**
```yaml
# ✅ Método correto
- name: Deploy
  run: |
    cd backend
    func azure functionapp publish ${{ vars.AZURE_FUNCTION_APP_NAME }} \
      --build remote --python
```

**Por quê:** `config-zip` causa pacote stale. `--build remote` compila no Azure.

---

## 🔍 Validação Pre-Commit — Automatize

Crie `.git/hooks/pre-commit`:

```bash
#!/bin/bash
set -e

echo "🔍 Pre-commit validation..."

# 1. Scan de credenciais
echo "Verificando credenciais hardcoded..."
if grep -rn --include="*.py" -E "(sk_live_|pk_live_)" backend/; then
    echo "❌ Credencial hardcoded detectada"
    exit 1
fi

# 2. Testes de regressão
echo "Rodando testes de regressão..."
cd backend
if ! pytest tests/unit/test_regression.py -q; then
    echo "❌ Testes de regressão falharam"
    exit 1
fi

echo "✅ Pre-commit passou"
```

Torne executável:
```bash
chmod +x .git/hooks/pre-commit
```

---

## 🔄 Loop de Iteração — Agente Local com CI/CD

**NOVA FUNCIONALIDADE**: O agente local agora pode monitorar CI/CD e iterar automaticamente.

### Fluxo Completo:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Agente implementa feature localmente                    │
│    - Escreve testes primeiro (TDD)                          │
│    - Implementa código                                       │
│    - Valida padrões de segurança                           │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Testes locais                                            │
│    cd backend && pytest tests/ -v                           │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Commit + Push                                            │
│    git add . && git commit -m "..." && git push             │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Monitorar CI/CD                                          │
│    ./infra/monitor_ci_status.sh                             │
│                                                              │
│    Exit codes:                                              │
│    - 0: Passou → continua                                   │
│    - 1: Falhou → lê logs e volta para 2                    │
│    - 2: Rodando → aguarda e checa novamente                │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Validar Preview (se disponível)                         │
│    - URL: https://{app}-pr{num}.azurewebsites.net          │
│    - Testa cadastro + OTP                                   │
│    - Testa pagamento Mercado Pago                           │
│    - Valida chatbot (se aplicável)                         │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Checklist de Aceitação                                  │
│    - Email é chave única? ✓                                 │
│    - Credenciais no Key Vault? ✓                            │
│    - GA4 configurado? ✓                                     │
│    - Tudo funcional? ✓                                      │
└────────────────┬────────────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Informa usuário: PRONTO PARA PRODUÇÃO                   │
└─────────────────────────────────────────────────────────────┘
```

### Script de Monitoramento:

```bash
# O agente executa após cada push
./infra/monitor_ci_status.sh

# Output exemplo:
# ==========================================
#   Monitor CI/CD — Branch: feature/new-payment
# ==========================================
#
# Último commit: a3b5c7d
#
# Workflows encontrados:
#   - CI — Testes e Qualidade: completed (success)
#   - Pre-Deploy Validation: completed (success)
#   - Agent Validation: completed (success)
#
# ✅ CI — Testes e Qualidade passou
# ✅ Pre-Deploy Validation passou
# ✅ Agent Validation passou
#
# ==========================================
#   RESULTADO
# ==========================================
#
# ✅ TODOS OS WORKFLOWS PASSARAM
#
# O agente pode prosseguir para o próximo passo
```

### Exemplo de Iteração Automática:

```python
# Pseudocódigo do que o agente deve fazer

def implement_feature(feature_request):
    while True:
        # 1. Implementa
        write_tests(feature_request)
        write_code(feature_request)

        # 2. Testa localmente
        result = run_tests_local()
        if not result.passed:
            fix_failing_tests()
            continue

        # 3. Commit + push
        git_commit_and_push()

        # 4. Monitora CI/CD
        ci_status = monitor_ci_status()

        if ci_status == "running":
            sleep(60)  # Aguarda 1 minuto
            continue

        if ci_status == "failed":
            logs = get_failure_logs()
            analyze_and_fix(logs)
            continue

        # 5. CI passou — valida preview
        if preview_available():
            preview_status = test_preview_e2e()
            if not preview_status.passed:
                fix_preview_issues()
                continue

        # 6. Checklist de aceitação
        checklist = validate_acceptance_criteria()
        if not checklist.all_passed:
            implement_missing_items(checklist.missing)
            continue

        # 7. Sucesso!
        notify_user("✅ Feature completa e validada. Pronto para produção.")
        break
```

### Checklist de Aceitação Automático:

O workflow `agent-validation.yml` valida automaticamente:

```yaml
✅ Validações Locais:
  - Testes de regressão
  - Cobertura ≥80%
  - Sem credenciais hardcoded
  - Email é chave única

✅ Preview E2E:
  - Health check
  - Endpoint de registro
  - Endpoint de pagamento
  - Key Vault conectado

📋 Checklist Manual (agente verifica):
  - [ ] Cadastro + OTP funcional no preview
  - [ ] Mercado Pago PIX funciona (credenciais teste do KV)
  - [ ] Chatbot envia/recebe (se aplicável)
  - [ ] GA4 configurado
```

### Como o Agente USA o Monitor:

No VS Code com Claude:

```
Usuário: "Implementa pagamento PIX com Mercado Pago"

Claude: "Vou implementar. Seguindo o fluxo de iteração:

1. ✅ Implementei testes em tests/unit/test_payment.py
2. ✅ Implementei endpoint /api/create-pix
3. ✅ Testes locais passando
4. ✅ Commit + push realizado
5. ⏳ Monitorando CI/CD...

[Executa: ./infra/monitor_ci_status.sh]

6. ❌ CI falhou — Gate 4: Secret acessado fora de config.py

[Lê logs, identifica problema]

7. ✅ Corrigi: importado get_secret_required()
8. ✅ Testes locais passando novamente
9. ✅ Commit + push da correção
10. ⏳ Monitorando CI/CD novamente...

[Executa: ./infra/monitor_ci_status.sh]

11. ✅ Todos os workflows passaram
12. ✅ Preview disponível em: https://app-pr123.azurewebsites.net
13. 🧪 Testando preview...
    - Health check: ✅
    - Endpoint /api/create-pix: ✅ (retorna QR code)
    - Webhook valida assinatura: ✅
14. ✅ Checklist de aceitação completo

PRONTO! Feature validada e funcional. Pode fazer merge."
```

---

## 📊 Monitoramento de Deploy — Validação Pós-Deploy

### Script de validação automática

```bash
#!/bin/bash
# infra/post_deploy_validation.sh

FUNCTION_APP_URL="https://$1.azurewebsites.net"

echo "Validando deploy em $FUNCTION_APP_URL"

# 1. Health check
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$FUNCTION_APP_URL/api/health")
if [ "$STATUS" != "200" ]; then
    echo "❌ Health check falhou: HTTP $STATUS"
    exit 1
fi
echo "✅ Health check: OK"

# 2. Teste de autenticação (smoke test)
REGISTER_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "$FUNCTION_APP_URL/api/register" \
    -H "Content-Type: application/json" \
    -d '{"email":"invalid"}')

if [ "$REGISTER_STATUS" != "400" ]; then
    echo "❌ Endpoint /register não está validando input"
    exit 1
fi
echo "✅ Validação de input: OK"

# 3. Teste de pagamento (verifica integração Stripe)
STRIPE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "$FUNCTION_APP_URL/api/plans")

if [ "$STRIPE_STATUS" != "200" ]; then
    echo "❌ Endpoint /plans não está respondendo"
    exit 1
fi
echo "✅ Integração Stripe: OK"

echo ""
echo "✅ VALIDAÇÃO PÓS-DEPLOY PASSOU"
```

Use no CI:
```yaml
- name: Validação pós-deploy
  run: |
    chmod +x infra/post_deploy_validation.sh
    ./infra/post_deploy_validation.sh ${{ vars.AZURE_FUNCTION_APP_NAME }}
```

---

## 🌐 Integração com Cloudflare — Checklist

### 1. Configuração de DNS no Cloudflare

Para cada domínio personalizado:

```bash
# Obtenha o CNAME do Azure
az functionapp show \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --query defaultHostName -o tsv

# No Cloudflare Dashboard:
# Tipo: CNAME
# Nome: @ (ou subdomínio)
# Valor: {FUNCTION_APP_NAME}.azurewebsites.net
# Proxy: OFF (ícone cinza) ← CRÍTICO para custom domains Azure
# TTL: Auto
```

### 2. Adicione domínio no Azure

```bash
az functionapp config hostname add \
  --webapp-name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --hostname ${CUSTOM_DOMAIN}
```

### 3. Validação automática de DNS

```python
# backend/tests/unit/test_dns_availability.py
import socket

REQUIRED_DOMAINS = [
    "api.meuapp.com.br",
    "app.meuapp.com.br",
]

def test_dns_resolution():
    """Valida que todos os domínios do projeto resolvem."""
    for domain in REQUIRED_DOMAINS:
        try:
            ip = socket.gethostbyname(domain)
            assert ip, f"DNS {domain} não resolve"
        except socket.gaierror:
            pytest.fail(f"DNS {domain} não encontrado")
```

Rode antes de cada deploy:
```bash
pytest backend/tests/unit/test_dns_availability.py -v
```

### 4. Script de configuração de Cloudflare via API

```bash
# infra/setup_cloudflare.sh
#!/bin/bash
set -e

ZONE_ID="${CLOUDFLARE_ZONE_ID}"
API_TOKEN="${CLOUDFLARE_API_TOKEN}"
AZURE_CNAME="${FUNCTION_APP_NAME}.azurewebsites.net"

# Adiciona registro CNAME
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "type": "CNAME",
    "name": "api",
    "content": "'${AZURE_CNAME}'",
    "ttl": 1,
    "proxied": false
  }'

echo "✅ DNS configurado no Cloudflare"
```

---

## 📦 Deploy com Preview URLs — Validação Antes de Produção

O workflow `preview.yml` já cria URLs temporárias para cada PR:
```
https://{app}-pr{número}.azurewebsites.net/api/health
```

### Como usar com agentes de IA

1. **Abra PR com feature nova**
```bash
git checkout -b feature/new-payment-flow
git push origin feature/new-payment-flow
gh pr create --title "Add PIX payment flow"
```

2. **Aguarde o bot comentar a URL de preview no PR**

3. **Valide APENAS a feature nova**
```bash
# Teste apenas o que foi pedido ao agente
curl https://{app}-pr123.azurewebsites.net/api/create-pix \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"amount": 29.90, "email": "test@test.com"}'
```

4. **O resto é garantido pelos testes de regressão**

Se regressão passou no CI, o resto do app funciona. Não teste tudo manualmente.

---

## 🎓 Boas Práticas — Resumo

| O que fazer | Por quê | Como verificar |
|------------|---------|----------------|
| **TDD obrigatório** | Código sem teste = código quebrado aguardando para falhar | `pytest tests/unit/test_*.py -v` |
| **Regressão intocável** | Garante que novas features não quebram fluxos críticos | `pytest tests/unit/test_regression.py -v` |
| **Secrets no Key Vault** | Credenciais no código = vazamento iminente | `grep -r "sk_live_" backend/` (deve estar vazio) |
| **Padrão defensivo de DB** | `conn = None` antes do try evita crash em finally | Validado no pre-deploy gate 3 |
| **Fallback chain OpenAI** | Deployment pode não existir — resiliência obrigatória | Deploy não deve falhar com 500 |
| **Preview antes de merge** | Catch bugs antes de produção | Teste URL de preview em cada PR |
| **Cloudflare proxy OFF** | Custom domains Azure não funcionam com proxy ativado | `nslookup {domain}` deve resolver |

---

## 🚀 Fluxo Completo — Do Zero ao Deploy

### 1. Clone do template
```bash
gh repo create meu-app --template contatoexcelverton-org/saas-project-template --private
cd meu-app
```

### 2. Setup local
```bash
cp .env.example .env
# Edite .env com valores de desenvolvimento

cd backend
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r requirements.txt

# Valide ambiente
pytest tests/ -v
```

### 3. Configure Azure (primeira vez)
```bash
# Crie resource group
az group create --name rg-meuapp --location brazilsouth

# Deploy infra
az deployment group create \
  --resource-group rg-meuapp \
  --template-file infra/main.bicep \
  --parameters @infra/parameters.json

# Configure OIDC (GitHub → Azure sem secrets)
az ad app federated-credential create \
  --id {CLIENT_ID} \
  --parameters '{
    "name": "github-oidc-meuapp",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:contatoexcelverton-org/meu-app:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'

# Configure variáveis no repo GitHub
gh variable set AZURE_CLIENT_ID --body "{CLIENT_ID}"
gh variable set AZURE_TENANT_ID --body "{TENANT_ID}"
gh variable set AZURE_SUBSCRIPTION_ID --body "{SUBSCRIPTION_ID}"
gh variable set AZURE_FUNCTION_APP_NAME --body "meuapp-func"
gh variable set AZURE_RESOURCE_GROUP --body "rg-meuapp"
```

### 4. Desenvolva com agente de IA
```bash
# No VS Code com Copilot
# Ou com Claude Code no terminal

# SEMPRE leia as instruções primeiro
cat .github/copilot-instructions.md

# Peça feature ao agente
"Implementar endpoint POST /api/create-subscription que integra com Stripe.
Requisitos: validação de input, conn = None defensivo, testes em test_payment.py"
```

### 5. Valide localmente
```bash
# Rode testes
pytest tests/ -v

# Regressão obrigatória
pytest tests/unit/test_regression.py -v

# Cobertura
pytest tests/ --cov=services --cov-report=term-missing
```

### 6. Abra PR
```bash
git checkout -b feature/stripe-subscription
git add .
git commit -m "feat: add Stripe subscription endpoint"
git push origin feature/stripe-subscription

gh pr create --title "Add Stripe subscription" --body "Closes #123"
```

### 7. Valide preview
```bash
# Aguarde bot comentar URL de preview
# Teste APENAS a feature nova
curl https://meuapp-pr456.azurewebsites.net/api/create-subscription \
  -X POST -H "Content-Type: application/json" \
  -d '{"customer_id": "cus_test", "price_id": "price_test"}'
```

### 8. Merge para produção
```bash
# Se preview ok e testes passando
gh pr merge --squash

# CI automaticamente:
# 1. Re-roda todos os testes
# 2. Valida gates de qualidade
# 3. Faz deploy para Azure
# 4. Valida health check
# 5. Rollback se falhar
```

---

## 📞 Troubleshooting

### Deploy falhou mas testes passaram

**Causa:** Configuração de infra incorreta (Key Vault, App Settings).

**Solução:**
```bash
# Valide pós-setup
python infra/validate_project.py

# Verifique App Settings
az functionapp config appsettings list \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP}

# Secrets devem ter formato:
# @Microsoft.KeyVault(SecretUri=https://kv-{project}.vault.azure.net/secrets/{name}/)
```

### Agente gerou código com credencial hardcoded

**Causa:** Pedido ao agente não especificou uso de services.config.

**Solução:**
```
# Na próxima iteração, seja explícito:
"Refatore X para usar services.config.get_secret_required() em vez de os.environ"

# Valide antes de commit:
grep -rn "os.environ.get" backend/ --include="*.py" \
  --exclude-dir={tests,.venv} \
  | grep -E "(SECRET|KEY|TOKEN|PASSWORD)"
```

### Testes passam localmente mas falham no CI

**Causa:** Dependência de estado local (.env com valores específicos).

**Solução:**
```python
# Use monkeypatch ou pytest fixtures para isolar testes
def test_algo(monkeypatch):
    monkeypatch.setenv("VARIAVEL", "valor_de_teste")
    # seu teste aqui
```

---

## ✅ Checklist Final Antes de Produção

- [ ] Todos os testes de regressão passam
- [ ] Cobertura ≥80% em auth e payment
- [ ] Nenhuma credencial hardcoded (scan passou)
- [ ] Preview URL validada manualmente
- [ ] DNS configurado e validado
- [ ] Key Vault populado com todos os secrets
- [ ] App Settings apontam para Key Vault (não env vars)
- [ ] Application Insights configurado
- [ ] Health check retorna 200

**Se todos os itens acima estão ✅, pode fazer merge para `main`.**

---

## 📚 Links Úteis

- [Instruções do Copilot](.github/copilot-instructions.md)
- [Checklist de Custom Domain](SETUP_README.md#checklist-de-custom-domain)
- [Arquitetura Bicep](infra/main.bicep)
- [Validação de Projeto](infra/validate_project.py)
- [GitHub Actions Workflows](.github/workflows/)

---

## 🆘 Suporte

Se encontrar um problema que este guia não cobre:

1. Verifique os logs no Application Insights do Azure
2. Revise `.github/copilot-instructions.md` (contém regras detalhadas)
3. Rode validação pós-setup: `python infra/validate_project.py`
4. Abra issue no template: https://github.com/contatoexcelverton-org/saas-project-template/issues
