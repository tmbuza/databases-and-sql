#!/usr/bin/env bash
set -euo pipefail

echo "Checking Python..."
python --version

echo "Checking required Python packages..."
python -c "import pandas, sqlalchemy; print('Python dependencies: OK')"

echo "Checking Quarto..."
quarto --version

echo "Environment check: PASSED"