# backend/Dockerfile

# 1. Base Image - Builder Stage
FROM python:3.10-slim as builder

# 2. System Dependencies (for Psycopg2/Pandas compilation)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 3. Python Dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 4. Runtime Stage (Smaller Image)
FROM python:3.10-slim
WORKDIR /app

# Install runtime libs for Postgres + curl for healthcheck
RUN apt-get update && apt-get install -y libpq-dev curl && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy Application Code
COPY . .

# 5. Security: Create non-root user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# 6. Expose port
EXPOSE 8000

# 7. Production Command (Workers enabled)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
