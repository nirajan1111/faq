#!/bin/bash
set -e

# Format namenode if not already formatted
if [ ! -d "/hadoop/dfs/name/current" ]; then
    echo "Formatting NameNode..."
    ${HADOOP_HOME}/bin/hdfs namenode -format -force -nonInteractive
fi

echo "Starting NameNode..."
exec ${HADOOP_HOME}/bin/hdfs namenode
