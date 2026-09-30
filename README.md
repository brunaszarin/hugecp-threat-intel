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
make ingest

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

## Ingestão

`make ingest` lê `data/flows.csv` e `data/indicadores.csv`, cria o schema se ele
ainda não existir e recarrega todas as tabelas dentro de **uma única transação**.
Rodar duas vezes produz exatamente o mesmo estado, sem duplicar dados. Se algo
falhar no meio, nada é gravado e os dados anteriores continuam intactos.

Para usar arquivos em outro lugar:

```bash
cd backend
uv run python -m app.ingest --flows /caminho/flows.csv --indicators /caminho/indicadores.csv
```

## API

Com a API rodando (`make api`), a documentação interativa fica em http://localhost:8000/docs.
Todos os endpoints aceitam `from` e `to` (ISO 8601, UTC); sem eles, vale o período inteiro dos dados.

| Endpoint | O que devolve |
| --- | --- |
| `GET /api/overview/summary` | Totais de bytes, pacotes, flows, origens e destinos, e o tráfego vindo de indicadores |
| `GET /api/overview/timeseries` | Bytes, pacotes e flows por intervalo (`bucket` em segundos; automático se omitido) |
| `GET /api/overview/protocols` | Distribuição por protocolo |
| `GET /api/overview/top-ports` | Portas de destino mais procuradas (`limit`, `order_by=flows\|bytes`) |
| `GET /api/origins` | Origens que acionaram algum critério (`criteria`, `sort`, `order`, `page`, `page_size`) |
| `GET /api/origins/{ip}` | Ficha: identificação, indicador, estatísticas e critérios no período |
| `GET /api/origins/{ip}/timeseries` | Atividade da origem ao longo do tempo |
| `GET /api/origins/{ip}/destinations` | IPs protegidos atingidos e tráfego para cada um (paginado) |
| `GET /api/origins/{ip}/ports` | Portas procuradas (porta + protocolo) e em quantos flows (paginado) |
| `GET /api/origins/{ip}/flows` | Flows da origem (`sort=ts\|bytes\|packets`, paginado) |

Critérios da lista de origens: `indicator` (está na lista de indicadores), `many_destinations`
(mais de 20 IPs protegidos distintos), `many_ports` (mais de 50 portas distintas no mesmo IP
protegido) e `top_bytes` (entre as 20 que mais enviaram bytes).

## Testes

```bash
make db-up   # os testes de integração usam o PostgreSQL
make test
```

Cada teste de integração roda num schema temporário, criado e apagado
automaticamente, então os testes nunca apagam os dados carregados pelo `make ingest`.

## Decisões

Ver [docs/DECISIONS.md](docs/DECISIONS.md).
