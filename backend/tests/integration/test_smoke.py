"""
test_smoke.py — Smoke tests pós-deploy

Executados APÓS cada deploy para validar que o ambiente de produção/preview
está respondendo corretamente. Requerem a variável FUNCTION_APP_URL.

Uso:
    FUNCTION_APP_URL=https://meu-app.azurewebsites.net pytest tests/integration/test_smoke.py -v

No CI, a URL vem da variável de ambiente injetada pelo workflow preview.yml/deploy.yml.
"""

import os

import pytest
import requests

BASE_URL = os.environ.get("FUNCTION_APP_URL", "").rstrip("/")


# ---------------------------------------------------------------------------
# Pula todos os testes se a URL não estiver configurada
# ---------------------------------------------------------------------------
pytestmark = pytest.mark.skipif(
    not BASE_URL,
    reason="FUNCTION_APP_URL não configurada — smoke tests pulados em desenvolvimento local",
)


class TestHealthCheckSmoke:
    """Valida que o Function App deployado está respondendo."""

    def test_health_endpoint_responde_200(self):
        response = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert response.status_code == 200, (
            f"Health check falhou: HTTP {response.status_code}\n{response.text}"
        )

    def test_health_endpoint_retorna_json_valido(self):
        response = requests.get(f"{BASE_URL}/api/health", timeout=15)
        body = response.json()
        assert "status" in body, f"Campo 'status' ausente no response: {body}"
        assert body["status"] == "ok", f"Status inesperado: {body['status']}"

    def test_health_endpoint_latencia_aceitavel(self):
        """Response deve ser < 5s para indicar que o cold start não está excessivo."""
        import time
        start = time.time()
        requests.get(f"{BASE_URL}/api/health", timeout=15)
        elapsed = time.time() - start
        assert elapsed < 5.0, f"Health check muito lento: {elapsed:.2f}s"
