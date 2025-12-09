FROM python:3.11-slim

WORKDIR /app

# Install API requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install FAQ generator requirements
RUN pip install --no-cache-dir httpx pymongo pydantic

COPY . .

# Create services directory for FAQ generator (will be mounted via volume)
RUN mkdir -p /app/services/faq-generator

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
