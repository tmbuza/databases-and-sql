# Databases and SQL
## Building the Data Backbone for Analytical Workflows

This repository is part of **Complex Data Insights (CDI)**.

Databases and SQL form the structural foundation of modern analytical workflows.  
Before modeling, visualization, or machine learning, data must be structured correctly.

This free track teaches:

- Relational thinking
- SQL query fundamentals
- Aggregation and grouping discipline
- Join integrity and cardinality awareness
- Normalization and schema design principles
- SQL-to-Python integration for analysis

The emphasis is not only syntax.

It is structural clarity.

---

## Learning Philosophy

Structure → Query → Interpretation

When structure is correct, queries are predictable.  
When structure is weak, analysis becomes fragile.

This guide builds the backbone that supports every other CDI domain.

---

## Quick Start

Create the Python environment:

```bash
bash scripts/setup-env.sh
```

Initialize the SQLite database:

```bash
python scripts/init-sqlite-db.py
```

Render the book:

```bash
bash scripts/build-all.sh
```

---

## Repository Conventions

- `index.qmd` is cover-only
- Lessons use header-based structure (no YAML titles)
- No navigation callouts inside chapters
- Output renders to `docs/` for GitHub Pages
- Filenames use hyphen naming

---

## Versioning

This free track follows CDI semantic versioning:

- v0.x → structural drafts
- v1.0 → first fully coherent release
- v1.x → refinements and improvements
- v2.0 → major structural or scope changes

Current status: **Pre–v1.0 (Structural Complete)**

---

## Part of the CDI Ecosystem

This pillar connects directly to:

- Data Science
- Visualization
- Machine Learning
- Applied Bioinformatics

Every advanced workflow depends on reliable structure.

This repository ensures that foundation.
