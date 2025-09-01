# Environment configuration

Copy .env.example to .env and set values:
- USER_SERVICE_JWT_SECRET: Required
- USER_SERVICE_JWT_ISSUER: Default user-service
- USER_SERVICE_ACCESS_TOKEN_MIN: Default 30
- USER_SERVICE_REFRESH_TOKEN_DAYS: Default 7
- USER_SERVICE_DB_PATH: SQLite path, default users.db
- USER_SERVICE_CORS_ORIGINS: Comma-separated CORS origins, default *
- HTTP_TIMEOUT_SECONDS: Default 10
- INTERNAL_SERVICE_TOKEN: Optional internal auth header
