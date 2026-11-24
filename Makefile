PY ?= python3
export PYTHONPATH := src

.PHONY: install lint run ground docker-build docker-up docker-logs clean

# sur la Pi (smbus2 + ruff)
install:
	$(PY) -m pip install -e ".[rpi,dev]"

lint:
	ruff check src

# sans docker, pratique pour débugger
run:
	$(PY) -m telemetry_gateway -c config/gateway.toml

# station sol, à lancer sur le PC
ground:
	$(PY) -m telemetry_gateway.ground.receiver --port 5005

docker-build:
	docker compose build

docker-up:
	I2C_GID=$$(getent group i2c | cut -d: -f3) docker compose up -d

docker-logs:
	docker compose logs -f gateway

clean:
	rm -rf build dist *.egg-info .ruff_cache
	find . -name __pycache__ -type d -exec rm -rf {} +
