#!/bin/bash
set -e

# Wait for namenode to be ready
echo "Waiting for NameNode to be ready..."
while ! nc -z namenode 9000; do
    echo "NameNode not ready, waiting..."
    sleep 3
done
echo "NameNode is ready!"

# Small delay to ensure namenode is fully initialized
sleep 5

echo "Starting DataNode..."
exec ${HADOOP_HOME}/bin/hdfs datanode
