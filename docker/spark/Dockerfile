FROM python:3.11-slim

USER root

# Install system dependencies and add Eclipse Temurin repository for Java
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    gnupg \
    procps \
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

# Install Spark
ENV SPARK_VERSION=3.5.0
ENV HADOOP_VERSION=3
ENV SPARK_HOME=/opt/spark
ENV PATH=$SPARK_HOME/bin:$SPARK_HOME/sbin:$PATH

RUN wget -q https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz \
    && tar -xzf spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz -C /opt \
    && mv /opt/spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION} ${SPARK_HOME} \
    && rm spark-${SPARK_VERSION}-bin-hadoop${HADOOP_VERSION}.tgz

# Install Python dependencies for Spark
RUN pip3 install --no-cache-dir \
    pyspark==3.5.0 \
    kafka-python==2.0.2 \
    redis==5.0.1 \
    pymongo==4.6.0 \
    transformers==4.35.0 \
    torch==2.1.0 \
    numpy==1.26.2 \
    pandas==2.1.3 \
    pyarrow==14.0.1 \
    nltk==3.8.1

# Download NLTK data
RUN python3 -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet')"

WORKDIR /app

# Copy Spark configurations
COPY spark-defaults.conf ${SPARK_HOME}/conf/spark-defaults.conf

CMD ["bash"]
