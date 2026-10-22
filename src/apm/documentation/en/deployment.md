# Installation and Compose

## Choose a deployment

- `compose.yaml`: Linux with a dedicated Angie using host networking; requires Docker Engine, Compose v2, free TCP 80/81/443/8181/18081 and UDP 443 for HTTP/3.
- `compose.yaml` + `compose.local.yaml`: local Docker Desktop with a separate volume; panel https://localhost:81, HTTP localhost:8088, TLS localhost:8443. Use host.docker.internal for applications on macOS.
- `compose.existing.yaml`: standalone profile for an already installed Angie. It starts no second Angie; a host-local Unix agent is required.
- `compose.extended.yaml`: extended build with extra modules; inspect capabilities for actual compatible support.
- `compose.analytics.yaml`: optional GoAccess; runtime must enable access_logs and analytics.

## First managed startup

```sh
cp .env.example .env
# Set APM_PUBLIC_URL and other settings.
docker compose build manager
docker compose build angie
docker compose up -d
docker compose exec manager apm setup-token
```

Open the HTTPS panel, enter the locally obtained one-time token and create an administrator with a password of at least 12 characters. The bootstrap certificate is self-signed. Prepare the backend, optional DNS profile/certificate, then the proxy host. Check Operations. For local deployments add `-f compose.yaml -f compose.local.yaml` to every Compose command.

## Existing Angie

Prepare .env.existing from .env.existing.example. Manager, worker and the host agent must share the same absolute APM_DATA_DIR and compatible binary/root configuration/prefix paths. Install a local agent permitted to run angie -t and reload; the Angie HTTP API alone is insufficient. The agent must use Angie’s network environment.

Add includes to the appropriate existing root configuration contexts:

```nginx
http {
    include /srv/apm/current/http.conf;
}
stream {
    include /srv/apm/current/stream.conf;
}
```

APM preserves the root configuration and existing virtual hosts. Configure a separate HTTPS panel virtual host proxying manager at 127.0.0.1:8181; keep the status API and Unix socket local. The existing Angie owner manages process settings and global default listeners.

```sh
docker compose --env-file .env.existing -f compose.existing.yaml up -d
docker compose --env-file .env.existing -f compose.existing.yaml exec manager apm setup-token
```

## Services, paths and updates

manager serves UI/API, worker runs the queue and monitoring, agent validates/applies configuration, docker-gateway provides permitted read requests. Shared data contains SQLite, master.key, certificates, acme, revisions, current and logs. Back up the whole data directory with its master key, not just the database.

Before an update create an encrypted backup, stop services, update sources/images, rebuild manager and Angie, and start them. Check health, generation and routes. Do not use down --volumes if data must be retained. Separately validate the production CPU architecture, directory permissions and required modules.

[All environment settings](environment.md) · [CLI](cli.md) · [Backups](imports.md)
