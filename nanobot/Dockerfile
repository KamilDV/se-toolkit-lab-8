FROM python:3.14-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy root pyproject.toml for workspace config
COPY pyproject.toml /app/pyproject.toml

# Copy nanobot project
COPY nanobot/ /app/nanobot/

# Copy mcp for editable install
COPY mcp/ /app/mcp/

# Copy nanobot-websocket-channel for editable install
COPY nanobot-websocket-channel/ /app/nanobot-websocket-channel/

# Change to nanobot directory and install
WORKDIR /app/nanobot

# Install dependencies - sync from root to get workspace members
RUN cd /app && uv sync

# Set Python path
ENV PYTHONUNBUFFERED=1

# Run entrypoint
CMD ["python", "/app/nanobot/entrypoint.py"]
