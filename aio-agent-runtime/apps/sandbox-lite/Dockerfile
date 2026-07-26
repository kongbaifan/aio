FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 sandbox \
    && mkdir -p /workspace \
    && chown -R sandbox:sandbox /app /workspace

USER sandbox
ENV SANDBOX_WORKSPACE_DIR=/workspace
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8081
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8081"]

