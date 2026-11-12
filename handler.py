"""
LAF AI Studios - Z-Image-Turbo cover-art worker (RunPod serverless).

Loads the model once per worker, makes an image per request, uploads it to
Cloudflare R2 and returns a link. If R2 variables are not all set, the image
is returned as base64 instead.

Request (body {"input": {...}}):
  prompt          str    required. Name who is who in the scene.
  title           str    optional, only used in the log line
  width, height   int    256-2048, multiples of 16        (default 1024 x 1024)
  infer_step      int    1-20; Turbo is distilled for 8-9 (default 9 = 8 forwards)
  guidance_scale  float  must stay 0.0 for Turbo          (default 0.0)
  seed            int    -1 = random                      (default -1)
  format          str    "jpg" | "png" | "webp"           (default "jpg")

Response:
  {"images": [{"seed": 42, "format": "jpg", "key": "...", "url": "..."} or {"image_b64": "..."}],
   "seconds": 3.2, "model": "Tongyi-MAI/Z-Image-Turbo"}
"""

import base64
import os
import time
import uuid

import runpod

MODEL_ID = os.environ.get("MODEL_ID", "Tongyi-MAI/Z-Image-Turbo")
MAX_SIDE = int(os.environ.get("MAX_SIDE", "2048"))

R2_ENDPOINT = os.environ.get("R2_ENDPOINT")
R2_BUCKET = os.environ.get("R2_BUCKET")
R2_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID")
R2_SECRET = os.environ.get("R2_SECRET_ACCESS_KEY")
R2_PUBLIC_BASE = os.environ.get("R2_PUBLIC_BASE")

# Use the network volume for model downloads when one is attached.
if os.path.isdir("/runpod-volume") and "HF_HOME" not in os.environ:
    os.environ["HF_HOME"] = "/runpod-volume/hf"

OUT_DIR = "/tmp/laf_img"
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------- load once per worker
t0 = time.time()
print("[LAF-IMG] starting", flush=True)
try:
    import torch                          # noqa: E402
    from diffusers import ZImagePipeline  # noqa: E402
    import diffusers                      # noqa: E402
    print(f"[LAF-IMG] torch {torch.__version__} cuda_build={torch.version.cuda} "
          f"cuda_available={torch.cuda.is_available()} diffusers {diffusers.__version__}", flush=True)
    PIPE = ZImagePipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16)
    PIPE.to("cuda")
except Exception:
    import traceback
    traceback.print_exc()
    print("[LAF-IMG] startup failed (see traceback above)", flush=True)
    time.sleep(5)
    raise
print(f"[LAF-IMG] model ready in {time.time() - t0:.1f}s ({MODEL_ID})", flush=True)


def _r2_client():
    if not (R2_ENDPOINT and R2_BUCKET and R2_KEY_ID and R2_SECRET):
        return None
    import boto3
    return boto3.client("s3", endpoint_url=R2_ENDPOINT,
                        aws_access_key_id=R2_KEY_ID, aws_secret_access_key=R2_SECRET,
                        region_name="auto")


R2 = _r2_client()
MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
PIL_FMT = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}


def _deliver(path, fmt):
    if R2:
        key = f"covers/{uuid.uuid4().hex}.{fmt}"
        R2.upload_file(path, R2_BUCKET, key, ExtraArgs={"ContentType": MIME[fmt]})
        return {"key": key, "url": f"{R2_PUBLIC_BASE.rstrip('/')}/{key}" if R2_PUBLIC_BASE else None}
    with open(path, "rb") as f:
        return {"image_b64": base64.b64encode(f.read()).decode()}


def _side(value, name):
    v = int(value)
    if v < 256 or v > MAX_SIDE or v % 16:
        raise ValueError(f"{name} must be 256-{MAX_SIDE} and a multiple of 16")
    return v


def handler(job):
    inp = job.get("input") or {}
    prompt = (inp.get("prompt") or "").strip()
    if not prompt:
        return {"error": "prompt is required"}
    fmt = inp.get("format", "jpg")
    if fmt not in MIME:
        return {"error": "format must be jpg, png or webp"}
    try:
        width = _side(inp.get("width", 1024), "width")
        height = _side(inp.get("height", 1024), "height")
    except ValueError as e:
        return {"error": str(e)}

    steps = max(1, min(int(inp.get("infer_step", 9)), 20))
    guidance = float(inp.get("guidance_scale", 0.0))
    seed = int(inp.get("seed", -1))
    if seed < 0:
        seed = int.from_bytes(os.urandom(4), "big")

    start = time.time()
    path = os.path.join(OUT_DIR, f"{uuid.uuid4().hex}.{fmt}")
    try:
        image = PIPE(
            prompt=prompt, height=height, width=width,
            num_inference_steps=steps, guidance_scale=guidance,
            generator=torch.Generator("cuda").manual_seed(seed),
        ).images[0]
        image.convert("RGB").save(path, PIL_FMT[fmt], quality=92) if fmt != "png" else image.save(path, "PNG")
        item = {"seed": seed, "format": fmt}
        item.update(_deliver(path, fmt))
        print(f"[LAF-IMG] '{inp.get('title', '')}' {width}x{height} {steps} steps in {time.time() - start:.2f}s", flush=True)
        return {"images": [item], "seconds": round(time.time() - start, 2), "model": MODEL_ID}
    finally:
        if os.path.exists(path):
            os.remove(path)


runpod.serverless.start({"handler": handler})
