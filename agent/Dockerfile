# Always target linux/amd64 — EKS nodes are x86_64.
# On Apple Silicon, docker buildx uses QEMU emulation automatically.
FROM --platform=linux/amd64 python:3.11-slim AS builder
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN apt-get update && apt-get install -y gcc python3-dev build-essential
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

FROM --platform=linux/amd64 python:3.11-slim
# For helm, the install script auto-detects arch at runtime.
# For kubectl, we derive the arch explicitly from TARGETARCH.
ARG TARGETARCH=amd64
RUN apt-get update && apt-get install -y curl ca-certificates bash && rm -rf /var/lib/apt/lists/*
# Install helm (needed for Karpenter install/uninstall actions) — script auto-detects arch
RUN curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
# Install kubectl — use $TARGETARCH so multi-platform builds get the right binary
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/${TARGETARCH}/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/kubectl
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN useradd -u 1000 -m -s /bin/bash agent
WORKDIR /app
COPY --chown=agent:agent *.py /app/
ARG AGENT_VERSION=1.1.2
ENV AGENT_VERSION=${AGENT_VERSION}
LABEL version="${AGENT_VERSION}"
USER agent
EXPOSE 8080
HEALTHCHECK CMD curl -f http://localhost:8080/healthz || exit 1
ENTRYPOINT ["python", "main.py"]
