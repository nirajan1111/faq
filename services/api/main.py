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
    subreddits: List[str] = Field(default=["technology", "gadgets"])
    keywords: List[str] = Field(default=["review", "problem", "help", "question"])
    category: Optional[str] = None


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
    """Trigger Spark processing for a product"""
    try:
        # This would typically trigger a Spark job
        # For now, we'll update the status
        db.products.update_one(
            {"_id": ObjectId(product["_id"])}, {"$set": {"status": "processing"}}
        )
        logger.info(f"Processing triggered for {product['name']}")

    except Exception as e:
        logger.error(f"Failed to trigger processing: {e}")


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

    doc = {
        "name": product.name,
        "description": product.description,
        "subreddits": product.subreddits,
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
    """Run the full pipeline: scrape -> process -> generate FAQs"""
    try:
        doc = db.products.find_one({"_id": ObjectId(product_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product ID")

    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")

    async def run_pipeline(product: dict):
        """Run full pipeline sequentially"""
        try:
            # Step 1: Scrape
            logger.info(f"Pipeline: Starting scrape for {product['name']}")
            await trigger_scrape(product)
            await asyncio.sleep(60)  # Wait for scraping

            # Step 2: Process (would trigger Spark)
            logger.info(f"Pipeline: Starting processing for {product['name']}")
            await trigger_processing(product)
            await asyncio.sleep(30)  # Wait for processing

            # Step 3: Generate FAQs
            logger.info(f"Pipeline: Starting FAQ generation for {product['name']}")
            await generate_faqs_task(product)

            logger.info(f"Pipeline: Completed for {product['name']}")

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            db.products.update_one(
                {"_id": ObjectId(product["_id"])},
                {"$set": {"status": "error", "error": str(e)}},
            )

    background_tasks.add_task(run_pipeline, doc)

    return {
        "message": "Full pipeline started",
        "product": doc["name"],
        "steps": ["scrape", "process", "generate_faqs"],
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
