"""
_base.py — Helpers seguros para scripts utilitários

REGRA ABSOLUTA: Todo script em scripts/ DEVE importar daqui.
NUNCA hardcode host, user, password, token ou qualquer credencial em scripts.

Uso:
    from _base import get_pg_dsn, get_admin_token, require_env
    conn = psycopg2.connect(**get_pg_dsn())
"""
import os
import sys
from pathlib import Path

# Carrega .env automaticamente quando executado localmente
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).parent.parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file)
        print(f"[_base] .env carregado de {_env_file}")
except ImportError:
    pass  # python-dotenv não instalado — ok em CI


def require_env(*names: str) -> None:
    """Valida que todas as variáveis de ambiente estão definidas.
    Falha com mensagem clara listando o que está faltando.
    """
    missing = [n for n in names if not os.environ.get(n)]
    if missing:
        print(f"\n❌ Variáveis de ambiente obrigatórias não encontradas:")
        for n in missing:
            print(f"   - {n}")
        print("\n   Configure no .env (dev local) ou exporte antes de executar.")
        sys.exit(1)


def get_pg_dsn() -> dict:
    """Retorna dict de conexão PostgreSQL lido de env vars.
    Falha com mensagem clara se alguma variável estiver faltando.
    """
    require_env("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "sslmode": os.environ.get("POSTGRES_SSLMODE", "require"),
        "connect_timeout": 10,
    }


def get_pg_connection_string() -> str:
    """Retorna connection string PostgreSQL para psycopg2.connect(dsn_string)."""
    dsn = get_pg_dsn()
    return (
        f"host={dsn['host']} port={dsn['port']} dbname={dsn['dbname']} "
        f"user={dsn['user']} password={dsn['password']} "
        f"sslmode={dsn['sslmode']} connect_timeout={dsn['connect_timeout']}"
    )


def get_admin_token() -> str:
    """Retorna token de admin lido de env var. Falha se não estiver definido."""
    require_env("ADMIN_TOKEN")
    return os.environ["ADMIN_TOKEN"]


def get_env(name: str, default: str = "") -> str:
    """Busca variável de ambiente com default explícito."""
    return os.environ.get(name, default)


def get_env_required(name: str) -> str:
    """Busca variável de ambiente obrigatória. Falha se não encontrar."""
    require_env(name)
    return os.environ[name]
