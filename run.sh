#!/usr/bin/env bash
# Convenience wrapper. The base sandbox image is built automatically on first use.
set -euo pipefail
cd "$(dirname "$0")"
exec python -m agent.main "$@"
