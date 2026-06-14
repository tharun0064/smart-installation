FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for diagnostics
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    netcat-openbsd \
    net-tools \
    iproute2 \
    traceroute \
    dnsutils \
    lsof \
    procps \
    iptables \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml requirements.txt ./
COPY nr_diagnose/ ./nr_diagnose/
COPY agents/ ./agents/
COPY .env* ./

# Install the package
RUN pip install --no-cache-dir -e .

ENTRYPOINT ["nr-diagnose"]
CMD ["run", "--agent", "otel-oracledbreceiver"]
