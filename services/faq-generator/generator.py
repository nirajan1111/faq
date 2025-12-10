"""
FAQ Generation Service - Uses LLMs to generate FAQs from processed data
"""

import os
import json
import logging
import asyncio
from typing import List, Dict, Optional
from datetime import datetime
from abc import ABC, abstractmethod
import httpx
from pymongo import MongoClient
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FAQ(BaseModel):
    """FAQ model"""

    question: str
    answer: str
    category: str
    confidence: float
    sources: List[str]
    keywords: List[str]


class FAQGenerationResult(BaseModel):
    """Result of FAQ generation"""

    product: str
    faqs: List[FAQ]
    generated_at: datetime
    model_used: str
    source_count: int


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    async def generate_faqs(self, product: str, content: List[Dict]) -> List[FAQ]:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass


class GeminiProvider(LLMProvider):
    """Google Gemini API provider"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = "gemini-2.0-flash"  # Updated model name

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def generate_faqs(self, product: str, content: List[Dict]) -> List[FAQ]:
        """Generate FAQs using Gemini API"""

        # Prepare content summary
        content_text = self._prepare_content(content)

        prompt = self._create_prompt(product, content_text)
        print("Gemini Prompt:", prompt)
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.7,
                        "topK": 40,
                        "topP": 0.95,
                        "maxOutputTokens": 8192,
                    },
                },
            )

            if response.status_code != 200:
                logger.error(
                    f"Gemini API error: {response.status_code} - {response.text}"
                )
                raise Exception(f"Gemini API error: {response.status_code}")

            result = response.json()

            try:
                generated_text = result["candidates"][0]["content"]["parts"][0]["text"]
                return self._parse_faqs(generated_text, content)
            except (KeyError, IndexError) as e:
                logger.error(f"Failed to parse Gemini response: {e}")
                raise

    def _prepare_content(self, content: List[Dict]) -> str:
        """Prepare content for the prompt"""
        texts = []
        for item in content[:100]:  # Limit to 100 items
            text = item.get("content", "")
            questions = item.get("extracted_questions", [])
            if questions:
                text += "\nQuestions found: " + "; ".join(questions[:3])
            texts.append(text[:500])  # Limit each item

        return "\n---\n".join(texts)

    def _create_prompt(self, product: str, content: str) -> str:
        """Create the FAQ generation prompt"""
        return f"""You are an expert FAQ generator. Analyze the following user discussions, reviews, and comments about "{product}" and generate comprehensive FAQs.

USER DISCUSSIONS AND REVIEWS:
{content}

Based on the above content, generate 15-20 high-quality FAQs about "{product}". For each FAQ:
1. Identify common questions, concerns, and topics users discuss
2. Provide accurate, helpful answers based on the content
3. Categorize each FAQ (e.g., "Features", "Troubleshooting", "Setup", "Performance", "Comparison", "Purchase")
4. Include relevant keywords

IMPORTANT: Return your response as a valid JSON array with the following structure:
```json
[
  {{
    "question": "The question text",
    "answer": "A comprehensive answer based on user discussions",
    "category": "Category name",
    "confidence": 0.85,
    "keywords": ["keyword1", "keyword2", "keyword3"]
  }}
]
```

Generate the FAQs now:"""

    def _parse_faqs(self, text: str, content: List[Dict]) -> List[FAQ]:
        """Parse FAQs from LLM response"""
        # Extract JSON from response
        try:
            # Find JSON array in response
            start_idx = text.find("[")
            end_idx = text.rfind("]") + 1

            if start_idx == -1 or end_idx == 0:
                raise ValueError("No JSON array found in response")

            json_str = text[start_idx:end_idx]
            faqs_data = json.loads(json_str)

            # Get source URLs
            source_urls = [
                item.get("source_url", "")
                for item in content[:10]
                if item.get("source_url")
            ]

            faqs = []
            for faq_data in faqs_data:
                faq = FAQ(
                    question=faq_data.get("question", ""),
                    answer=faq_data.get("answer", ""),
                    category=faq_data.get("category", "General"),
                    confidence=float(faq_data.get("confidence", 0.8)),
                    sources=source_urls[:3],
                    keywords=faq_data.get("keywords", []),
                )
                faqs.append(faq)

            return faqs

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {e}")
            logger.debug(f"Response text: {text[:500]}")
            raise


class OllamaProvider(LLMProvider):
    """Ollama local LLM provider"""

    def __init__(self, host: str, model: str = "llama3.2"):
        self.host = host
        self.model = model

    def is_available(self) -> bool:
        try:
            import httpx

            response = httpx.get(f"{self.host}/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    async def generate_faqs(self, product: str, content: List[Dict]) -> List[FAQ]:
        """Generate FAQs using Ollama"""

        content_text = self._prepare_content(content)
        prompt = self._create_prompt(product, content_text)

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 4096,
                    },
                },
            )

            if response.status_code != 200:
                logger.error(f"Ollama API error: {response.status_code}")
                raise Exception(f"Ollama API error: {response.status_code}")

            result = response.json()
            generated_text = result.get("response", "")

            return self._parse_faqs(generated_text, content)

    def _prepare_content(self, content: List[Dict]) -> str:
        """Prepare content for the prompt (shorter for local models)"""
        texts = []
        for item in content[:50]:  # Limit to 50 items for local models
            text = item.get("content", "")[:300]
            questions = item.get("extracted_questions", [])
            if questions:
                text += " Questions: " + "; ".join(questions[:2])
            texts.append(text)

        return "\n---\n".join(texts)

    def _create_prompt(self, product: str, content: str) -> str:
        """Create a shorter prompt for local models"""
        return f"""Analyze these user discussions about "{product}" and generate 10 FAQs.

CONTENT:
{content}

Generate FAQs as a JSON array:
[{{"question": "...", "answer": "...", "category": "...", "confidence": 0.8, "keywords": ["..."]}}]

FAQs:"""

    def _parse_faqs(self, text: str, content: List[Dict]) -> List[FAQ]:
        """Parse FAQs from Ollama response"""
        try:
            start_idx = text.find("[")
            end_idx = text.rfind("]") + 1

            if start_idx == -1 or end_idx == 0:
                # Try to extract FAQs manually if JSON parsing fails
                return self._extract_faqs_manually(text, content)

            json_str = text[start_idx:end_idx]
            faqs_data = json.loads(json_str)

            source_urls = [
                item.get("source_url", "")
                for item in content[:5]
                if item.get("source_url")
            ]

            faqs = []
            for faq_data in faqs_data:
                faq = FAQ(
                    question=faq_data.get("question", ""),
                    answer=faq_data.get("answer", ""),
                    category=faq_data.get("category", "General"),
                    confidence=float(faq_data.get("confidence", 0.7)),
                    sources=source_urls[:3],
                    keywords=faq_data.get("keywords", []),
                )
                faqs.append(faq)

            return faqs

        except json.JSONDecodeError:
            return self._extract_faqs_manually(text, content)

    def _extract_faqs_manually(self, text: str, content: List[Dict]) -> List[FAQ]:
        """Fallback: Extract FAQs manually from text"""
        faqs = []
        lines = text.split("\n")

        current_question = None
        current_answer = ""

        for line in lines:
            line = line.strip()
            if line.startswith("Q:") or line.startswith("Question:"):
                if current_question and current_answer:
                    faqs.append(
                        FAQ(
                            question=current_question,
                            answer=current_answer.strip(),
                            category="General",
                            confidence=0.6,
                            sources=[],
                            keywords=[],
                        )
                    )
                current_question = line.split(":", 1)[1].strip()
                current_answer = ""
            elif line.startswith("A:") or line.startswith("Answer:"):
                current_answer = line.split(":", 1)[1].strip()
            elif current_question and line:
                current_answer += " " + line

        if current_question and current_answer:
            faqs.append(
                FAQ(
                    question=current_question,
                    answer=current_answer.strip(),
                    category="General",
                    confidence=0.6,
                    sources=[],
                    keywords=[],
                )
            )

        return faqs


class FAQGeneratorService:
    """Main FAQ generation service"""

    def __init__(self):
        self.gemini = GeminiProvider(os.getenv("GEMINI_API_KEY", ""))
        self.ollama = OllamaProvider(
            os.getenv("OLLAMA_HOST", "http://ollama:11434"),
            os.getenv("OLLAMA_MODEL", "llama3.2"),
        )
        self.use_ollama_fallback = (
            os.getenv("USE_OLLAMA_FALLBACK", "true").lower() == "true"
        )

        # MongoDB connection
        self.mongo_client = MongoClient(
            os.getenv("MONGODB_URI", "mongodb://mongodb:27017")
        )
        self.db = self.mongo_client[os.getenv("MONGODB_DATABASE", "faq_generation")]
        self.faqs_collection = self.db["faqs"]
        self.products_collection = self.db["products"]

        # HDFS configuration
        self.hdfs_url = os.getenv("HDFS_URL", "http://namenode:9870")

    def get_raw_content_from_hdfs(self, product: str) -> List[Dict]:
        """Get raw content directly from HDFS via WebHDFS"""
        # Normalize product name to match consumer's slug format
        product_clean = product.strip().replace(" ", "_").lower()
        # Also try with trailing underscore (in case of trailing spaces in original)
        product_clean_alt = product.replace(" ", "_").lower()

        hdfs_paths_to_try = [
            f"/data/raw/reddit/{product_clean}",
            f"/data/raw/reddit/{product_clean_alt}",
            f"/data/raw/reddit/{product_clean}_",  # trailing underscore variant
        ]

        for hdfs_path in hdfs_paths_to_try:
            try:
                # List files in HDFS directory
                list_url = f"{self.hdfs_url}/webhdfs/v1{hdfs_path}?op=LISTSTATUS&user.name=root"
                response = httpx.get(list_url, timeout=30.0)

                if response.status_code != 200:
                    logger.debug(f"HDFS path not found: {hdfs_path}")
                    continue

                files = response.json().get("FileStatuses", {}).get("FileStatus", [])
                json_files = [f for f in files if f["pathSuffix"].endswith(".json")]

                if not json_files:
                    continue

                all_content = []
                for file_info in json_files[:20]:  # Limit to 20 files
                    file_path = f"{hdfs_path}/{file_info['pathSuffix']}"
                    read_url = (
                        f"{self.hdfs_url}/webhdfs/v1{file_path}?op=OPEN&user.name=root"
                    )

                    file_response = httpx.get(
                        read_url, timeout=30.0, follow_redirects=True
                    )
                    if file_response.status_code == 200:
                        try:
                            data = file_response.json()
                            if isinstance(data, list):
                                all_content.extend(data)
                            else:
                                all_content.append(data)
                        except json.JSONDecodeError:
                            continue

                if all_content:
                    logger.info(
                        f"Loaded {len(all_content)} items from HDFS path {hdfs_path} for {product}"
                    )
                    return all_content

            except Exception as e:
                logger.debug(f"Failed to read from HDFS path {hdfs_path}: {e}")
                continue

        logger.warning(f"No HDFS data found for {product} in any path variant")
        return []

    def get_processed_content(self, product: str) -> List[Dict]:
        """Get processed content from MongoDB, fallback to HDFS raw data"""
        product_clean = product.replace(" ", "_").lower()
        collection_name = f"processed_{product_clean}"

        try:
            collection = self.db[collection_name]
            cursor = collection.find({}).sort("relevance_score", -1).limit(200)
            content = list(cursor)

            if content:
                return content

            # Fallback: Read raw data from HDFS
            logger.info(f"No processed content found, reading raw data from HDFS")
            raw_content = self.get_raw_content_from_hdfs(product)

            if raw_content:
                # Transform raw content to expected format
                processed = []
                for item in raw_content:
                    processed.append(
                        {
                            "content": item.get("body", item.get("title", "")),
                            "title": item.get("title", ""),
                            "source": item.get("subreddit", "reddit"),
                            "url": item.get("url", ""),
                            "score": item.get("score", 0),
                            "extracted_questions": [],
                        }
                    )
                return processed

            return []
        except Exception as e:
            logger.error(f"Failed to get processed content: {e}")
            return []

    async def generate_faqs(
        self, product: str, content: Optional[List[Dict]] = None
    ) -> FAQGenerationResult:
        """Generate FAQs for a product"""

        if content is None:
            content = self.get_processed_content(product)

        if not content:
            raise ValueError(f"No processed content found for {product}")

        logger.info(f"Generating FAQs for {product} from {len(content)} content items")

        model_used = "none"
        faqs = []

        # Try Gemini first
        if self.gemini.is_available():
            try:
                logger.info("Using Gemini for FAQ generation")
                faqs = await self.gemini.generate_faqs(product, content)
                model_used = "gemini"
            except Exception as e:
                logger.error(f"Gemini generation failed: {e}")
                if self.use_ollama_fallback:
                    logger.info("Falling back to Ollama")

        # Fall back to Ollama if Gemini failed or unavailable
        if not faqs and self.use_ollama_fallback:
            if self.ollama.is_available():
                try:
                    logger.info("Using Ollama for FAQ generation")
                    faqs = await self.ollama.generate_faqs(product, content)
                    model_used = f"ollama/{self.ollama.model}"
                except Exception as e:
                    logger.error(f"Ollama generation failed: {e}")
            else:
                logger.warning("Ollama is not available")

        if not faqs:
            raise Exception("FAQ generation failed with all available providers")

        result = FAQGenerationResult(
            product=product,
            faqs=faqs,
            generated_at=datetime.utcnow(),
            model_used=model_used,
            source_count=len(content),
        )

        # Save to MongoDB
        self._save_faqs(result)

        return result

    def _save_faqs(self, result: FAQGenerationResult):
        """Save generated FAQs to MongoDB"""
        try:
            # Convert to dict for MongoDB
            doc = {
                "product": result.product,
                "faqs": [faq.model_dump() for faq in result.faqs],
                "generated_at": result.generated_at,
                "model_used": result.model_used,
                "source_count": result.source_count,
                "updated_at": datetime.utcnow(),
            }

            # Upsert by product
            self.faqs_collection.update_one(
                {"product": result.product}, {"$set": doc}, upsert=True
            )

            logger.info(f"Saved {len(result.faqs)} FAQs for {result.product}")

        except Exception as e:
            logger.error(f"Failed to save FAQs: {e}")

    def get_faqs(self, product: str) -> Optional[Dict]:
        """Get FAQs for a product from MongoDB"""
        try:
            doc = self.faqs_collection.find_one({"product": product})
            if doc:
                doc["_id"] = str(doc["_id"])
            return doc
        except Exception as e:
            logger.error(f"Failed to get FAQs: {e}")
            return None

    def get_all_products_with_faqs(self) -> List[Dict]:
        """Get all products that have FAQs"""
        try:
            cursor = self.faqs_collection.find(
                {},
                {"product": 1, "generated_at": 1, "model_used": 1, "source_count": 1},
            )
            products = []
            for doc in cursor:
                doc["_id"] = str(doc["_id"])
                products.append(doc)
            return products
        except Exception as e:
            logger.error(f"Failed to get products: {e}")
            return []


# For standalone testing
async def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage: python generator.py <product_name>")
        sys.exit(1)

    product = sys.argv[1]

    service = FAQGeneratorService()

    try:
        result = await service.generate_faqs(product)
        print(f"\nGenerated {len(result.faqs)} FAQs for {result.product}")
        print(f"Model used: {result.model_used}")
        print("\nFAQs:")
        for i, faq in enumerate(result.faqs, 1):
            print(f"\n{i}. Q: {faq.question}")
            print(f"   A: {faq.answer[:200]}...")
            print(f"   Category: {faq.category}")
    except Exception as e:
        logger.error(f"FAQ generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
