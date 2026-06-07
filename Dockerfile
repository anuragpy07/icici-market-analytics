FROM python:3.11-slim

WORKDIR /app

# System deps for numpy/pandas compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create runtime directories
RUN mkdir -p data/cache data/universe logs

# Expose Streamlit default port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Default: run the full pipeline then launch the dashboard
CMD ["python", "run_dashboard.py", "--run-pipeline", "--limit", "20"]
