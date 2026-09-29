# Fluxo de trabalho

## Branches

- `main`: versão estável, sempre pronta para entrega. Recebe merge apenas de `develop`.
- `develop`: integração do trabalho em andamento. É a branch padrão do repositório.
- `feat/*`, `fix/*`, `chore/*`, `docs/*`: criadas a partir de `develop` e integradas via pull request.

## Commits

Seguimos [Conventional Commits](https://www.conventionalcommits.org/pt-br/):

```
feat(api): adiciona endpoint de série temporal
fix(ingest): evita duplicação ao rodar a ingestão duas vezes
chore(ci): adiciona cache do uv
```

## Antes de abrir um PR

```bash
make lint
make test
```
