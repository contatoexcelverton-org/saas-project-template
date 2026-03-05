"""
config.py — Acesso centralizado a credenciais

⛔ PROIBIDO: os.environ.get() para segredos em qualquer outro arquivo.
✅ OBRIGATÓRIO: from services.config import get_secret, get_secret_required

Hierarquia de busca:
1. Azure Key Vault (produção — via Managed Identity)
2. Variáveis de ambiente / .env (desenvolvimento local)

Conversão automática: hífens ↔ underscores
  get_secret("STRIPE-SECRET-KEY")  →  os.environ["STRIPE_SECRET_KEY"]
  get_secret("pg-admin-password")  →  os.environ["PG_ADMIN_PASSWORD"]
"""
import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

# Singleton do SecretClient por vault URL
_kv_clients: dict = {}


def _get_kv_client():
    """Retorna SecretClient do Azure Key Vault (singleton por URL)."""
    vault_url = os.environ.get("AZURE_KEYVAULT_URL", "").rstrip("/")
    if not vault_url:
        return None
    if vault_url not in _kv_clients:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            _kv_clients[vault_url] = SecretClient(
                vault_url=vault_url,
                credential=DefaultAzureCredential(),
            )
            logger.debug("KV client inicializado: %s", vault_url)
        except Exception as e:
            logger.warning("Não foi possível inicializar KV client: %s", e)
            return None
    return _kv_clients[vault_url]


def get_secret(name: str, default: str = "") -> str:
    """Busca secret por nome. Key Vault primeiro, fallback em env var.

    Args:
        name: Nome do secret. Hífens e underscores são intercambiáveis.
        default: Valor padrão se não encontrado. Use "" — NUNCA um valor real.

    Exemplos:
        get_secret("STRIPE-SECRET-KEY")    # env: STRIPE_SECRET_KEY
        get_secret("pg-admin-password")    # env: PG_ADMIN_PASSWORD
        get_secret("JWT_ALGORITHM", "HS256")  # com default não-sensível
    """
    client = _get_kv_client()
    if client:
        try:
            value = client.get_secret(name).value
            if value is not None:
                return value
        except Exception as e:
            # Loga e faz fallback para env var (não levanta exceção)
            logger.warning("KV miss para '%s', tentando env var: %s", name, e)

    # Fallback: env var com underscores maiúsculos
    env_name = name.replace("-", "_").upper()
    value = os.environ.get(env_name, default)
    if not value and not default:
        logger.debug("Secret '%s' não encontrado em KV nem em env var", name)
    return value


def get_secret_required(name: str) -> str:
    """Como get_secret, mas levanta ValueError se não encontrar.

    Use para segredos que tornam o app inoperante se ausentes.
    O erro intencionalmente expõe o nome da variável para facilitar debug.
    """
    value = get_secret(name)
    if not value:
        raise ValueError(
            f"Secret obrigatória não encontrada: '{name}'. "
            f"Configure AZURE_KEYVAULT_URL (produção) ou "
            f"{name.replace('-', '_').upper()} (dev local)."
        )
    return value


def get_db_url() -> str:
    """Monta URL de conexão PostgreSQL a partir de secrets individuais."""
    host = get_secret_required("POSTGRES-HOST")
    port = get_secret("POSTGRES-PORT", "5432")
    db = get_secret_required("POSTGRES-DB")
    user = get_secret_required("POSTGRES-USER")
    password = get_secret_required("POSTGRES-PASSWORD")
    sslmode = get_secret("POSTGRES-SSLMODE", "require")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}?sslmode={sslmode}"


def get_pg_dsn() -> dict:
    """Retorna dict com parâmetros de conexão para psycopg2.connect(**dsn)."""
    return {
        "host": get_secret_required("POSTGRES-HOST"),
        "port": int(get_secret("POSTGRES-PORT", "5432")),
        "dbname": get_secret_required("POSTGRES-DB"),
        "user": get_secret_required("POSTGRES-USER"),
        "password": get_secret_required("POSTGRES-PASSWORD"),
        "sslmode": get_secret("POSTGRES-SSLMODE", "require"),
        "connect_timeout": 5,
    }


# ---------------------------------------------------------------------------
# Helpers de configuração não-sensível (plain env vars)
# ---------------------------------------------------------------------------

def get_env(name: str, default: str = "") -> str:
    """Busca variável de ambiente não-sensível (sem Key Vault).
    Use para: ENVIRONMENT, LOG_LEVEL, SITE_URL, etc.
    """
    return os.environ.get(name, default)


def is_production() -> bool:
    return get_env("ENVIRONMENT", "development").lower() == "production"


def is_test() -> bool:
    return get_env("ENVIRONMENT", "development").lower() == "test"
