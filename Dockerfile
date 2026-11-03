FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --output-file /tmp/requirements.txt \
    && uv pip install --system --no-cache --require-hashes -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY README.md LICENSE CHANGELOG.md ./
COPY openhal ./openhal
COPY examples/plant-waterer ./examples/plant-waterer
COPY examples/print-babysitter ./examples/print-babysitter
COPY library ./library
RUN uv pip install --system --no-cache --no-deps --compile-bytecode .

COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/openhal-container
RUN useradd --create-home --uid 10001 openhal
USER openhal
WORKDIR /home/openhal
ENV OPENHAL_HOME=/home/openhal/.openhal PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.title="OpenHAL" \
      org.opencontainers.image.description="The OpenHAL hub and MCP server, with a simulated plant waterer." \
      org.opencontainers.image.source="https://github.com/sohan-bhat/OpenHAL" \
      org.opencontainers.image.licenses="Apache-2.0"

ENTRYPOINT ["openhal-container"]
CMD ["mcp"]
