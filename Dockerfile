FROM python:3.12-slim

WORKDIR /app
ENV PIP_DEFAULT_TIMEOUT=120

# Install system dependencies for curl-cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --no-cache-dir "setuptools>=68" wheel \
    && pip install --no-cache-dir --no-build-isolation .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
