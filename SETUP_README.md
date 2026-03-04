# Excelverton SaaS Setup — Pacote de Configuração GitHub + Azure

## O que foi feito nesta sessão

### 1. Organização GitHub (`contatoexcelverton-org`)
- **Secret Scanning + Push Protection** ativados — bloqueia commits com credenciais reais
- **Dependabot** ativado — PRs automáticos de segurança para deps Python/PHP

### 2. Repositório Template
URL: https://github.com/contatoexcelverton-org/saas-project-template

Público, marcado como template, com branch protection na `main`:
- CI obrigatório antes de qualquer merge
- Checks: `Testes Python (backend)` e `Verificar credenciais expostas`

### 3. Estrutura do template (nesta pasta)
```
saas-project-template/
├── .github/
│   ├── copilot-instructions.md   # Instruções para o agente Copilot — LEIA ESTE PRIMEIRO
│   └── workflows/
│       ├── ci.yml                # Testes em todo PR (bloqueia merge se falhar)
│       └── deploy.yml            # Deploy Azure via OIDC (só roda com testes verdes)
├── backend/
│   ├── api/health.py             # Health check pós-deploy (valida PG + Key Vault)
│   ├── agents/                   # Lógica dos agentes LLM (Azure OpenAI + AI Search)
│   ├── services/
│   │   ├── auth.py               # OTP por email + JWT RS256 + Key Vault integrado
│   │   └── payment.py            # Stripe (internacional) + Mercado Pago/PIX
│   ├── tests/
│   │   ├── conftest.py           # Setup global dos testes
│   │   └── unit/
│   │       ├── test_auth.py      # 9 testes — OTP, JWT, expiração, tamper
│   │       └── test_payment.py   # 7 testes — Stripe + MP com mocks
│   ├── host.json                 # Config Azure Functions
│   └── requirements.txt          # Stack completa Azure + IA + Pagamentos
├── frontend/
│   └── public/index.php          # Entry point PHP
├── infra/
│   ├── main.bicep                # Infra Azure completa (Functions + PG + KV + AppInsights)
│   └── parameters.json           # Parâmetros — editar por projeto
├── .env.example                  # Mapeamento de todas as variáveis (sem valores reais)
├── .gitignore                    # .env nunca sobe
└── README.md                     # Instruções de setup por projeto
```

---

## Como usar ao criar um novo projeto SaaS

### Passo 1 — Criar repo a partir do template
```
GitHub → contatoexcelverton-org → New repository
→ Selecionar "saas-project-template" como template
→ Nome: nome-do-projeto (ex: erpdev, thepowerbi)
→ Visibilidade: Private
→ Create repository
```

### Passo 2 — Configurar Azure (first time por projeto)
```bash
# Criar resource group
az group create --name rg-PROJETO --location brazilsouth

# Deploy da infraestrutura
az deployment group create \
  --resource-group rg-PROJETO \
  --template-file infra/main.bicep \
  --parameters @infra/parameters.json

# Configurar OIDC (GitHub Actions autentica no Azure sem client secret)
az ad app federated-credential create \
  --id {CLIENT_ID_DO_APP} \
  --parameters '{
    "name": "github-oidc-PROJETO",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:contatoexcelverton-org/NOME-REPO:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'
```

### Passo 3 — Configurar variáveis no repositório GitHub
```bash
# Estas são variáveis públicas (não secrets) — por design do OIDC
gh variable set AZURE_CLIENT_ID --body "SEU_CLIENT_ID" --repo contatoexcelverton-org/NOME-REPO
gh variable set AZURE_TENANT_ID --body "SEU_TENANT_ID" --repo contatoexcelverton-org/NOME-REPO
gh variable set AZURE_SUBSCRIPTION_ID --body "SEU_SUBSCRIPTION_ID" --repo contatoexcelverton-org/NOME-REPO
gh variable set AZURE_FUNCTION_APP_NAME --body "NOME-func" --repo contatoexcelverton-org/NOME-REPO
gh variable set AZURE_RESOURCE_GROUP --body "rg-PROJETO" --repo contatoexcelverton-org/NOME-REPO
```

### Passo 4 — Setup local
```bash
git clone https://github.com/contatoexcelverton-org/NOME-REPO
cd NOME-REPO
cp .env.example .env
# Preencher .env com valores reais de desenvolvimento

cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Rodar testes para confirmar que tudo está ok
pytest tests/ -v --cov=. --cov-report=term-missing
```

### Passo 5 — Abrir no VS Code e começar
```
code .
```
O Copilot lê automaticamente `.github/copilot-instructions.md` e já conhece:
- Toda a arquitetura (Azure Functions + PostgreSQL + OpenAI + Key Vault)
- Regras de segurança (Key Vault obrigatório, nunca credencial no código)
- Fluxo TDD (testa antes, implementa depois)
- Stack completa (auth, payment, agentes, storage, speech, scraping)

---

## Fluxo de deploy automático

```
Push para branch feature
    ↓
PR aberto → CI roda automaticamente
    ↓ (se falhar, merge bloqueado)
Merge para main
    ↓
deploy.yml dispara
    ↓
Testes rodam novamente (obrigatório)
    ↓ (se falhar, deploy não acontece)
Login Azure via OIDC (sem client secret)
    ↓
Azure Functions atualizado
    ↓
Health check: GET /api/health
    ↓ (se falhar, rollback automático)
Deploy concluído
```

---

## Credenciais — regra absoluta

| Ambiente | Como acessar credenciais |
|---|---|
| Local (dev) | `.env` com valores reais — **nunca commitar** |
| CI (GitHub Actions) | Variáveis de ambiente fake para mocks — sem segredos reais |
| Produção (Azure) | App Settings com referências ao Key Vault: `@Microsoft.KeyVault(SecretUri=...)` |

O fluxo em produção: Azure Function → Managed Identity → Key Vault → valor em runtime.
Nenhuma credencial fica no código ou no GitHub.

---

## Referências
- Template: https://github.com/contatoexcelverton-org/saas-project-template
- Org: https://github.com/contatoexcelverton-org
- Azure Portal: https://portal.azure.com
- Copilot instructions: `.github/copilot-instructions.md`
