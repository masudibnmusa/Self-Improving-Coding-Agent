#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! docker image inspect coding-agent-base >/dev/null 2>&1; then
  docker build -f docker/Dockerfile.base -t coding-agent-base .
fi

python -m agent.main "$@"