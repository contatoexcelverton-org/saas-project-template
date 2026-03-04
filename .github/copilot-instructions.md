# Copilot Instructions — Excelverton SaaS Architecture

## Contexto do projeto
Você é o agente de desenvolvimento de um sistema SaaS. Cada repositório é um produto independente, mas todos seguem esta arquitetura padrão. Leia este arquivo inteiro antes de iniciar qualquer tarefa.

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

## Estrutura de diretórios obrigatória
```
/
├── backend/
│   ├── api/              # Azure Functions HTTP triggers
│   ├── agents/           # Lógica de agentes LLM (LangChain ou Semantic Kernel)
│   ├── services/         # Serviços reutilizáveis (auth, payment, storage, speech)
│   ├── tests/
│   │   ├── unit/         # Testes unitários (sem I/O externo — use mocks)
│   │   └── integration/  # Testes de integração (banco, APIs externas)
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
│       ├── ci.yml         # Testes em todo PR
│       └── deploy.yml     # Deploy para Azure (main branch)
├── .env.example           # Template de variáveis locais (sem valores reais)
├── .gitignore
└── README.md
```

## Regras de segurança — não negociáveis
1. **Nunca commite credenciais reais**. O push será bloqueado pelo Secret Scanning da org.
2. **`.env` é sempre gitignored**. Use `.env.example` para documentar as variáveis necessárias.
3. **Em produção, todas as variáveis sensíveis vêm do Key Vault** via referência nas App Settings do Azure Functions: `@Microsoft.KeyVault(SecretUri=https://kv-{project}.vault.azure.net/secrets/{name}/)`.
4. **Managed Identity** deve ser usada para autenticar no Key Vault — nunca CLIENT_SECRET.
5. **OIDC no GitHub Actions** — o workflow usa `azure/login@v2` com `client-id`, `tenant-id` e `subscription-id` como variáveis públicas (não secrets). O secret fica no Azure via Federated Credential.

## Regras de qualidade e TDD — não negociáveis
1. **Todo PR deve passar nos testes antes de fazer merge**. O workflow `ci.yml` bloqueia merge se falhar.
2. **Cadastro e pagamento NUNCA vão para produção sem testes verdes**. São os módulos mais críticos.
3. Para cada nova feature: escreva o teste primeiro, depois implemente.
4. Cobertura mínima: 80% nos módulos `auth` e `payment`.
5. Use `pytest` com `pytest-cov` para Python. Mocks obrigatórios para Azure SDK e APIs externas nos testes unitários.
6. **Se um teste falhar no CI, não suba para produção.** Corrija antes de pedir deploy.

## Fluxo de trabalho do agente
Quando receber uma tarefa, siga sempre esta ordem:
1. Leia o `README.md` do projeto para entender o contexto específico
2. Verifique se existe teste para o módulo que vai modificar — se não existir, crie antes
3. Implemente a feature seguindo a estrutura de diretórios acima
4. Execute os testes localmente (instrução no README)
5. Verifique se há credenciais expostas antes de commitar
6. Só considere a tarefa concluída quando: código implementado + testes passando + sem credenciais expostas

## Padrão de autenticação
```python
# backend/services/auth.py
# OTP flow: gera código 6 dígitos -> envia por email (Azure Communication Services) -> valida e emite JWT
# JWT: assimétrico (RS256), expiração 1h access + 7d refresh
# Key Vault: segredo JWT_PRIVATE_KEY e JWT_PUBLIC_KEY armazenados no KV
```

## Padrão de pagamento
```python
# backend/services/payment.py
# Stripe: planos mensais/anuais + metered billing para consumo de API
# Mercado Pago: PIX + cartão para mercado brasileiro
# Webhooks: Azure Function separada para receber eventos de cada gateway
# Nunca processe pagamento sem validar assinatura do webhook
```

## Padrão de agente LLM
```python
# backend/agents/
# Cada agente é especialista em um domínio
# Sempre usa Azure OpenAI (endpoint e key via Key Vault)
# RAG: Azure AI Search como retriever
# Instrumentar TODAS as chamadas LLM com Application Insights (tokens, latência, custo estimado)
```

## Variáveis de ambiente locais (.env)
Veja `.env.example` para a lista completa. Localmente você usa valores reais no `.env`.
Em produção, **todas** essas variáveis são referências ao Key Vault nas App Settings do Azure.

## Comandos úteis
```bash
# Rodar testes
cd backend && pytest tests/ -v --cov=. --cov-report=term-missing

# Rodar testes só do módulo crítico
pytest tests/ -v -k "auth or payment" --cov=backend/services --cov-fail-under=80

# Azure Functions local
cd backend && func start

# Deploy manual (emergência — preferir o CI/CD)
az functionapp deployment source config-zip ...
```
