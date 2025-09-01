This directory contains the OpenAPI specification for the UserService.

- Source: user.yaml
- Service default port: 8101

The running FastAPI service exposes OpenAPI at /openapi.json which aligns with user.yaml for the implemented endpoints:
- POST /auth/register (201, 409)
- POST /auth/login (200, 401)
- POST /auth/refresh (200, 401) [No security]
- GET /users/me (200, 401)
- PATCH /users/me (200)
