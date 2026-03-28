import unittest

from app.core.config import Settings


class SecurityConfigTests(unittest.TestCase):
    def test_validate_runtime_security_rejects_default_database_credentials_in_production(self):
        settings = Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql+psycopg2://admin:admin@db:5432/teamhome",
            JWT_SECRET="x" * 32,
            CORS_ALLOW_ORIGINS=["https://teamhome.example"],
            ALLOW_INSECURE_DEV_AUTH=False,
            ENABLE_DEBUG_ENDPOINTS=False,
            WECHAT_APPID="appid",
            WECHAT_SECRET="secret",
        )

        issues = settings.validate_runtime_security()

        self.assertIn("DATABASE_URL must not use default admin/admin credentials in production.", issues)

    def test_validate_runtime_security_accepts_non_default_database_credentials_in_production(self):
        settings = Settings(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql+psycopg2://teamhome_user:strong-db-password@db:5432/teamhome",
            JWT_SECRET="x" * 32,
            CORS_ALLOW_ORIGINS=["https://teamhome.example"],
            ALLOW_INSECURE_DEV_AUTH=False,
            ENABLE_DEBUG_ENDPOINTS=False,
            WECHAT_APPID="appid",
            WECHAT_SECRET="secret",
        )

        issues = settings.validate_runtime_security()

        self.assertNotIn("DATABASE_URL must not use default admin/admin credentials in production.", issues)


if __name__ == "__main__":
    unittest.main()
