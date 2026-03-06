# {{PROJECT_NAME}}

> Projeto SaaS — Excelverton  
> Arquitetura: Azure Functions (Python) + PostgreSQL + Azure OpenAI + Key Vault

## Setup local

```bash
# 1. Clone e instale dependências
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt

# 2. Configure variáveis locais
cp .env.example .env
# Edite .env com seus valores de desenvolvimento

# 3. Rode os testes
pytest tests/ -v --cov=. --cov-report=term-missing

# 4. Testes críticos com cobertura mínima
pytest tests/ -v -k "auth or payment" --cov=services --cov-fail-under=80

# 5. Inicie as Azure Functions localmente
func start
```

## Variáveis de ambiente
Veja `.env.example` para a lista completa.  
**Em produção todas as variáveis sensíveis são referências ao Key Vault** nas App Settings do Azure Functions.

## Deploy
- **Automático**: push para `main` dispara o workflow `deploy.yml` (requer testes verdes)
- **Manual (emergência)**: `gh workflow run deploy.yml`

## Configuração Azure (first time)
```bash
# 1. Cria o resource group
az group create --name rg-{PROJECT} --location brazilsouth

# 2. Deploy da infraestrutura
az deployment group create \
  --resource-group rg-{PROJECT} \
  --template-file infra/main.bicep \
  --parameters @infra/parameters.json

# 3. Configura OIDC para GitHub Actions (sem client secret)
az ad app federated-credential create \
  --id {CLIENT_ID} \
  --parameters '{"name":"github-oidc","issuer":"https://token.actions.githubusercontent.com","subject":"repo:contatoexcelverton-org/{REPO}:ref:refs/heads/main","audiences":["api://AzureADTokenExchange"]}'

# 4. Define variáveis de repositório (não secrets — são públicas por design)
gh variable set AZURE_CLIENT_ID --body "{CLIENT_ID}"
gh variable set AZURE_TENANT_ID --body "{TENANT_ID}"
gh variable set AZURE_SUBSCRIPTION_ID --body "{SUBSCRIPTION_ID}"
gh variable set AZURE_FUNCTION_APP_NAME --body "{FUNCTION_APP_NAME}"
gh variable set AZURE_RESOURCE_GROUP --body "{RESOURCE_GROUP}"
```

## Estrutura do projeto
```
backend/
  api/        # Azure Functions HTTP triggers
  agents/     # Lógica dos agentes LLM
  services/   # auth.py, payment.py, storage.py, speech.py...
  tests/
    unit/       # Sem I/O externo — rodam rápido
    integration/ # Com banco e APIs (rodam no CI com services Docker)
frontend/
  public/     # Entry points PHP
infra/
  main.bicep  # Toda a infra Azure
  setup_cloudflare.sh    # Automação DNS Cloudflare
  post_deploy_validation.sh  # Smoke tests pós-deploy
  validate_project.py    # Validação de configuração
.github/
  copilot-instructions.md  # Instruções para o agente Copilot
  workflows/
    ci.yml      # Testes em todo PR
    pre-deploy-validation.yml  # 5 gates de qualidade
    preview.yml  # Deploy de preview por PR
    deploy.yml  # Deploy para Azure (main branch)
```

## Guias e Documentação

- **[AI_AGENT_DEV_GUIDE.md](AI_AGENT_DEV_GUIDE.md)** — Guia completo para desenvolvimento com agentes de IA (GitHub Copilot, Claude Code)
- **[MONITORING_GUIDE.md](MONITORING_GUIDE.md)** — Observabilidade, dashboards, alertas e runbook de incidentes
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Resolução de problemas comuns (desenvolvimento, deploy, DNS, pagamentos)
- **[SETUP_README.md](SETUP_README.md)** — Configuração inicial do template e checklist de custom domains
- **[.github/copilot-instructions.md](.github/copilot-instructions.md)** — Instruções arquiteturais para agentes de IA

## Agentes especializados
> Documente aqui os agentes deste projeto, o que cada um faz e qual Azure AI Search index usa.

## Links úteis
- Azure Portal: https://portal.azure.com
- Function App: https://{FUNCTION_APP_NAME}.azurewebsites.net/api/health
Template padrao para todos os projetos SaaS - Azure Functions + PostgreSQL + LLM + Auth
