"""
Simple HTTP API for triggering Spark jobs
This runs inside the spark-master container and executes spark-submit locally
"""

from flask import Flask, request, jsonify
import subprocess
import threading
import logging
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track running jobs
running_jobs = {}


def run_spark_job(product_name: str, job_id: str):
    """Run spark-submit in background"""
    try:
        running_jobs[job_id] = {"status": "running", "product": product_name}

        cmd = [
            "/opt/spark/bin/spark-submit",
            "--master",
            "spark://spark-master:7077",
            "--driver-memory",
            "1g",
            "--executor-memory",
            "1g",
            "/app/src/processor.py",
            product_name,
        ]

        logger.info(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )

        if result.returncode == 0:
            running_jobs[job_id] = {
                "status": "completed",
                "product": product_name,
                "output": result.stdout[-1000:] if result.stdout else "",
            }
            logger.info(f"Job {job_id} completed successfully")
        else:
            running_jobs[job_id] = {
                "status": "failed",
                "product": product_name,
                "error": result.stderr[-500:] if result.stderr else "Unknown error",
            }
            logger.error(f"Job {job_id} failed: {result.stderr[:500]}")

    except subprocess.TimeoutExpired:
        running_jobs[job_id] = {
            "status": "timeout",
            "product": product_name,
            "error": "Job timed out after 10 minutes",
        }
    except Exception as e:
        running_jobs[job_id] = {
            "status": "error",
            "product": product_name,
            "error": str(e),
        }
        logger.error(f"Job {job_id} error: {e}")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"})


@app.route("/submit", methods=["POST"])
def submit_job():
    """Submit a Spark processing job"""
    data = request.json or {}
    product_name = data.get("product_name") or data.get("product")

    if not product_name:
        return jsonify({"error": "product_name is required"}), 400

    import uuid

    job_id = str(uuid.uuid4())[:8]

    # Run in background thread
    thread = threading.Thread(target=run_spark_job, args=(product_name, job_id))
    thread.daemon = True
    thread.start()

    return jsonify(
        {
            "status": "submitted",
            "job_id": job_id,
            "product": product_name,
            "message": "Job submitted successfully",
        }
    )


@app.route("/status/<job_id>", methods=["GET"])
def job_status(job_id: str):
    """Get status of a job"""
    if job_id in running_jobs:
        return jsonify(running_jobs[job_id])
    return jsonify({"status": "not_found"}), 404


@app.route("/jobs", methods=["GET"])
def list_jobs():
    """List all jobs"""
    return jsonify(running_jobs)


if __name__ == "__main__":
    port = int(os.getenv("SPARK_API_PORT", 8888))
    app.run(host="0.0.0.0", port=port)
