# Data Pipelines

Companion repository for the Complex Data Insights guide **Data Pipelines: Building Reliable Workflows from Data Sources to Trusted Outputs**.

The guide begins with the material previously taught as **Databases and SQL**, then extends that foundation into ingestion, ETL/ELT, storage, orchestration, testing, monitoring, recovery, governance, and production delivery.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
export PYTHONPATH="${PYTHONPATH:-}:src"
bash scripts/bash/06-run-sql-python-example.sh
bash scripts/bash/07-run-starter-pipeline.sh
python -m pytest -q
quarto render
```
