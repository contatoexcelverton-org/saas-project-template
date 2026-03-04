"""
Testes unitários — Autenticação
Todos os testes usam mocks — sem I/O externo, sem banco, sem Azure.
"""
import os
import time

import pytest

os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_SECRET_FALLBACK", "test-secret-unit")
os.environ.setdefault("JWT_ACCESS_EXPIRE_MINUTES", "60")
os.environ.setdefault("JWT_REFRESH_EXPIRE_DAYS", "7")

from services.auth import (
    create_access_token,
    create_refresh_token,
    generate_otp,
    hash_otp,
    verify_token,
)


class TestOtp:
    def test_otp_length_default(self):
        otp = generate_otp()
        assert len(otp) == 6

    def test_otp_length_custom(self):
        assert len(generate_otp(8)) == 8

    def test_otp_only_digits(self):
        otp = generate_otp()
        assert otp.isdigit()

    def test_otp_unique(self):
        otps = {generate_otp() for _ in range(100)}
        # Com 6 dígitos e 100 amostras, probabilidade de colisão é muito baixa
        assert len(otps) > 90

    def test_hash_otp_deterministic(self):
        otp = "123456"
        assert hash_otp(otp) == hash_otp(otp)

    def test_hash_otp_different_values(self):
        assert hash_otp("123456") != hash_otp("654321")


class TestAccessToken:
    def test_create_and_verify(self):
        token = create_access_token("user-1", "tenant-1", "user@test.com")
        payload = verify_token(token)
        assert payload["sub"] == "user-1"
        assert payload["tenant"] == "tenant-1"
        assert payload["email"] == "user@test.com"
        assert payload["type"] == "access"

    def test_expired_token_raises(self, monkeypatch):
        monkeypatch.setenv("JWT_ACCESS_EXPIRE_MINUTES", "0")
        import importlib
        import services.auth as auth_module
        importlib.reload(auth_module)
        # Cria com expiração imediata
        os.environ["JWT_ACCESS_EXPIRE_MINUTES"] = "-1"
        token = auth_module.create_access_token("u", "t", "e@e.com")
        with pytest.raises(ValueError, match="expirado"):
            auth_module.verify_token(token)

    def test_invalid_token_raises(self):
        with pytest.raises(ValueError, match="inválido"):
            verify_token("token.invalido.aqui")

    def test_tampered_token_raises(self):
        token = create_access_token("user-1", "tenant-1", "user@test.com")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(ValueError):
            verify_token(tampered)


class TestRefreshToken:
    def test_create_and_verify(self):
        token = create_refresh_token("user-1", "tenant-1")
        payload = verify_token(token)
        assert payload["sub"] == "user-1"
        assert payload["type"] == "refresh"

    def test_refresh_token_has_longer_expiry(self):
        access = create_access_token("u", "t", "e@e.com")
        refresh = create_refresh_token("u", "t")
        access_exp = verify_token(access)["exp"]
        refresh_exp = verify_token(refresh)["exp"]
        assert refresh_exp > access_exp
