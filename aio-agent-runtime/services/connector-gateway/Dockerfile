FROM python@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/connector-gateway
COPY pyproject.toml ./
COPY src ./src
RUN python -m pip install --no-cache-dir . \
    && groupadd --gid 10002 connector \
    && useradd --uid 10002 --gid 10002 --create-home connector \
    && mkdir -p /var/lib/aio-connector \
    && chown 10002:10002 /var/lib/aio-connector
USER 10002:10002
CMD ["aio-connector-gateway"]
