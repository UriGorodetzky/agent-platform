# A minimal, self-contained image for the echo agent service.

# Base layer: a small Python image. Independent of the host's Python version.
FROM python:3.12-slim

# Where our app lives inside the container's own filesystem.
WORKDIR /app

# Install dependencies FIRST, as their own layer. This layer is cached and
# only rebuilds when requirements.txt changes — not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy the app code (changes often → later layer, cheap to rebuild).
COPY main.py .

# A fixed INTERNAL port. Thanks to network-namespace isolation this never
# clashes with the host or other containers, so it can be a stable convention.
# The host-side port is chosen later (in docker-compose.yml), not here.
EXPOSE 8000

# Bind to 0.0.0.0, NOT 127.0.0.1: inside a container, 127.0.0.1 is reachable
# only from within the container. 0.0.0.0 lets the host reach it via -p mapping.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
