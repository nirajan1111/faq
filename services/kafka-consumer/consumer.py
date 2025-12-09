"""
Kafka Consumer Service - Consumes raw social data and stores to HDFS
Uses pure Python libraries for ARM compatibility
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict
import requests
import signal
import sys
import time
from kafka import KafkaConsumer
from kafka.errors import KafkaError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class HDFSWebClient:
    """HDFS client using WebHDFS REST API - ARM compatible"""

    def __init__(self, namenode_url: str, user: str = "root"):
        self.namenode_url = namenode_url.rstrip("/")
        self.user = user
        self.webhdfs_base = f"{self.namenode_url}/webhdfs/v1"
        self._wait_for_hdfs()
        self._ensure_directories()

    def _wait_for_hdfs(self, max_retries: int = 30, delay: int = 5):
        """Wait for HDFS to be ready"""
        for i in range(max_retries):
            try:
                response = requests.get(
                    f"{self.webhdfs_base}/?op=LISTSTATUS&user.name={self.user}",
                    timeout=10,
                )
                if response.status_code == 200:
                    logger.info("HDFS is ready")
                    return
            except Exception as e:
                logger.warning(f"Waiting for HDFS... attempt {i + 1}/{max_retries}")
            time.sleep(delay)
        raise Exception("HDFS not available after maximum retries")

    def _ensure_directories(self):
        """Create necessary HDFS directories"""
        directories = [
            "/data/raw/reddit",
            "/data/raw/twitter",
            "/data/processed",
            "/data/faqs",
        ]
        for directory in directories:
            self.makedirs(directory)

    def makedirs(self, path: str) -> bool:
        """Create directory in HDFS"""
        try:
            url = f"{self.webhdfs_base}{path}?op=MKDIRS&user.name={self.user}"
            response = requests.put(url, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get("boolean", False):
                    logger.debug(f"Created directory: {path}")
                return True
            return False
        except Exception as e:
            logger.debug(f"Directory may already exist: {path} - {e}")
            return False

    def write_file(self, path: str, content: str) -> bool:
        """Write content to a file in HDFS"""
        try:
            # Step 1: Create file (get redirect URL)
            create_url = f"{self.webhdfs_base}{path}?op=CREATE&user.name={self.user}&overwrite=true"
            response = requests.put(create_url, allow_redirects=False, timeout=30)

            if response.status_code == 307:
                # Step 2: Follow redirect and write data
                redirect_url = response.headers["Location"]
                write_response = requests.put(
                    redirect_url,
                    data=content.encode("utf-8"),
                    headers={"Content-Type": "application/octet-stream"},
                    timeout=60,
                )
                if write_response.status_code == 201:
                    logger.debug(f"Successfully wrote file: {path}")
                    return True
                else:
                    logger.error(f"Failed to write file: {write_response.status_code}")
                    return False
            else:
                logger.error(f"Failed to create file: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error writing to HDFS: {e}")
            return False

    def store_batch(
        self, data_list: List[Dict], source: str, product: str
    ) -> Optional[str]:
        """Store batch of data to HDFS as a single JSON file"""
        product_clean = product.replace(" ", "_").lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Ensure directory exists
        dir_path = f"/data/raw/{source}/{product_clean}"
        self.makedirs(dir_path)

        # Write file
        filename = f"{product_clean}_batch_{timestamp}.json"
        filepath = f"{dir_path}/{filename}"

        content = json.dumps(data_list, indent=2, default=str)

        if self.write_file(filepath, content):
            logger.info(f"Stored batch of {len(data_list)} items to HDFS: {filepath}")
            return filepath
        else:
            logger.error(f"Failed to store batch to HDFS")
            return None


class KafkaDataConsumer:
    """Kafka consumer for raw social media data using pure Python kafka-python"""

    def __init__(self, config: dict):
        self.config = config
        self.running = True
        self.batch_size = 50
        self.batch_timeout = 30  # seconds
        self.message_batch = []
        self.last_flush_time = datetime.now()

        # Initialize HDFS client
        hdfs_url = config.get(
            "hdfs_url",
            f"http://{config['hdfs_namenode_host']}:{config['hdfs_namenode_port']}",
        )
        self.hdfs = HDFSWebClient(hdfs_url)

        # Initialize Kafka consumer with retry
        self.consumer = self._create_consumer_with_retry()

    def _create_consumer_with_retry(self, max_retries: int = 30, delay: int = 5):
        """Create Kafka consumer with retry logic"""
        for i in range(max_retries):
            try:
                consumer = KafkaConsumer(
                    self.config["topic"],
                    bootstrap_servers=self.config["kafka_bootstrap"],
                    group_id=self.config["consumer_group"],
                    auto_offset_reset="earliest",
                    enable_auto_commit=True,
                    auto_commit_interval_ms=5000,
                    value_deserializer=lambda x: json.loads(x.decode("utf-8")),
                    consumer_timeout_ms=1000,
                    session_timeout_ms=30000,
                    max_poll_interval_ms=300000,
                )
                logger.info("Successfully connected to Kafka")
                return consumer
            except Exception as e:
                logger.warning(
                    f"Waiting for Kafka... attempt {i + 1}/{max_retries}: {e}"
                )
                time.sleep(delay)
        raise Exception("Could not connect to Kafka after maximum retries")

    def _flush_batch(self):
        """Flush accumulated messages to HDFS"""
        if not self.message_batch:
            return

        # Group by source and product
        groups = {}
        for msg in self.message_batch:
            key = (msg.get("source", "unknown"), msg.get("product", "unknown"))
            if key not in groups:
                groups[key] = []
            groups[key].append(msg)

        # Store each group
        for (source, product), data_list in groups.items():
            self.hdfs.store_batch(data_list, source, product)

        self.message_batch = []
        self.last_flush_time = datetime.now()

    def consume(self):
        """Start consuming messages from Kafka"""
        logger.info(f"Starting to consume from topic: {self.config['topic']}")

        try:
            while self.running:
                # Poll for messages
                try:
                    for message in self.consumer:
                        if not self.running:
                            break

                        try:
                            data = message.value
                            self.message_batch.append(data)
                            logger.debug(
                                f"Received message for product: {data.get('product')}"
                            )

                            # Flush if batch is full
                            if len(self.message_batch) >= self.batch_size:
                                self._flush_batch()

                        except Exception as e:
                            logger.error(f"Error processing message: {e}")

                except StopIteration:
                    # No messages available, check timeout flush
                    pass

                # Check if we need to flush due to timeout
                elapsed = (datetime.now() - self.last_flush_time).total_seconds()
                if elapsed >= self.batch_timeout and self.message_batch:
                    self._flush_batch()

        except KeyboardInterrupt:
            pass
        finally:
            self._flush_batch()  # Flush remaining messages
            self.consumer.close()
            logger.info("Consumer closed")

    def stop(self):
        """Stop the consumer"""
        self.running = False


def main():
    config = {
        "kafka_bootstrap": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
        "consumer_group": os.getenv("KAFKA_CONSUMER_GROUP", "hdfs_storage_consumer"),
        "topic": os.getenv("KAFKA_TOPIC_RAW_DATA", "raw_social_data"),
        "hdfs_namenode_host": os.getenv("HDFS_NAMENODE_HOST", "namenode"),
        "hdfs_namenode_port": os.getenv("HDFS_NAMENODE_PORT", "9870"),
        "hdfs_url": os.getenv("HDFS_URL", "http://namenode:9870"),
    }

    consumer = KafkaDataConsumer(config)

    # Setup graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        consumer.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Starting Kafka consumer for HDFS storage")
    consumer.consume()


if __name__ == "__main__":
    main()
