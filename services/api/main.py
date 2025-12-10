"""
FastAPI Backend - Main API for FAQ Generation System
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import os
import httpx
import logging
from pymongo import MongoClient
from bson import ObjectId
import asyncio

# Import the FAQ generator
import sys

sys.path.append("/app/services/faq-generator")
from generator import FAQGeneratorService, FAQ

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="FAQ Generation API",
    description="API for generating FAQs from social media data",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB connection
mongo_client = MongoClient(os.getenv("MONGODB_URI", "mongodb://mongodb:27017"))
db = mongo_client[os.getenv("MONGODB_DATABASE", "faq_generation")]

# FAQ Generator Service
faq_service = FAQGeneratorService()


# Pydantic Models
class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    subreddits: Optional[List[str]] = (
        None  # Now optional - will auto-discover if not provided
    )
    keywords: List[str] = Field(default=["review", "problem", "help", "question"])
    category: Optional[str] = None
    auto_discover_subreddits: bool = Field(
        default=True, description="Automatically discover subreddits if not provided"
    )


class ProductResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    subreddits: List[str]
    keywords: List[str]
    category: Optional[str]
    created_at: datetime
    last_scraped: Optional[datetime]
    last_processed: Optional[datetime]
    faq_count: int
    status: str


class ScrapeRequest(BaseModel):
    product_id: str


class ProcessRequest(BaseModel):
    product_id: str


class GenerateFAQRequest(BaseModel):
    product_id: str


class FAQResponse(BaseModel):
    question: str
    answer: str
    category: str
    confidence: float
    sources: List[str]
    keywords: List[str]


class FAQListResponse(BaseModel):
    product: str
    faqs: List[FAQResponse]
    generated_at: Optional[datetime]
    model_used: Optional[str]
    source_count: int


class JobStatus(BaseModel):
    job_id: str
    product: str
    job_type: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    error: Optional[str]


# Helper functions
def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document for JSON serialization"""
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc


async def discover_subreddits(topic: str, top_n: int = 3) -> List[str]:
    """
    Automatically discover relevant subreddits for a topic using Reddit's search API

    Args:
        topic: The product/topic name to search for
        top_n: Number of top subreddits to return (default: 3)

    Returns:
        List of subreddit names (without 'r/' prefix)
    """
    try:
        # Reddit's subreddit search endpoint
        search_url = "https://www.reddit.com/subreddits/search.json"

        # Clean the topic for search (remove special chars, make lowercase)
        search_query = topic.strip().lower()

        headers = {"User-Agent": "FAQ-Generator/1.0"}

        params = {
            "q": search_query,
            "limit": 10,  # Get more results to filter from
            "sort": "relevance",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(search_url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                subreddits = []

                # Extract subreddit names and subscriber counts
                for child in data.get("data", {}).get("children", []):
                    subreddit_data = child.get("data", {})
                    name = subreddit_data.get("display_name")
                    subscribers = subreddit_data.get("subscribers", 0)

                    if name and subscribers > 1000:  # Filter out very small subreddits
                        subreddits.append({"name": name, "subscribers": subscribers})

                # Sort by subscriber count and get top N
                subreddits.sort(key=lambda x: x["subscribers"], reverse=True)
                top_subreddits = [s["name"] for s in subreddits[:top_n]]

                if top_subreddits:
                    logger.info(
                        f"Discovered subreddits for '{topic}': {top_subreddits}"
                    )
                    return top_subreddits
                else:
                    logger.warning(f"No subreddits found for '{topic}', using defaults")
                    return ["technology", "gadgets"]

            else:
                logger.error(f"Reddit API error: {response.status_code}")
                return ["technology", "gadgets"]

    except Exception as e:
        logger.error(f"Failed to discover subreddits: {e}")
        return ["technology", "gadgets"]  # Fallback to defaults


# Background tasks
async def trigger_scrape(product: dict):
    """Trigger scraping for a product"""
    try:
        scraper_url = os.getenv("REDDIT_SCRAPER_URL", "http://reddit-scraper:8081")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{scraper_url}/scrape",
                json={
                    "product": product["name"],
                    "subreddits": product.get("subreddits", []),
                    "keywords": product.get("keywords", []),
                },
            )

            if response.status_code == 200:
                # Update product status
                db.products.update_one(
                    {"_id": ObjectId(product["_id"])},
                    {"$set": {"last_scraped": datetime.utcnow(), "status": "scraping"}},
                )
                logger.info(f"Scrape triggered for {product['name']}")
            else:
                logger.error(f"Scrape trigger failed: {response.text}")

    except Exception as e:
        logger.error(f"Failed to trigger scrape: {e}")


async def trigger_processing(product: dict):
    """Trigger Spark processing for a product via Spark API"""
    try:
        product_name = product["name"]
        product_id = str(product["_id"])

        db.products.update_one(
            {"_id": ObjectId(product_id)}, {"$set": {"status": "processing"}}
        )
        logger.info(f"Processing triggered for {product_name}")

        # Call Spark API to submit job
        spark_api_url = "http://spark-master:8888/submit"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                spark_api_url, json={"product_name": product_name}
            )

            if response.status_code == 200:
                result = response.json()
                job_id = result.get("job_id")
                logger.info(f"Spark job submitted: {result}")

                # Poll for job completion
                status_url = f"http://spark-master:8888/status/{job_id}"
                max_attempts = 60  # 10 minutes max (10s * 60)

                for attempt in range(max_attempts):
                    await asyncio.sleep(10)  # Check every 10 seconds

                    try:
                        status_response = await client.get(status_url)
                        if status_response.status_code == 200:
                            status = status_response.json()
                            logger.info(f"Job {job_id} status: {status.get('status')}")

                            if status.get("status") == "completed":
                                db.products.update_one(
                                    {"_id": ObjectId(product_id)},
                                    {
                                        "$set": {
                                            "status": "processed",
                                            "last_processed": datetime.utcnow(),
                                        }
                                    },
                                )
                                logger.info(
                                    f"Spark processing completed for {product_name}"
                                )
                                return
                            elif status.get("status") in ["failed", "error", "timeout"]:
                                error_msg = status.get("error", "Unknown error")
                                logger.error(f"Spark processing failed: {error_msg}")
                                db.products.update_one(
                                    {"_id": ObjectId(product_id)},
                                    {
                                        "$set": {
                                            "status": "processing_failed",
                                            "error": error_msg,
                                        }
                                    },
                                )
                                return
                    except Exception as poll_err:
                        logger.warning(f"Error polling job status: {poll_err}")

                # Timeout waiting for job
                logger.warning(f"Timeout waiting for Spark job {job_id}")
                db.products.update_one(
                    {"_id": ObjectId(product_id)},
                    {"$set": {"status": "processing_timeout"}},
                )
            else:
                logger.error(f"Failed to submit Spark job: {response.text}")
                db.products.update_one(
                    {"_id": ObjectId(product_id)},
                    {"$set": {"status": "processing_failed", "error": response.text}},
                )

    except Exception as e:
        logger.error(f"Failed to trigger processing: {e}")
        db.products.update_one(
            {"_id": ObjectId(product["_id"])},
            {"$set": {"status": "processing_failed", "error": str(e)}},
        )


async def generate_faqs_task(product: dict):
    """Background task to generate FAQs"""
    try:
        db.products.update_one(
            {"_id": ObjectId(product["_id"])}, {"$set": {"status": "generating"}}
        )

        result = await faq_service.generate_faqs(product["name"])

        db.products.update_one(
            {"_id": ObjectId(product["_id"])},
            {
                "$set": {
                    "status": "completed",
                    "faq_count": len(result.faqs),
                    "last_processed": datetime.utcnow(),
                }
            },
        )

        logger.info(f"Generated {len(result.faqs)} FAQs for {product['name']}")

    except Exception as e:
        logger.error(f"FAQ generation failed: {e}")
        db.products.update_one(
            {"_id": ObjectId(product["_id"])},
            {"$set": {"status": "error", "error": str(e)}},
        )


# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "healthy", "service": "FAQ Generation API"}


@app.get("/health")
async def health():
    """Detailed health check"""
    try:
        # Check MongoDB
        mongo_client.admin.command("ping")
        mongo_status = "healthy"
    except Exception:
        mongo_status = "unhealthy"

    return {
        "status": "healthy" if mongo_status == "healthy" else "degraded",
        "mongodb": mongo_status,
        "timestamp": datetime.utcnow(),
    }


# Product endpoints
@app.post("/api/products", response_model=ProductResponse)
async def create_product(product: ProductCreate):
    """Create a new product to track"""
    # Check if product already exists
    existing = db.products.find_one({"name": product.name})
    if existing:
        raise HTTPException(status_code=400, detail="Product already exists")

    # Auto-discover subreddits if not provided or if auto_discover is enabled
    subreddits = product.subreddits
    if (
        subreddits is None or len(subreddits) == 0
    ) and product.auto_discover_subreddits:
        logger.info(f"Auto-discovering subreddits for '{product.name}'")
        subreddits = await discover_subreddits(product.name, top_n=3)
        logger.info(f"Discovered subreddits: {subreddits}")
    elif subreddits is None or len(subreddits) == 0:
        # Fallback to defaults if auto-discovery is disabled
        subreddits = ["technology", "gadgets"]

    doc = {
        "name": product.name,
        "description": product.description,
        "subreddits": subreddits,
        "keywords": product.keywords,
        "category": product.category,
        "created_at": datetime.utcnow(),
        "last_scraped": None,
        "last_processed": None,
        "faq_count": 0,
        "status": "pending",
    }

    result = db.products.insert_one(doc)
    doc["_id"] = result.inserted_id

    return serialize_doc(doc)


@app.get("/api/products", response_model=List[ProductResponse])
async def list_products(
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    """List all products"""
    cursor = db.products.find().skip(skip).limit(limit).sort("created_at", -1)
    products = [serialize_doc(doc) for doc in cursor]
    return products


@app.get("/api/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    """Get a specific product"""
    try:
        doc = db.products.find_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")

    return serialize_doc(doc)


@app.delete("/api/products/{product_id}")
async def delete_product(product_id: str):
    """Delete a product"""
    try:
        result = db.products.delete_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")

    # Also delete associated FAQs
    db.faqs.delete_many({"product_id": product_id})

    return {"message": "Product deleted successfully"}


@app.put("/api/products/{product_id}", response_model=ProductResponse)
async def update_product(product_id: str, product: ProductCreate):
    """Update a product"""
    try:
        result = db.products.update_one(
            {"_id": ObjectId(product_id)},
            {
                "$set": {
                    "name": product.name,
                    "description": product.description,
                    "subreddits": product.subreddits,
                    "keywords": product.keywords,
                    "category": product.category,
                }
            },
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")

    doc = db.products.find_one({"_id": ObjectId(product_id)})
    return serialize_doc(doc)


# Scraping endpoints
@app.post("/api/scrape")
async def trigger_scrape_endpoint(
    request: ScrapeRequest, background_tasks: BackgroundTasks
):
    """Trigger scraping for a product"""
    try:
        doc = db.products.find_one({"_id": ObjectId(request.product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")

    background_tasks.add_task(trigger_scrape, doc)

    return {
        "message": "Scrape job started",
        "product": doc["name"],
        "status": "started",
    }


# Processing endpoints
@app.post("/api/process")
async def trigger_process_endpoint(
    request: ProcessRequest, background_tasks: BackgroundTasks
):
    """Trigger data processing for a product"""
    try:
        doc = db.products.find_one({"_id": ObjectId(request.product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")

    background_tasks.add_task(trigger_processing, doc)

    return {
        "message": "Processing job started",
        "product": doc["name"],
        "status": "started",
    }


# FAQ Generation endpoints
@app.post("/api/generate-faqs")
async def generate_faqs_endpoint(
    request: GenerateFAQRequest, background_tasks: BackgroundTasks
):
    """Generate FAQs for a product"""
    try:
        doc = db.products.find_one({"_id": ObjectId(request.product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")

    background_tasks.add_task(generate_faqs_task, doc)

    return {
        "message": "FAQ generation started",
        "product": doc["name"],
        "status": "started",
    }


@app.get("/api/faqs/{product_name}", response_model=FAQListResponse)
async def get_faqs(product_name: str):
    """Get FAQs for a product"""
    doc = db.faqs.find_one({"product": product_name})

    if not doc:
        raise HTTPException(status_code=404, detail="FAQs not found for this product")

    return {
        "product": doc["product"],
        "faqs": doc.get("faqs", []),
        "generated_at": doc.get("generated_at"),
        "model_used": doc.get("model_used"),
        "source_count": doc.get("source_count", 0),
    }


@app.get("/api/faqs")
async def list_all_faqs():
    """List all products with FAQs"""
    cursor = db.faqs.find({}, {"product": 1, "generated_at": 1, "model_used": 1})
    return [serialize_doc(doc) for doc in cursor]


# Full pipeline endpoint
@app.post("/api/pipeline/{product_id}")
async def run_full_pipeline(product_id: str, background_tasks: BackgroundTasks):
    """Run the full pipeline: scrape -> process (Spark) -> generate FAQs"""
    try:
        doc = db.products.find_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")

    async def run_pipeline(product: dict):
        """Run full pipeline sequentially"""
        product_id = str(product["_id"])
        product_name = product["name"]

        try:
            # Step 1: Scrape
            logger.info(f"Pipeline: Step 1/3 - Starting scrape for {product_name}")
            db.products.update_one(
                {"_id": ObjectId(product_id)}, {"$set": {"status": "pipeline_scraping"}}
            )
            await trigger_scrape(product)

            # Wait for scraping to complete (poll status or wait fixed time)
            # In production, message use garne plan xa tarw na bihauna ni sakinxa
            await asyncio.sleep(90)  # Wait for scraping to complete

            # Step 2: Spark Processing
            logger.info(
                f"Pipeline: Step 2/3 - Starting Spark processing for {product_name}"
            )
            db.products.update_one(
                {"_id": ObjectId(product_id)},
                {"$set": {"status": "pipeline_processing"}},
            )
            await trigger_processing(product)

            # Step 3: Generate FAQs
            logger.info(
                f"Pipeline: Step 3/3 - Starting FAQ generation for {product_name}"
            )
            db.products.update_one(
                {"_id": ObjectId(product_id)},
                {"$set": {"status": "pipeline_generating"}},
            )
            await generate_faqs_task(product)

            db.products.update_one(
                {"_id": ObjectId(product_id)},
                {"$set": {"status": "pipeline_completed"}},
            )
            logger.info(f"Pipeline: Completed successfully for {product_name}")

        except Exception as e:
            logger.error(f"Pipeline failed for {product_name}: {e}")
            db.products.update_one(
                {"_id": ObjectId(product_id)},
                {"$set": {"status": "pipeline_error", "error": str(e)}},
            )

    background_tasks.add_task(run_pipeline, doc)

    return {
        "message": "Full pipeline started",
        "product": doc["name"],
        "steps": ["scrape (Reddit)", "process (Spark)", "generate_faqs (LLM)"],
        "note": "Pipeline runs in background. Check product status for progress.",
    }


# Stats endpoint
@app.get("/api/stats")
async def get_stats():
    """Get system statistics"""
    total_products = db.products.count_documents({})
    total_faqs = db.faqs.count_documents({})

    # Count FAQs by status
    status_counts = {}
    for status in [
        "pending",
        "scraping",
        "processing",
        "generating",
        "completed",
        "error",
    ]:
        status_counts[status] = db.products.count_documents({"status": status})

    return {
        "total_products": total_products,
        "total_faq_documents": total_faqs,
        "products_by_status": status_counts,
        "timestamp": datetime.utcnow(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
