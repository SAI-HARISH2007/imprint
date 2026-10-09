FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch keeps the image small enough for a free Space
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service/ .

# Fetch the watermark model at build time so the first request does not depend on a download.
# HOME/XDG_CACHE_HOME/TORCH_HOME point inside /app so the cached weights are readable after we
# drop to the unprivileged appuser below.
ENV HOME=/app XDG_CACHE_HOME=/app/.cache TORCH_HOME=/app/.cache/torch HF_HOME=/app/.cache/huggingface
RUN python -c "from trustmark import TrustMark; TrustMark(verbose=False, model_type='Q', encoding_type=TrustMark.Encoding.BCH_5); print('model ready')"

RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

ENV PORT=7860
EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
