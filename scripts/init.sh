#!/bin/bash

# Initialize FAQ Generation System
# This script sets up the initial configuration and sample data

set -e

echo "🚀 Initializing FAQ Generation System..."

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Check API health
echo "🔍 Checking API health..."
until curl -s http://localhost:8000/health > /dev/null 2>&1; do
    echo "   Waiting for API..."
    sleep 5
done
echo "✅ API is healthy"

# Create sample products
echo "📦 Creating sample products..."

# Samsung Galaxy S24
curl -s -X POST http://localhost:8000/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Samsung Galaxy S24",
    "description": "Samsung flagship smartphone 2024",
    "subreddits": ["samsung", "samsunggalaxy", "Android", "gadgets", "technology"],
    "keywords": ["review", "problem", "issue", "help", "question", "experience", "battery", "camera", "screen"],
    "category": "Smartphones"
  }' | python3 -m json.tool

echo ""

# Samsung Galaxy Watch
curl -s -X POST http://localhost:8000/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Samsung Galaxy Watch 6",
    "description": "Samsung smartwatch",
    "subreddits": ["GalaxyWatch", "samsung", "smartwatch", "wearables"],
    "keywords": ["review", "battery", "health", "fitness", "problem", "help"],
    "category": "Wearables"
  }' | python3 -m json.tool

echo ""

# Samsung TV
curl -s -X POST http://localhost:8000/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Samsung QLED TV",
    "description": "Samsung QLED Smart TV",
    "subreddits": ["4kTV", "hometheater", "samsung", "OLED_Gaming"],
    "keywords": ["review", "picture", "gaming", "HDR", "problem", "settings"],
    "category": "TVs"
  }' | python3 -m json.tool

echo ""
echo "✅ Sample products created!"
echo ""
echo "📊 System Stats:"
curl -s http://localhost:8000/api/stats | python3 -m json.tool

echo ""
echo "🎉 Initialization complete!"
echo ""
echo "Next steps:"
echo "  1. Open the dashboard: http://localhost:3000"
echo "  2. Select a product and click 'Run Pipeline'"
echo "  3. Wait for FAQs to be generated"
