# Build from the repository root: docker build -f db/Dockerfile .
# Pinned by digest for reproducible builds; refresh it deliberately (scripts/lock-deps.sh, then rebuild).
FROM python:3.12-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /migrate
COPY db/requirements.lock.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY db/migrate.py ./
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin migrate
USER 10001
CMD ["python", "migrate.py"]
