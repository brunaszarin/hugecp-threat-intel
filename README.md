# HugeCP — Threat Intelligence

Página de threat intelligence para analistas de rede: panorama do tráfego, origens que merecem atenção e ficha detalhada de cada origem.

## Stack

| Camada   | Tecnologia                                          |
| -------- | --------------------------------------------------- |
| Backend  | Python 3.12, FastAPI, psycopg 3                     |
| Banco    | PostgreSQL 17                                       |
| Frontend | React 19, TypeScript, Vite, MUI, TanStack Query     |
| Tooling  | uv, Ruff, mypy, pytest, Vitest, Oxlint, Prettier    |

## Pré-requisitos

- Docker e Docker Compose
- Python 3.12+ e [uv](https://docs.astral.sh/uv/)
- Node.js 22+

## Como rodar

```bash
# 1. Copie os CSVs fornecidos para a pasta data/
cp /caminho/para/flows.csv /caminho/para/indicadores.csv data/

# 2. Suba o banco e instale as dependências
make db-up
make setup

# 3. Popule o banco (idempotente: pode rodar quantas vezes quiser)
# _a definir_

# 4. Rode backend e frontend (em terminais separados)
make api   # http://localhost:8000/docs
make web   # http://localhost:5173
```

## Estrutura

```
.
├── backend/          # API FastAPI e comando de ingestão
├── frontend/         # SPA React + TypeScript
├── data/             # CSVs locais (não versionados)
├── docs/             # Registro de decisões
└── docker-compose.yml
```

## Decisões

Ver [docs/DECISIONS.md](docs/DECISIONS.md).
