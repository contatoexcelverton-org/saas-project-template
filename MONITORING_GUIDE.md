# Guia de Monitoramento e Observabilidade — Produção

## 🎯 Visão Geral

Este guia estabelece práticas de monitoramento e observabilidade para micro-SaaS em produção, prevenindo falhas e permitindo diagnóstico rápido quando problemas ocorrem.

**Princípio fundamental**: Instrumentar ANTES de fazer deploy. Não descubra problemas pelo usuário.

---

## 📊 Stack de Observabilidade

### Azure Application Insights (obrigatório)

Instrumente TODA função e endpoint com Application Insights:

```python
# backend/services/telemetry.py
import logging
from applicationinsights import TelemetryClient
from services.config import get_secret

# Singleton do telemetry client
_telemetry_client = None

def get_telemetry_client():
    global _telemetry_client
    if _telemetry_client is None:
        instrumentation_key = get_secret("APPINSIGHTS-INSTRUMENTATION-KEY", "")
        if instrumentation_key:
            _telemetry_client = TelemetryClient(instrumentation_key)
    return _telemetry_client

def track_event(name: str, properties: dict = None, measurements: dict = None):
    """Registra evento customizado."""
    client = get_telemetry_client()
    if client:
        client.track_event(name, properties, measurements)
        client.flush()

def track_exception(exception: Exception, properties: dict = None):
    """Registra exceção com contexto."""
    client = get_telemetry_client()
    if client:
        client.track_exception(type(exception), exception, None, properties)
        client.flush()

def track_metric(name: str, value: float, properties: dict = None):
    """Registra métrica customizada."""
    client = get_telemetry_client()
    if client:
        client.track_metric(name, value, properties=properties)
        client.flush()
```

### Padrão de instrumentação em endpoints

```python
# backend/api/my_endpoint.py
import logging
import azure.functions as func
from services.telemetry import track_event, track_exception, track_metric
from time import time

logger = logging.getLogger(__name__)

def my_endpoint(req: func.HttpRequest) -> func.HttpResponse:
    start_time = time()
    conn = None

    try:
        # Log da requisição
        track_event("my_endpoint_request", {
            "method": req.method,
            "url": req.url,
            "user_agent": req.headers.get("User-Agent", "unknown"),
        })

        conn = get_pg_connection()
        # ... lógica do endpoint ...

        # Métricas de sucesso
        duration = time() - start_time
        track_metric("my_endpoint_duration_ms", duration * 1000)
        track_event("my_endpoint_success")

        return json_response({"ok": True})

    except ValueError as e:
        # Erro esperado (validação)
        logger.warning("Validação falhou: %s", e)
        track_event("my_endpoint_validation_error", {"error": str(e)})
        return json_response({"error": str(e)}, status=400)

    except psycopg2.OperationalError as e:
        # Erro de infraestrutura
        logger.error("DB indisponível: %s", e)
        track_exception(e, {"context": "database_connection"})
        return json_response({"error": "servico_indisponivel"}, status=503)

    except Exception as e:
        # Erro inesperado (bug)
        logger.exception("Erro inesperado em my_endpoint")
        track_exception(e, {
            "endpoint": "my_endpoint",
            "method": req.method,
        })
        return json_response({"error": "erro_interno"}, status=500)

    finally:
        if conn:
            return_pg_connection(conn)
```

---

## 🚨 Alertas Obrigatórios

Configure estes alertas no Application Insights para TODOS os projetos:

### 1. Taxa de erro HTTP ≥ 5%

```kql
requests
| where timestamp > ago(5m)
| summarize
    total = count(),
    errors = countif(resultCode >= 400)
| extend error_rate = (errors * 100.0) / total
| where error_rate >= 5.0
```

**Ação**: Notifica via email/SMS imediatamente.

### 2. Health check falhando

```kql
requests
| where timestamp > ago(2m)
| where name == "health_check"
| where resultCode != 200
| summarize count()
| where count() >= 2
```

**Ação**: Rollback automático via webhook.

### 3. Tempo de resposta > 5s (P95)

```kql
requests
| where timestamp > ago(10m)
| summarize p95 = percentile(duration, 95) by name
| where p95 > 5000
```

**Ação**: Notifica time de infra.

### 4. Exceções não tratadas

```kql
exceptions
| where timestamp > ago(5m)
| where type !in ("ValueError", "KeyError")  // Exceções esperadas
| summarize count() by type, outerMessage
| where count() >= 3
```

**Ação**: Notifica desenvolvedor de plantão.

### 5. Rate de tentativas de login falhadas > 10/min

```kql
customEvents
| where timestamp > ago(1m)
| where name == "login_failed"
| summarize count()
| where count() > 10
```

**Ação**: Notifica segurança (possível ataque).

---

## 📈 Dashboards Obrigatórios

### Dashboard de Saúde do Sistema

Métricas exibidas (atualização a cada 1 min):

1. **Disponibilidade** (uptime %)
   ```kql
   requests
   | where timestamp > ago(1h)
   | summarize
       total = count(),
       success = countif(resultCode < 400)
   | extend uptime = (success * 100.0) / total
   ```

2. **Latência P50, P95, P99**
   ```kql
   requests
   | where timestamp > ago(1h)
   | summarize
       p50 = percentile(duration, 50),
       p95 = percentile(duration, 95),
       p99 = percentile(duration, 99)
   ```

3. **Taxa de erro por endpoint**
   ```kql
   requests
   | where timestamp > ago(1h)
   | summarize
       total = count(),
       errors = countif(resultCode >= 400)
       by name
   | extend error_rate = (errors * 100.0) / total
   | order by error_rate desc
   ```

4. **Dependências externas (Stripe, MP, OpenAI)**
   ```kql
   dependencies
   | where timestamp > ago(1h)
   | summarize
       total = count(),
       failures = countif(success == false)
       by target
   | extend failure_rate = (failures * 100.0) / total
   ```

### Dashboard de Negócio

Métricas de produto (atualização a cada 5 min):

1. **Cadastros por hora**
   ```kql
   customEvents
   | where timestamp > ago(24h)
   | where name == "user_registered"
   | summarize count() by bin(timestamp, 1h)
   ```

2. **Taxa de conversão (cadastro → assinatura)**
   ```kql
   customEvents
   | where timestamp > ago(7d)
   | summarize
       registrations = countif(name == "user_registered"),
       subscriptions = countif(name == "subscription_created")
   | extend conversion_rate = (subscriptions * 100.0) / registrations
   ```

3. **Revenue por gateway (Stripe vs MP)**
   ```kql
   customEvents
   | where timestamp > ago(30d)
   | where name == "payment_success"
   | extend gateway = tostring(customDimensions.gateway)
   | extend amount = todouble(customDimensions.amount)
   | summarize total = sum(amount) by gateway
   ```

4. **Uso de IA (tokens, custo estimado)**
   ```kql
   customEvents
   | where timestamp > ago(24h)
   | where name == "openai_completion"
   | extend tokens = toint(customMeasurements.tokens)
   | extend cost = todouble(customMeasurements.cost_usd)
   | summarize
       total_tokens = sum(tokens),
       total_cost = sum(cost)
   ```

---

## 🔍 Queries Úteis de Diagnóstico

### 1. Rastrear requisição por ID

```kql
union requests, dependencies, exceptions, traces
| where timestamp > ago(1h)
| where operation_Id == "SEU_OPERATION_ID"
| order by timestamp asc
| project timestamp, itemType, name, resultCode, duration, message
```

### 2. Identificar endpoint mais lento

```kql
requests
| where timestamp > ago(1h)
| summarize avg(duration), p95=percentile(duration, 95) by name
| order by p95 desc
| take 10
```

### 3. Usuários afetados por erro

```kql
exceptions
| where timestamp > ago(1h)
| extend user_id = tostring(customDimensions.user_id)
| where isnotempty(user_id)
| summarize count() by user_id, type
| order by count_ desc
```

### 4. Dependência causando timeout

```kql
dependencies
| where timestamp > ago(1h)
| where duration > 5000 or success == false
| summarize count(), avg(duration) by target, name
| order by count_ desc
```

### 5. Cold start (Azure Functions)

```kql
requests
| where timestamp > ago(1h)
| where duration > 10000  // > 10s
| extend cold_start = customDimensions.cold_start
| where cold_start == "true"
| summarize count() by bin(timestamp, 1h)
```

---

## 🛠️ Instrumentação Customizada

### Eventos de negócio

```python
from services.telemetry import track_event

# Cadastro de usuário
track_event("user_registered", {
    "email": email,  # hash se for sensível
    "source": "web",
    "has_referral": str(referral_code is not None),
})

# Assinatura criada
track_event("subscription_created", {
    "plan": plan_id,
    "gateway": "stripe",
    "trial": str(trial_days > 0),
}, {
    "amount": float(amount),
})

# Pagamento aprovado
track_event("payment_success", {
    "gateway": "mercadopago",
    "method": "pix",
    "customer_id": customer_id,
}, {
    "amount": float(amount),
})
```

### Métricas de performance

```python
from services.telemetry import track_metric
from time import time

# Tempo de query
start = time()
result = execute_query()
track_metric("db_query_duration_ms", (time() - start) * 1000, {
    "query_type": "user_search",
})

# Uso de tokens OpenAI
track_metric("openai_tokens_used", tokens, {
    "model": deployment,
    "user_id": user_id,
})

# Tamanho de payload
track_metric("api_response_size_bytes", len(json.dumps(response)), {
    "endpoint": "list_products",
})
```

---

## 🔐 Logs Seguros — O que NUNCA logar

### ❌ Proibido logar:

- Senhas (mesmo hasheadas)
- Tokens JWT completos
- Chaves de API (Stripe, MP, OpenAI)
- CPF completo (use mascaramento: `***.***.123-45`)
- Dados de cartão de crédito
- OTPs ou códigos de verificação

### ✅ Permitido logar:

```python
# Email (use hash se muito sensível)
logger.info("Login tentado: email=%s", email)

# IDs (sempre seguros)
logger.info("User ID: %s", user_id)

# Status de operação
logger.info("Payment status: %s", status)

# Metadata
logger.info("Request from IP: %s, user-agent: %s", ip, user_agent)
```

---

## 📞 Runbook de Incidentes

### Cenário 1: Taxa de erro subiu para 20%

**Sintomas:**
- Dashboard mostra 20% de HTTP 5xx
- Alertas disparando

**Diagnóstico:**
```bash
# 1. Identifique endpoint problemático
az monitor app-insights query \
  --app ${APPINSIGHTS_APP_ID} \
  --analytics-query "requests | where timestamp > ago(10m) | where resultCode >= 500 | summarize count() by name | order by count_ desc"

# 2. Veja logs do endpoint
az monitor app-insights query \
  --app ${APPINSIGHTS_APP_ID} \
  --analytics-query "exceptions | where timestamp > ago(10m) | where operation_Name == 'problematic_endpoint' | take 20"
```

**Ações:**
1. Se erro de DB → Verifique Azure Database for PostgreSQL (CPU, conexões)
2. Se erro de Key Vault → Verifique Managed Identity
3. Se erro de OpenAI → Verifique quota e deployment
4. **Último recurso**: Rollback para versão anterior

### Cenário 2: Health check falhando

**Sintomas:**
- `/api/health` retornando 503 ou 500
- App inacessível

**Diagnóstico:**
```bash
# Teste direto
curl -v https://${FUNCTION_APP_NAME}.azurewebsites.net/api/health

# Verifique status do Function App
az functionapp show \
  --name ${FUNCTION_APP_NAME} \
  --resource-group ${RESOURCE_GROUP} \
  --query state
```

**Ações:**
1. Se `state != "Running"` → Reinicie: `az functionapp restart ...`
2. Se DB offline → Verifique Azure Database status
3. Se App Settings erradas → Valide refs Key Vault
4. **Último recurso**: Rollback automático (já configurado no CI)

### Cenário 3: Spike de latência (P95 > 10s)

**Sintomas:**
- Usuários reportam lentidão
- Dashboard mostra P95 > 10s

**Diagnóstico:**
```bash
# Identifique dependência lenta
az monitor app-insights query \
  --app ${APPINSIGHTS_APP_ID} \
  --analytics-query "dependencies | where timestamp > ago(10m) | where duration > 5000 | summarize avg(duration), count() by target"
```

**Ações:**
1. Se DB lenta → Verifique índices, queries sem otimização
2. Se OpenAI lenta → Reduza max_tokens ou use modelo mais rápido
3. Se cold start → Considere Always On ou Premium plan
4. Escale horizontalmente se CPU > 80%

### Cenário 4: Pagamentos não processando

**Sintomas:**
- Usuários reportam pagamento travado
- Webhooks Stripe/MP não chegando

**Diagnóstico:**
```bash
# Verifique webhooks recebidos
az monitor app-insights query \
  --app ${APPINSIGHTS_APP_ID} \
  --analytics-query "customEvents | where timestamp > ago(1h) | where name in ('stripe_webhook_received', 'mp_webhook_received') | summarize count() by name"

# Verifique assinatura de webhooks
grep "webhook.*invalid" backend/logs/*
```

**Ações:**
1. Verifique segredo de webhook no Key Vault
2. Teste manualmente: `curl -X POST https://${URL}/api/webhook/stripe -d @test_payload.json`
3. Verifique se Cloudflare não está bloqueando IPs do Stripe/MP
4. Re-envie webhook pelo dashboard Stripe/MP

---

## 📋 Checklist Pré-Deploy (Observabilidade)

Valide ANTES de fazer merge para `main`:

- [ ] Endpoint instrumentado com `track_event` no sucesso
- [ ] Exceções instrumentadas com `track_exception`
- [ ] Métricas de performance (duração) instrumentadas
- [ ] Logs não contém dados sensíveis
- [ ] Query KQL de diagnóstico documentada
- [ ] Alerta configurado se endpoint é crítico
- [ ] Dashboard atualizado com nova métrica (se aplicável)

---

## 🔗 Links Úteis

- [Application Insights Portal](https://portal.azure.com/#blade/HubsExtension/BrowseResource/resourceType/microsoft.insights%2Fcomponents)
- [Azure Monitor Docs](https://docs.microsoft.com/azure/azure-monitor/)
- [KQL Reference](https://docs.microsoft.com/azure/data-explorer/kusto/query/)
- [Python Application Insights SDK](https://docs.microsoft.com/azure/azure-monitor/app/opencensus-python)

---

## 🆘 Suporte

Se encontrar um incidente que este runbook não cobre:

1. Documente no Application Insights (query + resultado)
2. Atualize este runbook com novo cenário
3. Abra post-mortem: https://github.com/contatoexcelverton-org/{projeto}/issues
