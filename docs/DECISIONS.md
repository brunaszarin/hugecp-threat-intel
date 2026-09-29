# Registro de decisões

Cada decisão relevante de arquitetura ou modelagem fica registrada aqui, com contexto e alternativas consideradas.

## 001 — Estrutura do repositório

- **Decisão:** monorepo com `backend/` (Python, FastAPI) e `frontend/` (React, TypeScript, Vite).
- **Motivo:** a entrega é um único `.zip`; um repositório só simplifica CI, README e revisão.
- **Alternativas:** repositórios separados (descartado pelo formato de entrega).

## 002 — Banco de dados

- **Decisão:** PostgreSQL 17 via Docker Compose.
- **Motivo:** tipo `inet` nativo para IPs, índices compostos, `date_bin` para agrupar por tempo e `COPY` para carga rápida. Sobe com um comando na máquina de quem avalia.
- **Alternativas:** DuckDB (colunar e sem servidor, ótimo para agregação; descartado para manter um banco transacional "de mercado" e facilitar a discussão sobre índices); ClickHouse (faria sentido com bilhões de linhas, é excessivo para 80 mil).
- **Porta 5433 no host:** o container expõe o PostgreSQL na 5433 para não conflitar com um PostgreSQL instalado localmente na máquina de quem roda o projeto.

## 003 — Modelo de dados

- **Decisão:** três tabelas: `origins` (IP, ASN, país), `indicators` (IP e dados do feed) e `flows` (amostras, com chave estrangeira para `origins`).
- **Motivo:** na exploração, cada IP de origem aparece sempre com o mesmo ASN e país, então esses atributos pertencem ao IP e não à amostra. Cada indicador aparece uma única vez, o que permite `ip` como chave primária e um join 1 para 1.
- **Sem FK de `flows` para `indicators`:** a maioria das origens não é indicador; o cruzamento é um `LEFT JOIN` na consulta.
- **Chave sintética em `flows`:** não existe chave natural, já que duas amostras idênticas seriam legítimas.
- **Protocolo como `text` com `CHECK`**, em vez de `ENUM`: mais simples de evoluir e igualmente validado.
- **Índices:** `flows(ts)` para o panorama, `flows(src_ip, ts)` para a lista e a ficha de origens, `flows(dst_ip)` para destinos.
- **Sem pré-agregação:** com 80 mil linhas os critérios são calculados na hora, respeitando o filtro de período. Com volume muito maior, a evolução natural seriam materialized views ou um banco colunar.

## 004 — Ingestão idempotente

- **Decisão:** a ingestão roda numa única transação: aplica o schema (`IF NOT EXISTS`), carrega os CSVs em tabelas temporárias via `COPY`, faz `TRUNCATE` e reinsere tudo.
- **Motivo:** idempotência por construção, sem depender de chave natural (que não existe em `flows`). Quem consulta durante a carga continua vendo os dados antigos até o `COMMIT`, e uma falha no meio não deixa o banco pela metade.
- **Validação:** cabeçalhos são conferidos antes da carga; tipos e faixas são validados pelo próprio Postgres (`inet`, `CHECK`). Se um IP vier com ASN ou país diferentes, a chave primária de `origins` falha de propósito, em vez de escolher um valor arbitrário.
- **Alternativas:** `INSERT ... ON CONFLICT` com hash da linha (descartado: amostras idênticas legítimas colidiriam); carga incremental (desnecessária para um arquivo fechado).

## 005 — Critério "está na lista de indicadores"

- **Decisão:** uma origem aciona o critério se o IP estiver em `indicators`, independentemente de `first_seen` e `last_seen`.
- **Motivo:** é a leitura literal do enunciado. Na exploração, 33 dos 34 indicadores presentes no tráfego têm `last_seen` anterior ao início do período; exigir que o flow caísse na janela do feed praticamente eliminaria o critério.
- **Consequência na interface:** o `last_seen` do indicador aparece na lista e na ficha, para o analista avaliar se a informação está desatualizada.
