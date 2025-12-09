"""
Spark Data Processor - Processes raw social data for FAQ generation
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    lower,
    regexp_replace,
    trim,
    split,
    explode,
    count,
    avg,
    sum as spark_sum,
    collect_list,
    concat_ws,
    udf,
    lit,
    when,
    length,
    row_number,
    desc,
    asc,
    from_json,
    to_json,
    struct,
    array,
    size,
)
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    TimestampType,
    ArrayType,
    FloatType,
    MapType,
)
from pyspark.ml.feature import HashingTF, IDF, Tokenizer, StopWordsRemover
from pyspark.ml.clustering import KMeans
import os
import json
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SparkDataProcessor:
    """Process raw social media data using Spark"""

    def __init__(self):
        self.spark = (
            SparkSession.builder.appName("FAQDataProcessor")
            .config("spark.driver.memory", "1g")
            .config("spark.executor.memory", "1g")
            .getOrCreate()
        )

        self.spark.sparkContext.setLogLevel("WARN")

        self.hdfs_base = os.getenv("HDFS_URL", "hdfs://namenode:9000")
        self.raw_data_path = f"{self.hdfs_base}/data/raw"
        self.processed_data_path = f"{self.hdfs_base}/data/processed"

        # Schema for raw social data
        self.raw_schema = StructType(
            [
                StructField("source", StringType(), True),
                StructField("product", StringType(), True),
                StructField("data_type", StringType(), True),
                StructField("content", StringType(), True),
                StructField("title", StringType(), True),
                StructField("author", StringType(), True),
                StructField("score", IntegerType(), True),
                StructField("url", StringType(), True),
                StructField("subreddit", StringType(), True),
                StructField("created_at", StringType(), True),
                StructField("scraped_at", StringType(), True),
                StructField("metadata", MapType(StringType(), StringType()), True),
            ]
        )

    def load_raw_data(self, product: str, source: str = "reddit"):
        """Load raw data from HDFS for a specific product"""
        product_clean = product.replace(" ", "_").lower()

        # Try multiple path variants (with and without trailing underscore)
        path_variants = [
            f"{self.raw_data_path}/{source}/{product_clean}/*.json",
            f"{self.raw_data_path}/{source}/{product_clean}_/*.json",
        ]

        for path in path_variants:
            try:
                logger.info(f"Trying to load from: {path}")
                df = self.spark.read.json(path, multiLine=True)
                count = df.count()
                if count > 0:
                    logger.info(f"Loaded {count} records for {product} from {path}")
                    return df
            except Exception as e:
                logger.warning(f"Path {path} failed: {e}")
                continue

        logger.error(f"Failed to load data from any path variant for {product}")
        return None

    def clean_text(self, df):
        """Clean and normalize text content"""
        # Remove URLs, special characters, extra whitespace
        cleaned_df = df.withColumn(
            "content_cleaned",
            trim(
                regexp_replace(
                    regexp_replace(
                        regexp_replace(
                            lower(col("content")),
                            r"http\S+|www\.\S+",
                            "",  # Remove URLs
                        ),
                        r"[^a-zA-Z0-9\s\?\.\!]",
                        " ",  # Keep alphanumeric and basic punctuation
                    ),
                    r"\s+",
                    " ",  # Normalize whitespace
                )
            ),
        )

        # Filter out very short or empty content
        cleaned_df = cleaned_df.filter(length(col("content_cleaned")) > 20)

        return cleaned_df

    def extract_questions(self, df):
        """Extract potential questions from content"""

        # UDF to identify question sentences
        def is_question(text):
            if not text:
                return []
            sentences = text.replace("!", ".").replace("?", "?.").split(".")
            questions = []
            question_starters = [
                "how",
                "what",
                "why",
                "when",
                "where",
                "which",
                "who",
                "is",
                "are",
                "can",
                "could",
                "would",
                "should",
                "does",
                "do",
                "will",
                "has",
                "have",
                "any",
            ]
            for sentence in sentences:
                sentence = sentence.strip()
                if sentence and (
                    sentence.endswith("?")
                    or any(sentence.lower().startswith(q) for q in question_starters)
                ):
                    if len(sentence) > 15:  # Filter very short questions
                        questions.append(sentence)
            return questions

        extract_questions_udf = udf(is_question, ArrayType(StringType()))

        df_with_questions = df.withColumn(
            "extracted_questions", extract_questions_udf(col("content_cleaned"))
        )

        return df_with_questions

    def aggregate_by_topic(self, df):
        """Aggregate content by topics/themes"""
        # Tokenize content
        tokenizer = Tokenizer(inputCol="content_cleaned", outputCol="words")
        words_df = tokenizer.transform(df)

        # Remove stop words
        remover = StopWordsRemover(inputCol="words", outputCol="filtered_words")
        filtered_df = remover.transform(words_df)

        # Calculate TF-IDF
        hashingTF = HashingTF(
            inputCol="filtered_words", outputCol="raw_features", numFeatures=1000
        )
        featurized_df = hashingTF.transform(filtered_df)

        idf = IDF(inputCol="raw_features", outputCol="features")
        idf_model = idf.fit(featurized_df)
        tfidf_df = idf_model.transform(featurized_df)

        # Cluster similar content
        kmeans = KMeans(k=10, seed=42, featuresCol="features", predictionCol="cluster")

        try:
            model = kmeans.fit(tfidf_df)
            clustered_df = model.transform(tfidf_df)

            # Aggregate by cluster
            aggregated = clustered_df.groupBy("cluster").agg(
                count("*").alias("post_count"),
                avg("score").alias("avg_score"),
                collect_list("content_cleaned").alias("contents"),
                collect_list("extracted_questions").alias("all_questions"),
                collect_list("url").alias("source_urls"),
            )

            return aggregated
        except Exception as e:
            logger.error(f"Clustering failed: {e}")
            return df

    def calculate_content_metrics(self, df):
        """Calculate engagement metrics and relevance scores"""
        metrics_df = (
            df.withColumn(
                "relevance_score",
                (col("score") + 1) * when(col("data_type") == "post", 2).otherwise(1),
            )
            .withColumn("content_length", length(col("content_cleaned")))
            .withColumn("has_question", size(col("extracted_questions")) > 0)
        )

        return metrics_df

    def prepare_for_faq_generation(self, df, product: str):
        """Prepare final dataset for FAQ generation"""
        # Select and format data for FAQ generation
        faq_ready_df = (
            df.select(
                lit(product).alias("product"),
                col("content_cleaned").alias("content"),
                col("extracted_questions"),
                col("relevance_score"),
                col("data_type"),
                col("url").alias("source_url"),
                col("score").alias("engagement_score"),
            )
            .filter(
                (col("relevance_score") > 1) | (size(col("extracted_questions")) > 0)
            )
            .orderBy(desc("relevance_score"))
            .limit(500)
        )  # Top 500 most relevant items

        return faq_ready_df

    def save_processed_data(self, df, product: str):
        """Save processed data to HDFS"""
        product_clean = product.replace(" ", "_").lower()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save to HDFS as Parquet
        hdfs_path = f"{self.processed_data_path}/{product_clean}/{timestamp}"
        df.write.mode("overwrite").parquet(hdfs_path)
        logger.info(f"Saved processed data to HDFS: {hdfs_path}")

        # Also save as JSON for easier reading by FAQ generator
        json_path = f"{self.processed_data_path}/{product_clean}/latest.json"
        df.coalesce(1).write.mode("overwrite").json(json_path)
        logger.info(f"Saved JSON data to: {json_path}")

        return hdfs_path

    def process_product(self, product: str, source: str = "reddit"):
        """Full processing pipeline for a product"""
        logger.info(f"Starting processing pipeline for: {product}")

        # Load raw data
        raw_df = self.load_raw_data(product, source)
        if raw_df is None or raw_df.count() == 0:
            logger.warning(f"No data found for {product}")
            return None

        # Clean text
        cleaned_df = self.clean_text(raw_df)
        logger.info(f"Cleaned data: {cleaned_df.count()} records")

        # Extract questions
        questions_df = self.extract_questions(cleaned_df)

        # Calculate metrics
        metrics_df = self.calculate_content_metrics(questions_df)

        # Prepare for FAQ generation
        faq_ready_df = self.prepare_for_faq_generation(metrics_df, product)
        logger.info(f"FAQ-ready data: {faq_ready_df.count()} records")

        # Save processed data
        output_path = self.save_processed_data(faq_ready_df, product)

        # Return summary
        return {
            "product": product,
            "total_records": raw_df.count(),
            "processed_records": faq_ready_df.count(),
            "output_path": output_path,
        }

    def get_processed_data(self, product: str):
        """Retrieve processed data for a product from HDFS"""
        product_clean = product.replace(" ", "_").lower()

        try:
            # Read the latest JSON data from HDFS
            json_path = f"{self.processed_data_path}/{product_clean}/latest.json"
            df = self.spark.read.json(json_path)
            return df.toPandas().to_dict("records")
        except Exception as e:
            logger.error(f"Failed to retrieve processed data: {e}")
            return []

    def stop(self):
        """Stop Spark session"""
        self.spark.stop()


def main():
    """Main entry point for Spark processing job"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: spark-submit processor.py <product_name>")
        sys.exit(1)

    product = sys.argv[1]
    source = sys.argv[2] if len(sys.argv) > 2 else "reddit"

    processor = SparkDataProcessor()

    try:
        result = processor.process_product(product, source)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print(f"No data processed for {product}")
    finally:
        processor.stop()


if __name__ == "__main__":
    main()
