-- Schema do HugeCP. Idempotente: pode ser aplicado quantas vezes for preciso.

-- Uma linha por IP de origem. ASN e país são atributos do IP (nos dados,
-- cada IP tem sempre o mesmo ASN e país), então não se repetem em cada flow.
CREATE TABLE IF NOT EXISTS origins (
    ip      inet     PRIMARY KEY,
    asn     integer  NOT NULL,
    country char(2)  NOT NULL
);

-- Uma linha por indicador. Não há FK de flows para cá: a maioria das origens
-- não é indicador, e o cruzamento é feito com LEFT JOIN na consulta.
CREATE TABLE IF NOT EXISTS indicators (
    ip         inet        PRIMARY KEY,
    category   text        NOT NULL CHECK (category IN ('scan', 'botnet', 'c2', 'tor_exit')),
    source     text        NOT NULL,
    confidence smallint    NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    first_seen timestamptz NOT NULL,
    last_seen  timestamptz NOT NULL
);

-- Uma linha por amostra. Não existe chave natural: duas amostras idênticas
-- seriam legítimas, por isso a chave é sintética.
CREATE TABLE IF NOT EXISTS flows (
    id       bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts       timestamptz NOT NULL,
    src_ip   inet        NOT NULL REFERENCES origins (ip),
    src_port integer     NOT NULL CHECK (src_port BETWEEN 0 AND 65535),
    dst_ip   inet        NOT NULL,
    dst_port integer     NOT NULL CHECK (dst_port BETWEEN 0 AND 65535),
    protocol text        NOT NULL CHECK (protocol IN ('TCP', 'UDP', 'ICMP')),
    bytes    bigint      NOT NULL CHECK (bytes >= 0),
    packets  bigint      NOT NULL CHECK (packets >= 0)
);

-- Panorama e recorte por período.
CREATE INDEX IF NOT EXISTS flows_ts_idx ON flows (ts);
-- Lista de origens e ficha de uma origem (filtra por IP e depois por tempo).
CREATE INDEX IF NOT EXISTS flows_src_ip_ts_idx ON flows (src_ip, ts);
-- Destinos atingidos e contagem de portas por par origem/destino.
CREATE INDEX IF NOT EXISTS flows_dst_ip_idx ON flows (dst_ip);
