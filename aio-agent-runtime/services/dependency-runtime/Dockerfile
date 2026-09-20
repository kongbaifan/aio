ARG BASE_IMAGE=python@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
FROM ${BASE_IMAGE} AS installer
COPY check_wheels.py /opt/aio-builder/check_wheels.py
COPY manifest.json requirements.lock /opt/aio-builder/
COPY wheels/ /opt/aio-wheels/
RUN groupadd --gid 10001 runner && useradd --uid 10001 --gid 10001 --create-home runner \
    && mkdir -p /opt/aio-deps && chown 10001:10001 /opt/aio-deps
USER 10001:10001
# No source distributions, setup.py/build backends, runtime network or host pip installation.
RUN --network=none python -I -S /opt/aio-builder/check_wheels.py \
    && python -I -m pip install --no-index --no-deps --no-compile --require-hashes \
       --find-links=/opt/aio-wheels --target=/opt/aio-deps -r /opt/aio-builder/requirements.lock

FROM ${BASE_IMAGE}
RUN groupadd --gid 10001 runner && useradd --uid 10001 --gid 10001 --create-home runner \
    && mkdir -p /workspace && chown 10001:10001 /workspace
COPY --from=installer --chown=0:0 /opt/aio-deps /opt/aio-deps
COPY inventory.py smoke.py manifest.json /opt/aio-runtime/
ARG MANIFEST_DIGEST
LABEL aio.runtime.manifest_digest=$MANIFEST_DIGEST
LABEL aio.runtime.install_path=/opt/aio-deps
ENV HOME=/home/runner PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
USER 10001:10001
WORKDIR /workspace
CMD ["/usr/local/bin/python", "-I", "-S", "-u", "-c", "import time; time.sleep(86400)"]
