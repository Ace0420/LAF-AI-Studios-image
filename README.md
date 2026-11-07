# LAF Image Worker

Lean RunPod serverless worker for cover-art generation on LAF AI Studios
(Asa Hartz AI Services). It loads Z-Image-Turbo once per worker, makes an
image per request, uploads it to Cloudflare R2, and returns a link.

Sister repo to `LAF_AI_Studios` (the music worker). Same pattern, same R2
bucket, separate endpoint, so neither Dockerfile gets in the other's way.

> Status: spec. `handler.py` and `Dockerfile` are being written next.
> Update this section once the first build passes.

## What it does

- Model: Z-Image-Turbo (Apache 2.0), via `diffusers`.
- Turbo-distilled, so `guidance_scale` must stay at `0.0`. This is correct,
  not a bug. Do not "tune" it up the way ACE-Step's guidance was tuned.
- One image per request by default. Returns an R2 link, not a base64 blob.

## Request

```json
{
  "input": {
    "prompt": "A woman standing behind her partner in a wheelchair on a stormy cliff, dragons forming in the clouds, cinematic lighting",
    "title": "Like I Said Again",
    "width": 1024,
    "height": 1024,
    "infer_step": 8,
    "guidance_scale": 0.0,
    "seed": 42,
    "format": "jpg"
  }
}
```

Only `prompt` is required. Everything else has a default.

### Writing prompts (important)

Name who is who. "Two people, one in a wheelchair" gives an ambiguous
picture. "A woman standing behind her partner in a wheelchair" does not.
The future title + lyrics -> Claude -> visual prompt step must assign roles
explicitly whenever the lyrics imply a relationship.

## Response

```json
{
  "images": [{ "key": "covers/abc123.jpg", "url": "https://pub-xxxx.r2.dev/covers/abc123.jpg" }],
  "seconds": 0.0,
  "model": "Z-Image-Turbo"
}
```

If the R2 variables below are not all set, the worker falls back to
returning `image_b64` instead. A missing `url` in the response means R2 is
misconfigured.

## Environment variables (set on the RunPod endpoint)

| Variable | Value |
| --- | --- |
| `R2_ENDPOINT` | `https://<account-id>.r2.cloudflarestorage.com` (no bucket path) |
| `R2_BUCKET` | bucket name |
| `R2_ACCESS_KEY_ID` | R2 S3 access key ID |
| `R2_SECRET_ACCESS_KEY` | R2 S3 secret (exact name; `R2_SECRET_ACCESS` will not work) |
| `R2_PUBLIC_BASE` | public base URL for the bucket |
| `MODEL_ID` | Hugging Face id for Z-Image-Turbo |
| `HF_HOME` | `/runpod-volume/hf` when a network volume is attached |

Never commit these values to the repo.

## Deploy on RunPod

1. Serverless -> New Endpoint -> Import Git Repository -> this repo
   (Dockerfile at the root).
2. Queue endpoint, 1 GPU. Start with 24 GB+ cards; add 48 GB cards (A40,
   L40S) as fallback.
3. Set the environment variables above.
4. Container disk 40 GB. Max workers 1, idle timeout 60 s while testing.
5. Test in the Requests tab with `test_input.json`.

## Reliability rules (learned on the music worker)

- **At least two regions.** One region plus one network volume means a
  stock shortage leaves paying customers' jobs stuck in the queue. Either
  bake the model weights into the image so any region works, or keep a
  volume in two regions.
- A job stuck `IN_QUEUE` with zero workers means no GPU stock for the
  allowed types and regions, not a code problem.
- Rotate any API token that has been pasted into chat before real users.

## Cost

Billed per second of worker time. Turbo images should take a few seconds
warm. Measure on the real endpoint and record the number in the LAF plan
doc. Do not use a padded estimate.

## Files

- `Dockerfile` - build image (to be added)
- `handler.py` - RunPod handler (to be added)
- `test_input.json` - sample request (to be added)
- `README.md` - this file

