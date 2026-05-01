#!/bin/sh
set -e

DOCKER_BUILDKIT=1 docker build -f Dockerfile.ci -t hello-world:ci .

docker run --rm hello-world:ci sh -c "
  set -e
  echo '==> ruff check'
  uv run ruff check hello.py test_hello.py

  echo '==> ruff format --check'
  uv run ruff format --check hello.py test_hello.py

  echo '==> mypy'
  uv run mypy hello.py test_hello.py

  echo '==> pytest'
  uv run pytest

  echo ''
  echo 'All checks passed.'
"
