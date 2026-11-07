# LAF AI Studios - Z-Image-Turbo cover-art worker
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    HF_HUB_ENABLE_HF_TRANSFER=1

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir torch \
    && pip install --no-cache-dir diffusers transformers accelerate safetensors \
       sentencepiece pillow runpod boto3 huggingface_hub hf_transfer

COPY handler.py /app/handler.py

# Two-region option: bake the weights into the image so ANY region works
# (adds ~12 GB to the image; uncomment, rebuild, and the network volume is optional).
# RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('Tongyi-MAI/Z-Image-Turbo')"

CMD ["python", "-u", "/app/handler.py"]
