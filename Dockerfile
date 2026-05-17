FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for curl-cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir fastapi uvicorn apscheduler

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
