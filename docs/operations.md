# Operations

## Start

Copy `.env.example` to `.env` only when overriding defaults, then run:

```text
docker compose up --build -d
```

For production overrides:

```text
docker compose -f compose.yaml -f compose.prod.yaml up --build -d
```

The console is on port 8000, liveness is `/health/live`, readiness is `/health/ready`, and API
documentation is `/docs`. View service logs with `docker compose logs -f api worker` and stop with
`docker compose down`. Named PostgreSQL and Redis volumes survive ordinary shutdown. Back up the
PostgreSQL volume before upgrades; migrations run automatically during startup.

