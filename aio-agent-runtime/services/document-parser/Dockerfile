FROM python@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/document-parser
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir . \
    && groupadd --gid 10001 runner \
    && useradd --uid 10001 --gid 10001 --create-home runner \
    && mkdir -p /workspace \
    && chown 10001:10001 /workspace
WORKDIR /workspace
USER 10001:10001
