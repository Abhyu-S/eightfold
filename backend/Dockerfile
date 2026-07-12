FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if required for PyMuPDF / building packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend /app/backend/

# Set Python path so `backend.main` can be resolved
ENV PYTHONPATH=/app

# Expose backend port
EXPOSE 8000

# Start Uvicorn
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
