"""
Health check — Azure Function HTTP trigger
Valida conectividade com dependências críticas.
"""
import json
import logging
import os

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Endpoint de health check para validação pós-deploy."""
    checks = {"status": "ok", "checks": {}}

    # Verifica PostgreSQL
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.environ["POSTGRES_HOST"],
            database=os.environ["POSTGRES_DB"],
            user=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            connect_timeout=3,
        )
        conn.close()
        checks["checks"]["postgres"] = "ok"
    except Exception as e:
        checks["checks"]["postgres"] = f"error: {str(e)}"
        checks["status"] = "degraded"

    # Verifica Key Vault (se configurado)
    kv_url = os.environ.get("AZURE_KEYVAULT_URL")
    if kv_url:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            client = SecretClient(vault_url=kv_url, credential=DefaultAzureCredential())
            list(client.list_properties_of_secrets(max_page_size=1))
            checks["checks"]["keyvault"] = "ok"
        except Exception as e:
            checks["checks"]["keyvault"] = f"error: {str(e)}"
            checks["status"] = "degraded"

    status_code = 200 if checks["status"] == "ok" else 503
    return func.HttpResponse(
        json.dumps(checks),
        status_code=status_code,
        mimetype="application/json",
    )
