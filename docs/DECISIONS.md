# Registro de decisões

Cada decisão relevante de arquitetura ou modelagem fica registrada aqui, com contexto e alternativas consideradas.

## 001 — Estrutura do repositório

- **Decisão:** monorepo com `backend/` (Python, FastAPI) e `frontend/` (React, TypeScript, Vite).
- **Motivo:** a entrega é um único `.zip`; um repositório só simplifica CI, README e revisão.
- **Alternativas:** repositórios separados (descartado pelo formato de entrega).

## 002 — Banco de dados

- **Decisão:** PostgreSQL 17 via Docker Compose.
- **Motivo:** _a preencher após a exploração dos dados._
