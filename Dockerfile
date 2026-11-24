# telemetry-gateway
# à lancer sur la Pi (il faut le bus I2C)
#   docker compose build
#   I2C_GID=$(getent group i2c | cut -d: -f3) docker compose up -d
# ou juste : make docker-up

FROM python:3.11-slim

# pas de .pyc, et stdout non bufferisé sinon docker logs affiche tout en retard
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# setuptools veut le README (readme dans pyproject)
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[rpi]"

# la config en dernier pour garder le cache du pip install
COPY config ./config

# pas besoin de root, l'accès i2c passe par group_add (docker-compose)
RUN useradd --system --no-create-home gateway
USER gateway

# unhealthy si le heartbeat n'a pas bougé depuis 10 s
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import os, sys, time; sys.exit(time.time() - os.path.getmtime('/tmp/telemetry-gateway.heartbeat') > 10)"

ENTRYPOINT ["telemetry-gateway"]
CMD ["-c", "/app/config/gateway.toml"]
