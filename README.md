# Databases and SQL (Free Track)

This repository is part of **Complex Data Insights (CDI)**.

It teaches databases and SQL as the backbone behind analytical workflows.

## What you will learn

- how relational databases structure data
- how to write SQL to answer real questions
- how joins work and where they break
- how to think about normalization and integrity
- how to connect SQL to Python for analysis

## Quick start

1. Create the environment

```bash
bash scripts/setup-env.sh
```

2. Build the sample SQLite database

```bash
python scripts/init-sqlite-db.py
```

3. Render the book

```bash
bash scripts/build-all.sh
```

## Repository conventions

- `index.qmd` is cover-only
- Gateway text and `:::cdi-message` start in `01-preface-and-setup.qmd`
- Output is rendered to `docs/` for GitHub Pages
- Filenames use hyphens

## Data

This free track includes a small retail dataset stored as:

- SQL schema and seed scripts in `data/sql/`
- a generated SQLite database file: `data/cdi-retail.sqlite`

## License

TBD

