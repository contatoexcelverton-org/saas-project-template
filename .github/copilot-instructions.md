# Copilot Instructions — Excelverton SaaS Architecture

## LEIA ESTE ARQUIVO COMPLETO ANTES DE QUALQUER AÇÃO

Você é o agente de desenvolvimento principal dos projetos SaaS da Excelverton.
Cada repositório é um produto independente, mas **todos** seguem esta arquitetura.
Seu trabalho só está concluído quando: **código implementado + testes passando (incluindo regressão) + sem credenciais expostas**.

---

## Stack obrigatória
- **Backend**: Python 3.11+ (Azure Functions como orquestrador principal)
- **Frontend**: PHP 8.2+ (sem framework pesado — vanilla ou Laravel leve)
- **Banco de dados**: PostgreSQL (Azure Database for PostgreSQL Flexible Server)
- **Multi-tenancy**: Schema por tenant (nunca misture dados entre tenants no mesmo schema)
- **Autenticação**: Email + código OTP por email OU Entra External ID (OAuth Google/Microsoft)
- **Pagamentos**: Stripe (internacional) + Mercado Pago (Brasil/PIX) — ambos simultâneos
- **IA / Agentes**: Azure OpenAI (GPT-4o por padrão) + Azure AI Search (RAG)
- **Mensageria / Chatbot**: Telegram Bot API e/ou Azure Communication Services (WhatsApp)
- **Armazenamento**: Azure Blob Storage
- **Fala**: Azure Speech Services (STT e TTS)
- **Scraping**: Python (requests + BeautifulSoup ou Playwright headless)
- **Segredos**: Azure Key Vault SEMPRE — nunca credenciais hardcoded ou em variáveis de ambiente direto em produção
- **Observabilidade**: Application Insights em TODA função e endpoint
- **DNS**: Cloudflare (CDN + proteção) apontando para Azure
- **CI/CD**: GitHub Actions com Azure OIDC (sem CLIENT_SECRET armazenado no GitHub)
- **Containers**: GHCR (GitHub Container Registry) — não usar Azure Container Registry

---

## Estrutura de diretórios obrigatória
```
/
├── backend/
│   ├── api/              # Azure Functions HTTP triggers
│   ├── agents/           # Lógica de agentes LLM (LangChain ou Semantic Kernel)
│   ├── services/         # Serviços reutilizáveis (auth, payment, storage, speech)
│   ├── tests/
│   │   ├── unit/
│   │   │   └── test_regression.py   # NUNCA REMOVER — contratos dos fluxos críticos
│   │   └── integration/
│   │       └── test_smoke.py        # Smoke tests pós-deploy
│   ├── requirements.txt
│   └── host.json         # Config Azure Functions
├── frontend/
│   ├── public/           # Entry points PHP
│   └── assets/           # CSS, JS, imagens
├── infra/
│   ├── main.bicep        # Infraestrutura Azure completa
│   └── parameters.json   # Parâmetros por ambiente
├── .github/
│   ├── copilot-instructions.md  # ESTE ARQUIVO
│   └── workflows/
│       ├── ci.yml         # Testes em todo PR (bloqueia merge se falhar)
│       ├── preview.yml    # Deploy de preview por PR com URL temporária
│       └── deploy.yml     # Deploy para Azure (main branch, só com testes verdes)
├── .vscode/
│   ├── extensions.json   # Extensões recomendadas
│   ├── settings.json     # Configurações do workspace
│   └── mcp.json          # Servidores MCP para o agente
├── .env.example           # Template de variáveis locais (sem valores reais)
├── .gitignore
└── README.md
```

---

## Regras de segurança — não negociáveis
1. **Nunca commite credenciais reais**. O push será bloqueado pelo Secret Scanning da org.
2. **`.env` é sempre gitignored**. Use `.env.example` para documentar as variáveis necessárias.
3. **Em produção, todas as variáveis sensíveis vêm do Key Vault** via referência nas App Settings do Azure Functions: `@Microsoft.KeyVault(SecretUri=https://kv-{project}.vault.azure.net/secrets/{name}/)`.
4. **Managed Identity** deve ser usada para autenticar no Key Vault — nunca CLIENT_SECRET.
5. **OIDC no GitHub Actions** — o workflow usa `azure/login@v2` com `client-id`, `tenant-id` e `subscription-id` como variáveis públicas (não secrets). O secret fica no Azure via Federated Credential.

---

## Regras de qualidade e TDD — não negociáveis

### Regra #0 — Regressão obrigatória
**Toda alteração, por menor que seja, deve passar pelos testes de regressão.**
O arquivo `tests/unit/test_regression.py` contém os contratos dos fluxos críticos.
Nunca remova testes existentes. Nunca faça merge com testes quebrando.

### Regra #1 — TDD
Para cada nova feature: escreva o teste primeiro, depois implemente.

### Regra #2 — Cobertura mínima
- `auth` e `payment`: mínimo 80% de cobertura
- Novos módulos: mínimo 70%

### Regra #3 — Fluxos críticos sempre testados
Estes fluxos **nunca** podem quebrar por nenhuma alteração:
- **Cadastro de usuário** (OTP gerado, hash salvo, email simulado)
- **Login** (OTP validado, JWT access + refresh emitidos)
- **Expiração de token** (access expira em 1h, refresh em 7d)
- **Token adulterado** (deve lançar ValueError)
- **Criação de customer Stripe** (retorna customer_id)
- **Criação de assinatura Stripe** (retorna subscription_id + client_secret)
- **Validação de webhook Stripe** (assinatura válida aceita, inválida rejeita)
- **Criação de PIX Mercado Pago** (retorna qr_code + qr_code_base64)
- **Validação de webhook Mercado Pago** (HMAC-SHA256 válido)
- **Health check** endpoint retorna HTTP 200

### Regra #4 — Deploy gate
Nunca faça deploy se algum teste estiver falhando. A ordem é sempre:
```
testes unitários → regressão → integração → cobertura ≥ 80% → deploy
```

### Regra #5 — Ferramentas
- `pytest` + `pytest-cov` + `pytest-asyncio`
- Mocks obrigatórios para Azure SDK, Stripe, Mercado Pago nos testes unitários
- Testes de integração usam PostgreSQL real (container Docker no CI)

---

## Fluxo de trabalho do agente — SEMPRE siga esta ordem

### Para qualquer tarefa (nova feature, alteração, correção):
1. **Leia** `README.md` e `CHANGELOG.md` (se existir) para entender o contexto
2. **Execute os testes existentes ANTES** de qualquer mudança:
   ```bash
   cd backend && pytest tests/ -v --tb=short 2>&1 | tail -20
   ```
   Se algum teste já estiver falhando, reporte e corrija antes de avançar.
3. **Identifique** todos os módulos que serão tocados
4. **Escreva os novos testes** para a feature/alteração pedida
5. **Implemente** o código
6. **Execute todos os testes** novamente — incluindo regressão:
   ```bash
   cd backend && pytest tests/ -v --cov=services --cov-report=term-missing
   ```
7. **Verifique** se não há credenciais no código (grep por 'sk_live', 'password=', etc.)
8. **Só então** faça commit e informe o resultado ao usuário

### Para validação de deploy (preview):
- Todo PR abre automaticamente uma URL de preview via `preview.yml`
- A URL segue o padrão: `https://{app}-pr{número}.azurewebsites.net/api/health`
- Informe esta URL ao usuário para validação antes do merge
- A validação do usuário é focada **apenas na feature pedida** — o restante é garantido pelos testes

### Para deploy em produção:
- Só acontece via merge para `main`
- CI re-executa todos os testes automaticamente
- Se falhar: rollback automático via deployment slot

---

## Agentes especializados de IA — use quando aplicável

Organize o trabalho em sub-agentes especializados quando a task for complexa:

| Agente | Responsabilidade | Arquivo |
|--------|-----------------|--------|
| `TestAgent` | Escreve e mantém testes, valida cobertura | `agents/test_agent.py` |
| `AuthAgent` | Implementa fluxos de auth, OTP, JWT | `agents/auth_agent.py` |
| `PaymentAgent` | Integra Stripe + MP, valida webhooks | `agents/payment_agent.py` |
| `InfraAgent` | Provisiona recursos Azure via Bicep | `agents/infra_agent.py` |
| `ReviewAgent` | Revisa código, detecta credenciais, valida padrões | `agents/review_agent.py` |

Todos os agentes usam Azure OpenAI (GPT-4o) via Key Vault. Instrumente com Application Insights.

---

## Padrão de autenticação
```python
# backend/services/auth.py
# OTP flow: gera código 6 dígitos -> envia por email (Azure Communication Services) -> valida e emite JWT
# JWT: assimétrico (RS256), expiração 1h access + 7d refresh
# Key Vault: segredo JWT_PRIVATE_KEY e JWT_PUBLIC_KEY armazenados no KV
```

---

## Padrão de pagamento
```python
# backend/services/payment.py
# Stripe: planos mensais/anuais + metered billing para consumo de API
# Mercado Pago: PIX + cartão para mercado brasileiro
# Webhooks: Azure Function separada para receber eventos de cada gateway
# Nunca processe pagamento sem validar assinatura do webhook
```

---

## Padrão de agente LLM
```python
# backend/agents/
# Cada agente é especialista em um domínio
# Sempre usa Azure OpenAI (endpoint e key via Key Vault)
# RAG: Azure AI Search como retriever
# Instrumentar TODAS as chamadas LLM com Application Insights (tokens, latência, custo estimado)
```

---

## MCP Servers disponíveis no workspace

O arquivo `.vscode/mcp.json` configura os servidores MCP que o agente pode usar:

- **github**: Criar PRs, ler issues, verificar status de CI, comentar em PRs com URL de preview
- **filesystem**: Leitura e escrita de arquivos do projeto (já embutido no VS Code Copilot)

Use o servidor `github` para verificar se o CI passou antes de reportar conclusão.

---

## Variáveis de ambiente locais (.env)
Veja `.env.example` para a lista completa. Localmente você usa valores reais no `.env`.
Em produção, **todas** essas variáveis são referências ao Key Vault nas App Settings do Azure.

---

## Comandos úteis
```bash
# Rodar TODOS os testes (obrigatório antes de qualquer commit)
cd backend && pytest tests/ -v --cov=. --cov-report=term-missing

# Rodar só regressão crítica (rápido — use para validar durante desenvolvimento)
cd backend && pytest tests/unit/test_regression.py -v

# Testes críticos com cobertura mínima
cd backend && pytest tests/ -v -k "auth or payment or regression" \
  --cov=services --cov-fail-under=80

# Azure Functions local
cd backend && func start

# Deploy manual (emergência — preferir o CI/CD)
az functionapp deployment source config-zip \
  --resource-group rg-{PROJECT} --name {FUNCTION_APP_NAME} \
  --src deploy.zip
```
