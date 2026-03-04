# conftest.py — configuração global dos testes
import os
import sys

# Garante que o diretório backend está no path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Variáveis de ambiente padrão para testes (sobrescritas por CI quando necessário)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_SECRET_FALLBACK", "test-only-secret")
os.environ.setdefault("JWT_ACCESS_EXPIRE_MINUTES", "60")
os.environ.setdefault("JWT_REFRESH_EXPIRE_DAYS", "7")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fake")
os.environ.setdefault("MP_ACCESS_TOKEN", "APP_USR_fake")
os.environ.setdefault("MP_WEBHOOK_SECRET", "mp_fake_secret")
