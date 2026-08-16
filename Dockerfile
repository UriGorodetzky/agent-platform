# Image for the orchestrator (the FastAPI control plane).
# Build context is the repo root, because it needs pyproject.toml + the package.
FROM python:3.12-slim

WORKDIR /app

# Copy only what's needed to install the orchestrator, then install it.
# (services/ and tests/ are excluded via .dockerignore and not needed here.)
COPY pyproject.toml ./
COPY orchestrator/ ./orchestrator/
RUN pip install --no-cache-dir .

EXPOSE 8000

# 0.0.0.0 so the container is reachable from outside its network namespace.
CMD ["uvicorn", "orchestrator.api:app", "--host", "0.0.0.0", "--port", "8000"]
