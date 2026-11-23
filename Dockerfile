FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/cache/huggingface \
    EARNINGS_CACHE_DIR=/cache/sec

WORKDIR /app

# CPU-only PyTorch keeps the image ~1.5 GB smaller than the default CUDA build.
# Build with --build-arg WITH_FINBERT=false for a lightweight dictionary-only image.
ARG WITH_FINBERT=true
COPY requirements.txt requirements-finbert.txt ./
RUN pip install -r requirements.txt && \
    if [ "$WITH_FINBERT" = "true" ]; then \
      pip install torch --index-url https://download.pytorch.org/whl/cpu && \
      pip install "transformers>=4.40"; \
    fi

COPY . .
RUN useradd --create-home appuser && mkdir -p /cache && chown -R appuser /cache /app
USER appuser

EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
