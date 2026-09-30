# Registro de decisões

Cada decisão relevante de arquitetura ou modelagem fica registrada aqui, com contexto e alternativas consideradas.

## 001 — Estrutura do repositório

- **Decisão:** monorepo com `backend/` (Python, FastAPI) e `frontend/` (React, TypeScript, Vite).
- **Motivo:** a entrega é um único `.zip`; um repositório só simplifica CI, README e revisão.
- **Alternativas:** repositórios separados (descartado pelo formato de entrega).

## 002 — Banco de dados

- **Decisão:** PostgreSQL 17 via Docker Compose.
- **Motivo:** tipo `inet` nativo para IPs, índices compostos, `date_bin` para agrupar por tempo e `COPY` para carga rápida. Sobe com um comando na máquina de quem avalia.
- **Porta 5433 no host:** o container expõe o PostgreSQL na 5433 para não conflitar com um PostgreSQL instalado localmente na máquina de quem roda o projeto.
- **Alternativas:** DuckDB (colunar e sem servidor, ótimo para agregação; descartado para manter um banco transacional "de mercado" e facilitar a discussão sobre índices); ClickHouse (faria sentido com bilhões de linhas, é excessivo para 80 mil).

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

## 006 — API do panorama

- **Filtro de período comum:** todos os endpoints aceitam `from` (inclusivo) e `to` (exclusivo) em ISO 8601. Sem eles, vale o período coberto pelos dados. Datas sem fuso são tratadas como UTC, o fuso dos timestamps do CSV. Cada resposta devolve o período efetivamente usado.
- **Série temporal com bytes, pacotes e flows juntos:** o custo está na varredura e no agrupamento, não no payload; somar as três métricas no mesmo `GROUP BY` custa o mesmo que somar uma. Uma única resposta mantém as métricas consistentes entre si e permite trocar a métrica na tela sem nova requisição. Um parâmetro para escolher métricas só seria adicionado se surgissem métricas que a tela não usa sempre.
- **Granularidade automática:** o backend escolhe o menor intervalo "redondo" (1 s, 5 s, … 2 min, 5 min, …) que mantém a série em até ~200 pontos, e devolve `bucket_seconds` para o frontend rotular o eixo. O parâmetro `bucket` força um intervalo, limitado a 5.000 pontos por resposta.
- **Intervalos vazios viram zero:** os intervalos são gerados com `generate_series` e cruzados com `LEFT JOIN`; sem isso, o gráfico ligaria pontos distantes com uma reta e esconderia períodos sem tráfego.
- **Sem conversão para taxa (bps/pps):** os bytes são de amostras e a taxa de amostragem é desconhecida, então qualquer taxa seria um número inventado. A tela mostra o total amostrado por intervalo.
- **Top portas sem ICMP:** ICMP não tem portas e vem com `dst_port = 0`; incluí-lo faria a "porta 0" aparecer como um serviço procurado. A ordenação padrão é por quantidade de flows ("mais procuradas"), com opção de ordenar por bytes.
- **Pool de conexões com timeout de 5 s:** se o banco estiver fora do ar, a API responde erro rapidamente em vez de segurar a requisição por 30 s.

## 007 — Origens: lista (B) e ficha (C)

- **Critérios calculados dentro do período filtrado**, inclusive o "top 20 em bytes": ao recortar a janela, o ranking é refeito só com o tráfego dela. Uma origem sem tráfego na janela não entra na lista.
- **Limiares estritos:** "mais de 20" e "mais de 50" são `>`; os testes cobrem exatamente 20/21 destinos e 50/51 portas.
- **Portas por destino:** o critério usa o maior número de portas distintas que a origem procurou num mesmo IP protegido, não a soma entre destinos. ICMP fica fora de todas as contagens de portas.
- **Empate no top 20:** `rank()` inclui todos os empatados na 20ª posição, em vez de escolher um arbitrariamente. Nos dados fornecidos não há empate.
- **Nomes neutros para os critérios** (`indicator`, `many_destinations`, `many_ports`, `top_bytes`): descrevem o que foi observado, sem afirmar que houve varredura ou ataque, já que o enunciado pede para não criar detecção.
- **Uma CTE compartilhada** calcula as estatísticas e os critérios de todas as origens; a lista, as contagens por critério e a ficha partem dela. O top 20 depende do conjunto inteiro, então a ficha de um IP também precisa passar por ela.
- **Filtro, ordenação e paginação no banco.** Ordenação só por colunas de uma lista fechada (validada pela API), nunca por texto livre. As contagens por critério (`criteria_counts`) ignoram o filtro aplicado, para a tela mostrar quantas origens existem em cada critério.
- **Ficha em endpoints separados** (identificação, atividade, destinos, portas, flows): cada bloco da tela carrega de forma independente e só os flows precisam de paginação pesada.
- **A ficha aceita qualquer origem presente nos dados**, mesmo sem critério acionado, porque o analista pode querer investigar um IP fora da lista. IP inexistente devolve 404; IP inválido, 422.
- **Portas da ficha agrupadas por porta e protocolo:** 53/UDP e 53/TCP são serviços diferentes.
