FROM python@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
# No server, manager credential, host mount or user-writable runtime code is included.
RUN groupadd --gid 10001 runner && useradd --uid 10001 --gid 10001 --create-home runner \
    && mkdir -p /workspace && chown runner:runner /workspace
USER 10001:10001
WORKDIR /workspace
ENV HOME=/home/runner PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8
CMD ["python", "-I", "-u", "-c", "import time; time.sleep(86400)"]
