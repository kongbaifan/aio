FROM python@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
ARG DEPENDENCY_DIGEST
LABEL aio.mcp.dependency_digest=$DEPENDENCY_DIGEST
WORKDIR /opt/mcp
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock \
    && groupadd --gid 10001 runner \
    && useradd --uid 10001 --gid 10001 --create-home runner \
    && mkdir -p /workspace && chown 10001:10001 /workspace
COPY example_server.py ./example_server.py
USER 10001:10001
WORKDIR /workspace
CMD ["python", "-I", "-u", "/opt/mcp/example_server.py"]
