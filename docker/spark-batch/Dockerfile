FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and add Eclipse Temurin repository for Java
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    gcc \
    g++ \
    procps \
    cron \
    && wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public | gpg --dearmor -o /usr/share/keyrings/adoptium.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(. /etc/os-release && echo $VERSION_CODENAME) main" > /etc/apt/sources.list.d/adoptium.list \
    && apt-get update \
    && apt-get install -y temurin-17-jdk \
    && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/temurin-17-jdk-arm64
ENV PATH=$JAVA_HOME/bin:$PATH

# Fallback for amd64
RUN if [ ! -d "$JAVA_HOME" ]; then \
        export JAVA_HOME=/usr/lib/jvm/temurin-17-jdk-amd64; \
    fi

# Copy requirements
COPY requirements/spark-batch.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet'); nltk.download('punkt_tab')"

# Copy source code
COPY src /app/src
COPY config /app/config

# Create necessary directories
RUN mkdir -p /app/logs /app/models

# Setup cron job for hourly batch processing
COPY docker/spark-batch/batch-cron /etc/cron.d/batch-cron
RUN chmod 0644 /etc/cron.d/batch-cron && crontab /etc/cron.d/batch-cron

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYSPARK_PYTHON=python
ENV PYSPARK_DRIVER_PYTHON=python

# Copy and set up entrypoint
COPY docker/spark-batch/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
