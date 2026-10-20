#!/bin/sh
set -eu
# Run from the checkout root. No image pulls or DB migration before the backup.
docker compose stop worker manager angie
docker compose run --rm --no-deps manager backup
docker compose build manager
docker compose build angie
docker compose up -d
