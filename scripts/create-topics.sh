#!/bin/bash

# Create Kafka topics
# Run this script after Kafka is up

set -e

KAFKA_CONTAINER="kafka"
TOPICS=("raw_social_data" "processed_data" "faq_requests")

echo "🔧 Creating Kafka topics..."

for TOPIC in "${TOPICS[@]}"; do
    echo "Creating topic: $TOPIC"
    docker exec $KAFKA_CONTAINER kafka-topics --create \
        --bootstrap-server localhost:9092 \
        --replication-factor 1 \
        --partitions 3 \
        --topic $TOPIC \
        --if-not-exists
done

echo ""
echo "📋 Listing topics:"
docker exec $KAFKA_CONTAINER kafka-topics --list --bootstrap-server localhost:9092

echo ""
echo "✅ Kafka topics created!"
