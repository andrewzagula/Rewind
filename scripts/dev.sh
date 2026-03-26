#!/usr/bin/env bash
set -euo pipefail

echo "Starting Rewind development environment..."

if [ ! -f .env ]; then
    echo "No .env file found. Copying from .env.example..."
    cp .env.example .env
fi

docker compose up --build "$@"
