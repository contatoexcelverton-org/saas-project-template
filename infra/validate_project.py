#!/usr/bin/env python3
"""
validate_project.py — Validação pós-setup do projeto

Execute após provisionar os recursos Azure para confirmar que tudo está correto.
Falhas críticas impedem o deploy. Avisos são informativos.

Uso:
    python infra/validate_project.py
    python infra/validate_project.py --env staging
    python infra/validate_project.py --skip-dns  # Para validação antes de configurar DNS
"""
import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path


# Cores para output no terminal
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

_errors: list[str] = []
_warnings: list[str] = []
_passed: list[str] = []


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")
    _passed.append(msg)


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {msg}")
    _warnings.append(msg)


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")
    _errors.append(msg)


def section(title: str) -> None:
    print(f"\n{BOLD}{'─' * 50}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'─' * 50}{RESET}")


# ---------------------------------------------------------------------------
# Carrega .env se existir
# ---------------------------------------------------------------------------

def load_dotenv() -> None:
    env_file = Path(__file__).parent.parent / ".env"
    if not env_file.exists():
        warn(f"Arquivo .env não encontrado em {env_file} — usando apenas env vars do shell")
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key not in os.environ:
            os.environ[key] = value.strip('"').strip("'")


# ---------------------------------------------------------------------------
# Verificações
# ---------------------------------------------------------------------------

def check_env_vars() -> None:
    """Verifica que todas as variáveis obrigatórias estão definidas."""
    section("Variáveis de ambiente")
    required = [
        "POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD",
        "JWT_SECRET",
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
        "MERCADOPAGO_ACCESS_TOKEN", "MERCADOPAGO_WEBHOOK_SECRET",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_KEYVAULT_URL",
        "FUNCTION_APP_NAME",
    ]
    optional = [
        "AZURE_OPENAI_DEPLOYMENT",
        "ENVIRONMENT",
        "SITE_URL",
        "GOOGLE_CLIENT_ID",
        "SENDGRID_API_KEY",
    ]
    for var in required:
        value = os.environ.get(var, "")
        if not value:
            fail(f"{var} — NÃO DEFINIDA (obrigatória)")
        elif any(bad in value.lower() for bad in ["sk_live", "sk_test_live", "todo", "changeme"]):
            warn(f"{var} — Parece um placeholder, confirme o valor real")
        else:
            ok(f"{var} — OK")
    for var in optional:
        if os.environ.get(var):
            ok(f"{var} — OK (opcional)")
        else:
            warn(f"{var} — não definida (opcional, pode ser necessária)")


def check_postgres() -> None:
    """Tenta conexão TCP com o PostgreSQL."""
    section("PostgreSQL")
    host = os.environ.get("POSTGRES_HOST", "")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))
    if not host:
        fail("POSTGRES_HOST não definida — pulando verificação de conectividade")
        return
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
        ok(f"Conexão TCP com {host}:{port} — OK")
    except (OSError, TimeoutError) as e:
        fail(f"Não foi possível conectar a {host}:{port} — {e}")


def check_keyvault() -> None:
    """Verifica se o Key Vault responde (via az CLI ou SDK)."""
    section("Azure Key Vault")
    vault_url = os.environ.get("AZURE_KEYVAULT_URL", "")
    if not vault_url:
        fail("AZURE_KEYVAULT_URL não definida")
        return
    result = subprocess.run(
        ["az", "keyvault", "show", "--id", vault_url, "--query", "name", "-o", "tsv"],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        ok(f"Key Vault acessível: {result.stdout.strip()}")
    else:
        fail(f"Key Vault não encontrado ou sem permissão: {vault_url}\n"
             f"     {result.stderr.strip()}")


def check_function_app() -> None:
    """Verifica se o Function App existe e está Running."""
    section("Azure Function App")
    app_name = os.environ.get("FUNCTION_APP_NAME", "")
    if not app_name:
        fail("FUNCTION_APP_NAME não definida")
        return
    result = subprocess.run(
        ["az", "functionapp", "show", "--name", app_name,
         "--query", "{state:state,url:defaultHostName}", "-o", "json"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        import json
        try:
            info = json.loads(result.stdout)
            state = info.get("state", "?")
            url = info.get("url", "?")
            if state == "Running":
                ok(f"{app_name} — State: {state} | URL: https://{url}")
            else:
                warn(f"{app_name} — State: {state} (esperado: Running)")
        except json.JSONDecodeError:
            warn(f"Resposta inesperada do az CLI: {result.stdout[:200]}")
    else:
        fail(f"Function App '{app_name}' não encontrado: {result.stderr.strip()}")


def check_dns(skip_dns: bool) -> None:
    """Verifica resolução DNS dos domínios customizados."""
    section("DNS Customizado")
    if skip_dns:
        warn("DNS skipped (--skip-dns). Execute novamente após configurar o Cloudflare.")
        return
    site_url = os.environ.get("SITE_URL", "")
    if not site_url:
        warn("SITE_URL não definida — pulando verificação de DNS")
        return
    domain = site_url.replace("https://", "").replace("http://", "").rstrip("/")
    try:
        results = socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)
        ips = [r[4][0] for r in results]
        ok(f"{domain} → {', '.join(ips[:3])}")
    except socket.gaierror as e:
        fail(
            f"DNS não resolve para {domain}: {e}\n"
            f"     → Adicione registro CNAME ou A no Cloudflare\n"
            f"     → Verifique Custom Domain no Azure SWA/Web App"
        )


def check_no_credentials_in_code() -> None:
    """Grep básico por credenciais hardcoded."""
    section("Scan de segredos no código")
    repo_root = Path(__file__).parent.parent
    patterns = [
        ("sk_live_", "Stripe live key"),
        ("pk_live_", "Stripe publishable live key"),
        ("password=", "Senha hardcoded"),
        ("secret=", "Secret hardcoded"),
        ("BEGIN PRIVATE KEY", "Chave privada"),
        ("BEGIN RSA PRIVATE", "Chave RSA privada"),
    ]
    found = False
    exclude_dirs = {".venv", "__pycache__", ".git", "node_modules", ".env.example"}
    for pattern, label in patterns:
        for path in repo_root.rglob("*.py"):
            if any(excl in path.parts for excl in exclude_dirs):
                continue
            content = path.read_text(errors="ignore")
            if pattern.lower() in content.lower():
                fail(f"{label} encontrado em {path.relative_to(repo_root)}")
                found = True
    if not found:
        ok("Nenhum padrão de credencial hardcoded detectado em arquivos .py")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Valida o projeto antes do deploy")
    parser.add_argument("--env", default="development", help="Ambiente alvo")
    parser.add_argument("--skip-dns", action="store_true", help="Pula verificação de DNS")
    parser.add_argument("--skip-azure", action="store_true", help="Pula verificações que exigem az login")
    args = parser.parse_args()

    print(f"\n{BOLD}{'═' * 50}{RESET}")
    print(f"{BOLD}  Validação do projeto — ambiente: {args.env}{RESET}")
    print(f"{BOLD}{'═' * 50}{RESET}")

    load_dotenv()
    check_env_vars()
    check_postgres()
    check_no_credentials_in_code()

    if not args.skip_azure:
        check_keyvault()
        check_function_app()

    check_dns(args.skip_dns)

    # Resumo
    print(f"\n{BOLD}{'═' * 50}{RESET}")
    print(f"{BOLD}  Resultado{RESET}")
    print(f"{BOLD}{'═' * 50}{RESET}")
    print(f"  {GREEN}✓ Passaram: {len(_passed)}{RESET}")
    print(f"  {YELLOW}⚠ Avisos:   {len(_warnings)}{RESET}")
    print(f"  {RED}✗ Erros:    {len(_errors)}{RESET}")

    if _errors:
        print(f"\n{RED}{BOLD}  ❌ Validação FALHOU — corrija os erros antes de fazer deploy.{RESET}\n")
        sys.exit(1)
    elif _warnings:
        print(f"\n{YELLOW}{BOLD}  ⚠  Validação passou com avisos — revise os pontos acima.{RESET}\n")
    else:
        print(f"\n{GREEN}{BOLD}  ✅ Tudo OK — projeto pronto para deploy.{RESET}\n")


if __name__ == "__main__":
    main()
