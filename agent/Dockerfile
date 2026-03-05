FROM python:3.11-slim as builder
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y gcc python3-dev build-essential
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.11-slim
RUN apt-get update && apt-get install -y curl ca-certificates bash && rm -rf /var/lib/apt/lists/*
# Install helm (needed for Karpenter install/uninstall actions)
RUN curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
# Install kubectl (EXEC-02: needed for kubectl drain --dry-run validation and future direct operations)
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/kubectl
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN useradd -u 1000 -m -s /bin/bash agent
WORKDIR /app
COPY --chown=agent:agent *.py /app/
USER agent
EXPOSE 8080
HEALTHCHECK CMD curl -f http://localhost:8080/healthz || exit 1
ENTRYPOINT ["python", "main.py"]
