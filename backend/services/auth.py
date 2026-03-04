"""
Serviço de autenticação — OTP por email + JWT RS256
Credenciais sempre via Key Vault em produção.
"""
import os
import secrets
import string
from datetime import datetime, timedelta, UTC
from typing import Optional

import jwt
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

# -- Key Vault client (Managed Identity em prod, env vars em dev) --

def _get_secret(name: str) -> str:
    kv_url = os.environ.get("AZURE_KEYVAULT_URL")
    if kv_url:
        client = SecretClient(vault_url=kv_url, credential=DefaultAzureCredential())
        return client.get_secret(name).value
    # Fallback para dev local
    return os.environ.get(name.replace("-", "_").upper(), "")


# -- OTP --

def generate_otp(length: int = 6) -> str:
    """Gera código OTP numérico seguro."""
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_otp(otp: str) -> str:
    """Hash simples para armazenar o OTP no banco sem expor o valor real."""
    import hashlib
    return hashlib.sha256(otp.encode()).hexdigest()


# -- JWT --

def _get_algorithm() -> str:
    return os.environ.get("JWT_ALGORITHM", "RS256")


def _get_signing_key() -> str:
    algo = _get_algorithm()
    if algo == "RS256":
        # Em prod vem do Key Vault
        key_path = os.environ.get("JWT_PRIVATE_KEY_PATH")
        if key_path and os.path.exists(key_path):
            return open(key_path).read()
        return _get_secret("JWT-PRIVATE-KEY")
    # HS256 apenas para testes CI
    return os.environ.get("JWT_SECRET_FALLBACK", "change-me")


def _get_verification_key() -> str:
    algo = _get_algorithm()
    if algo == "RS256":
        key_path = os.environ.get("JWT_PUBLIC_KEY_PATH")
        if key_path and os.path.exists(key_path):
            return open(key_path).read()
        return _get_secret("JWT-PUBLIC-KEY")
    return os.environ.get("JWT_SECRET_FALLBACK", "change-me")


def create_access_token(user_id: str, tenant_id: str, email: str) -> str:
    expire = datetime.now(UTC) + timedelta(
        minutes=int(os.environ.get("JWT_ACCESS_EXPIRE_MINUTES", 60))
    )
    payload = {
        "sub": user_id,
        "tenant": tenant_id,
        "email": email,
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "access",
    }
    return jwt.encode(payload, _get_signing_key(), algorithm=_get_algorithm())


def create_refresh_token(user_id: str, tenant_id: str) -> str:
    expire = datetime.now(UTC) + timedelta(
        days=int(os.environ.get("JWT_REFRESH_EXPIRE_DAYS", 7))
    )
    payload = {
        "sub": user_id,
        "tenant": tenant_id,
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "refresh",
    }
    return jwt.encode(payload, _get_signing_key(), algorithm=_get_algorithm())


def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(
            token,
            _get_verification_key(),
            algorithms=[_get_algorithm()],
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expirado")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Token inválido: {e}")
