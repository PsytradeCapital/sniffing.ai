FROM python:3.12-slim

# Security: run as non-root user
RUN useradd -m -u 1000 botuser

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create log directory and set permissions
RUN mkdir -p data/logs && chown -R botuser:botuser /app

USER botuser

# Unbuffered output so logs appear immediately
ENV PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "-u", "main.py"]
