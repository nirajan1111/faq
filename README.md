# FAQ Generation System

A production-ready, scalable FAQ generation system that scrapes social media data (Reddit), processes it with Apache Spark, and generates intelligent FAQs using LLMs (Google Gemini / Ollama).

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FAQ Generation System                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌─────────────┐     ┌──────────────┐                  │
│  │   Reddit     │────▶│   Apache    │────▶│    HDFS      │                  │
│  │  Scraper(Go) │     │   Kafka     │     │   Storage    │                  │
│  └──────────────┘     └─────────────┘     └──────────────┘                  │
│                              │                    │                          │
│                              │                    ▼                          │
│                              │            ┌──────────────┐                   │
│                              │            │    Apache    │                   │
│                              │            │    Spark     │                   │
│                              │            └──────────────┘                   │
│                              │                    │                          │
│                              ▼                    ▼                          │
│                       ┌──────────────┐    ┌──────────────┐                   │
│                       │   MongoDB    │◀───│     FAQ      │                   │
│                       │              │    │  Generator   │                   │
│                       └──────────────┘    │ (Gemini/     │                   │
│                              │            │  Ollama)     │                   │
│                              │            └──────────────┘                   │
│                              ▼                                               │
│                       ┌──────────────┐                                       │
│                       │   FastAPI    │                                       │
│                       │   Backend    │                                       │
│                       └──────────────┘                                       │
│                              │                                               │
│                              ▼                                               │
│                       ┌──────────────┐                                       │
│                       │    React     │                                       │
│                       │  Dashboard   │                                       │
│                       └──────────────┘                                       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 🚀 Features

- **Multi-Source Scraping**: Go-based Reddit scraper with rate limiting (100 posts/minute)
- **Real-time Streaming**: Apache Kafka for reliable message queuing
- **Distributed Storage**: HDFS for storing raw and processed data
- **Big Data Processing**: Apache Spark for data cleaning and analysis
- **AI-Powered FAQ Generation**: Google Gemini with Ollama fallback
- **Modern Dashboard**: React/Next.js UI for product management
- **REST API**: FastAPI backend for all operations
- **Fully Dockerized**: Production-ready Docker Compose setup

## 📋 Prerequisites

- Docker & Docker Compose
- 8GB+ RAM (recommended 16GB for full stack)
- Reddit API credentials
- Google Gemini API key (optional, has Ollama fallback)
- Ollama installed locally (optional, for local LLM)

## 🛠️ Quick Start

### 1. Clone and Configure

```bash
cd faq_generation

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

### 2. Set Environment Variables

Edit `.env` file:

```env
# Reddit API Credentials
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=CompanyFAQScraper/1.0 by u/your_username

# LLM Configuration
GEMINI_API_KEY=your_gemini_api_key
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=llama3.2
USE_OLLAMA_FALLBACK=true
```

### 3. Start the System

**For Development (lighter weight):**

```bash
docker-compose -f docker-compose.dev.yml up -d
```

**For Production (full stack):**

```bash
docker-compose up -d
```

### 4. Access Services

| Service    | URL                        | Description                           |
| ---------- | -------------------------- | ------------------------------------- |
| Dashboard  | http://localhost:3000      | Web UI for managing products and FAQs |
| API        | http://localhost:8000      | REST API endpoints                    |
| API Docs   | http://localhost:8000/docs | Swagger documentation                 |
| Kafka UI   | http://localhost:8080      | Kafka monitoring                      |
| MongoDB UI | http://localhost:8081      | Database browser                      |
| HDFS UI    | http://localhost:9870      | Hadoop file browser                   |
| Spark UI   | http://localhost:8082      | Spark monitoring                      |

## 📖 Usage

### Adding a Product

1. Open the Dashboard at http://localhost:3000
2. Click "Add Product"
3. Enter product details:
   - **Name**: e.g., "Samsung Galaxy S24"
   - **Subreddits**: technology, gadgets, samsung, samsunggalaxy
   - **Keywords**: review, problem, help, question, experience

### Running the Pipeline

1. Select a product from the list
2. Click "Run Pipeline" (▶️) to:
   - Scrape Reddit for discussions
   - Store data in HDFS via Kafka
   - Generate FAQs using AI

### API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# List products
curl http://localhost:8000/api/products

# Add a product
curl -X POST http://localhost:8000/api/products \
  -H "Content-Type: application/json" \
  -d '{"name": "Samsung Galaxy S24", "subreddits": ["samsung", "gadgets"]}'

# Trigger scraping
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"product_id": "your_product_id"}'

# Generate FAQs
curl -X POST http://localhost:8000/api/generate-faqs \
  -H "Content-Type: application/json" \
  -d '{"product_id": "your_product_id"}'

# Get FAQs
curl http://localhost:8000/api/faqs/Samsung%20Galaxy%20S24
```

## 🏭 Services Architecture

### Go Reddit Scraper (`scrapers/reddit-scraper/`)

- OAuth2 authentication with Reddit API
- Rate-limited requests (configurable, default 100/min)
- Produces messages to Kafka
- HTTP endpoint for triggering scrapes

### Kafka Consumer (`services/kafka-consumer/`)

- Consumes raw social data from Kafka
- Batches messages for efficiency
- Stores data to HDFS in JSON format

### Spark Processor (`services/spark-processor/`)

- Cleans and normalizes text data
- Extracts questions from content
- Calculates relevance scores
- Clusters similar content
- Saves to MongoDB for FAQ generation

### FAQ Generator (`services/faq-generator/`)

- Supports Google Gemini API
- Ollama fallback for local LLM
- Generates structured FAQs with:
  - Questions and answers
  - Categories
  - Confidence scores
  - Source references
  - Keywords

### FastAPI Backend (`services/api/`)

- RESTful API for all operations
- Product management CRUD
- Pipeline orchestration
- FAQ retrieval

### React Dashboard (`dashboard/`)

- Next.js 14 with TypeScript
- Tailwind CSS styling
- Real-time status updates
- FAQ search and filtering

## 🔧 Configuration

### Scraper Configuration

| Variable                  | Default | Description                    |
| ------------------------- | ------- | ------------------------------ |
| `SCRAPE_RATE_LIMIT`       | 100     | Requests per minute            |
| `SCRAPE_INTERVAL_SECONDS` | 60      | Interval between scrape cycles |

### Kafka Configuration

| Variable               | Default         | Description            |
| ---------------------- | --------------- | ---------------------- |
| `KAFKA_TOPIC_RAW_DATA` | raw_social_data | Topic for scraped data |
| `KAFKA_CONSUMER_GROUP` | faq_processor   | Consumer group ID      |

### LLM Configuration

| Variable              | Default             | Description                         |
| --------------------- | ------------------- | ----------------------------------- |
| `GEMINI_API_KEY`      | -                   | Google Gemini API key               |
| `OLLAMA_HOST`         | http://ollama:11434 | Ollama server URL                   |
| `OLLAMA_MODEL`        | llama3.2            | Ollama model to use                 |
| `USE_OLLAMA_FALLBACK` | true                | Fall back to Ollama if Gemini fails |

## 📊 Monitoring

### Kafka

- Access Kafka UI at http://localhost:8080
- Monitor topics, consumer groups, and message flow

### HDFS

- Access HDFS UI at http://localhost:9870
- Browse stored data at `/data/raw/` and `/data/processed/`

### MongoDB

- Access Mongo Express at http://localhost:8081
- Credentials: admin / admin123
- Browse `faq_generation` database

## 🐛 Troubleshooting

### Services not starting

```bash
# Check logs
docker-compose logs -f [service_name]

# Restart specific service
docker-compose restart [service_name]
```

### Kafka connection issues

```bash
# Check Kafka health
docker-compose exec kafka kafka-broker-api-versions --bootstrap-server localhost:9092
```

### HDFS issues

```bash
# Check HDFS status
docker-compose exec namenode hdfs dfsadmin -report
```

### Ollama not working

```bash
# Pull the model first
ollama pull llama3.2

# Test Ollama
curl http://localhost:11434/api/tags
```

## 🚀 Scaling

### Horizontal Scaling

- Add more Kafka partitions for parallel processing
- Add Spark workers for distributed processing
- Deploy multiple API instances behind a load balancer

### Production Recommendations

- Use managed Kafka (Confluent Cloud, AWS MSK)
- Use managed MongoDB (Atlas)
- Use managed HDFS (AWS EMR, GCP Dataproc)
- Implement proper authentication and authorization
- Set up monitoring with Prometheus/Grafana

## 📁 Project Structure

```
faq_generation/
├── docker-compose.yml          # Production compose file
├── docker-compose.dev.yml      # Development compose file
├── .env.example                # Environment template
├── hadoop/
│   └── hadoop.env              # Hadoop configuration
├── scrapers/
│   └── reddit-scraper/         # Go Reddit scraper
│       ├── main.go
│       ├── go.mod
│       └── Dockerfile
├── services/
│   ├── kafka-consumer/         # Kafka to HDFS consumer
│   │   ├── consumer.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── spark-processor/        # Spark data processor
│   │   ├── processor.py
│   │   └── requirements.txt
│   ├── faq-generator/          # LLM FAQ generator
│   │   ├── generator.py
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   └── api/                    # FastAPI backend
│       ├── main.py
│       ├── requirements.txt
│       └── Dockerfile
└── dashboard/                  # React/Next.js frontend
    ├── app/
    ├── package.json
    └── Dockerfile
```

## 📄 License

MIT License

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request
