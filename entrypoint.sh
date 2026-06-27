#!/bin/bash
set -e
echo "⚡ NetConfig v1.0 starting..."
mkdir -p /app/logs /app/instance

if [ ! -f /app/instance/netconfig.db ]; then
    echo "[*] Initializing database..."
    python -c "
from app.main import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    db.create_all()
"
    python /app/scripts/init_db.py
fi

exec gunicorn "app.main:create_app()" \
    --bind 0.0.0.0:5000 \
    --workers ${GUNICORN_WORKERS:-1} \
    --threads ${GUNICORN_THREADS:-2} \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
