FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py .
COPY mcp_server.py .

# config/ 由 compose 挂载进来；这里先建空目录，让 paths.project_root() 能把根锁定在 /app
# 而不是继续向上找到 /（compose 里另有 HARNESS_PROJECT_ROOT 显式指定）。
RUN useradd --create-home --uid 10002 harness \
    && mkdir -p /app/var /app/config /app/skills \
    && chown -R harness:harness /app

USER harness
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

EXPOSE 8080
CMD ["python", "run.py"]

