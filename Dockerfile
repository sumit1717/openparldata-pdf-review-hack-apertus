# Source-only candidate: this Docker build and image have NOT been executed.
# Preserve the existing project's immutable CPython 3.12 Linux amd64 base.
FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e
WORKDIR /app/src
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY track_2a/requirements/base.lock /app/requirements/base.lock
COPY track_2a/src/track_2a_converter/requirements.lock /app/requirements/converter.lock
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: --no-deps \
    -r /app/requirements/base.lock -r /app/requirements/converter.lock && python -m pip check
COPY track_2a/src/ /app/src/
COPY track_2a/tests/ /app/tests/
USER 65532:65532
ENTRYPOINT ["python", "/app/src/cli.py"]
CMD ["demo", "--out", "/output/demo"]
