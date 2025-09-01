# UserService

FastAPI-based User Service for the food delivery application. Implements:
- POST /auth/register
- POST /auth/login
- POST /auth/refresh
- GET /users/me
- PATCH /users/me

Auth: JWT (HS256), HTTP Bearer scheme. Passwords stored hashed with bcrypt.
Storage: SQLite by default (file users.db).

## Run

Install deps:
```
pip install -r requirements.txt
```

Run dev server:
```
uvicorn app.main:app --host 0.0.0.0 --port 8101 --reload
```

OpenAPI docs:
- Swagger UI: http://localhost:8101/docs
- JSON: http://localhost:8101/openapi.json

## Environment variables

Set via .env (do not commit secrets). Example:

```
USER_SERVICE_JWT_SECRET=replace_with_strong_secret
USER_SERVICE_JWT_ISSUER=user-service
USER_SERVICE_ACCESS_TOKEN_MIN=30
USER_SERVICE_REFRESH_TOKEN_DAYS=7
USER_SERVICE_DB_PATH=users.db
USER_SERVICE_CORS_ORIGINS=*
```

## Notes

- OpenAPI contract reference provided under openapi/user.yaml.
- The implementation aligns field names and response structures accordingly.
