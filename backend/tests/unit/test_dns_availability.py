"""
test_dns_availability.py — Resolução de DNS obrigatória

Previne DNS_PROBE_FINISHED_NXDOMAIN silencioso em produção/preview.
Roda em todo pytest run — sem flag especial.

⚠️  CUSTOMIZAR POR PROJETO:
    Edite REQUIRED_DOMAINS com os domínios reais do projeto.
    Adicione novos domínios sempre que criar um Custom Domain no Azure.

Por que isso existe:
    No projeto erpdev (mar/2026), o site ficou fora do ar por CNAME ausente no
    Cloudflare enquanto o Custom Domain no SWA mostrava "Ready".
    Nenhum teste detectou — só o usuário final descobriu.
"""
import os
import socket

import pytest

# ---------------------------------------------------------------------------
# ⚠️  CUSTOMIZAR POR PROJETO — lista de domínios obrigatórios
# ---------------------------------------------------------------------------
# Substitua pelos domínios reais. Deixe vazio ([]) se o projeto não tiver
# domínio customizado ainda (testes serão marcados como skip).
# ---------------------------------------------------------------------------
REQUIRED_DOMAINS: list[str] = [
    # "exemplo.com.br",
    # "www.exemplo.com.br",
    # "app.exemplo.com.br",
    # "api.exemplo.com.br",
]

# Domínios internos do Azure usados antes de configurar DNS customizado
# (sempre devem funcionar se o recurso existir)
AZURE_INTERNAL_DOMAINS: list[str] = [
    # "{app}.azurewebsites.net",
    # "{swa}.azurestaticapps.net",
]


# ---------------------------------------------------------------------------
# Testes de DNS customizado
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    len(REQUIRED_DOMAINS) == 0,
    reason="REQUIRED_DOMAINS vazio — configure com os domínios do projeto",
)
class TestDNSResolution:
    """Valida que todos os domínios do projeto resolvem via DNS."""

    @pytest.mark.parametrize("domain", REQUIRED_DOMAINS)
    def test_domain_resolve(self, domain: str):
        """DNS deve resolver para o domínio — falha = CNAME ou A ausente."""
        try:
            results = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
            assert len(results) > 0, f"getaddrinfo retornou vazio para {domain}"
        except socket.gaierror as e:
            pytest.fail(
                f"\n❌ DNS FALHOU para: {domain}\n"
                f"   Erro: {e}\n\n"
                f"   Possíveis causas:\n"
                f"   1. CNAME ausente no Cloudflare → dash.cloudflare.com → DNS\n"
                f"   2. Registro A incorreto ou apontando para IP errado\n"
                f"   3. Custom Domain não configurado no Azure SWA/Web App\n\n"
                f"   Para diagnosticar:\n"
                f"   $ nslookup {domain}\n"
                f"   $ az staticwebapp hostname list --name <SWA_NAME> -o table"
            )


@pytest.mark.skipif(
    len(AZURE_INTERNAL_DOMAINS) == 0,
    reason="AZURE_INTERNAL_DOMAINS vazio — configure com os hostnames Azure do projeto",
)
class TestAzureInternalDNS:
    """Valida domínios internos do Azure (.azurewebsites.net, .azurestaticapps.net)."""

    @pytest.mark.parametrize("domain", AZURE_INTERNAL_DOMAINS)
    def test_azure_domain_resolve(self, domain: str):
        """Domínio interno Azure deve sempre resolver se o recurso existir."""
        try:
            results = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
            assert len(results) > 0
        except socket.gaierror as e:
            pytest.fail(
                f"\n❌ DNS Azure FALHOU para: {domain}\n"
                f"   Erro: {e}\n\n"
                f"   Possíveis causas:\n"
                f"   1. Recurso Azure deletado ou nome incorreto\n"
                f"   2. Recurso em outro region/subscription\n\n"
                f"   Verifique: az functionapp show --name <APP> -o table"
            )


# ---------------------------------------------------------------------------
# Utilitário de diagnóstico (não é um teste — execute manualmente)
# ---------------------------------------------------------------------------

def diagnose_domain(domain: str) -> None:  # pragma: no cover
    """Execute diretamente para diagnosticar um domínio:
        python -c "from test_dns_availability import diagnose_domain; diagnose_domain('meusite.com.br')"
    """
    print(f"\n🔍 Diagnóstico de DNS: {domain}")
    try:
        results = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
        print(f"  ✅ Resolve para:")
        for r in results:
            print(f"     {r[4][0]}")
    except socket.gaierror as e:
        print(f"  ❌ Não resolve: {e}")
