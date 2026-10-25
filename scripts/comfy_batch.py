#!/usr/bin/env python3
"""Batch-generate the Mulan boards with a remote ComfyUI (Qwen Image 2.1).

Usage:
  python3 scripts/comfy_batch.py --only ref_ --limit 4
  python3 scripts/comfy_batch.py --kind ref
  python3 scripts/comfy_batch.py --only char_
  python3 scripts/comfy_batch.py --only scene_
  python3 scripts/comfy_batch.py --only shot_
  python3 scripts/comfy_batch.py --only shot_ --start 1 --limit 10
  python3 scripts/comfy_batch.py --jobs scripts/jobs_16x9.json --only shot_01_16x9

Resumable: existing non-empty output files are skipped unless --force.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_PATH = os.path.join(ROOT, "scripts", "jobs.json")
MANIFEST = os.path.join(ROOT, "assets", "generated", "manifest.jsonl")


def build_workflow(job, uploaded):
    refs = job.get("refs") or []
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "qwen_image_2.1_int8_convrot.safetensors",
            "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_8b_int8_convrot.safetensors",
            "type": "qwen_image", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {
            "vae_name": "qwen_image_2.1_vae_bf16.safetensors"}},
    }
    te_inputs = {
        "clip": ["2", 0],
        "prompt": job["prompt"],
        "negative_prompt": job.get("negative", ""),
        "resolution": 1024,
    }
    if refs:
        te_inputs["vae"] = ["3", 0]
        for i, _ in enumerate(refs, start=1):
            te_inputs[f"images.image_{i}"] = [str(19 + i), 0]
    wf["4"] = {"class_type": "TextEncodeQwenImage21", "inputs": te_inputs}
    wf["5"] = {"class_type": "EmptySD3LatentImage", "inputs": {
        "width": job["width"], "height": job["height"], "batch_size": 1}}
    wf["6"] = {"class_type": "KSampler", "inputs": {
        "model": ["1", 0], "seed": job["seed"], "steps": job.get("steps", 25),
        "cfg": job.get("cfg", 2.0), "sampler_name": "euler", "scheduler": "simple",
        "positive": ["4", 0], "negative": ["4", 1], "latent_image": ["5", 0],
        "denoise": 1.0}}
    wf["7"] = {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}}
    wf["8"] = {"class_type": "SaveImage", "inputs": {
        "images": ["7", 0], "filename_prefix": "MULAN_" + job["id"]}}

    for i, path in enumerate(refs, start=1):
        name = upload_image(path)
        wf[str(19 + i)] = {"class_type": "LoadImage", "inputs": {"image": name}}
    return wf


_upload_cache = {}


def upload_image(path):
    path = os.path.join(ROOT, path) if not os.path.isabs(path) else path
    if path in _upload_cache:
        return _upload_cache[path]
    data = open(path, "rb").read()
    digest = hashlib.sha1(data).hexdigest()[:10]
    ext = os.path.splitext(path)[1]
    name = f"mulanref_{digest}{ext}"
    mime = "image/jpeg" if ext.lower() in (".jpg", ".jpeg") else "image/png"
    r = requests.post(
        ARGS.base + "/upload/image",
        files={"image": (name, data, mime)},
        data={"overwrite": "true", "type": "input"},
        timeout=60,
    )
    r.raise_for_status()
    info = r.json()
    uploaded_name = info["name"]
    if info.get("subfolder"):
        uploaded_name = info["subfolder"] + "/" + uploaded_name
    _upload_cache[path] = uploaded_name
    return uploaded_name


def submit(wf):
    r = requests.post(ARGS.base + "/prompt", json={"prompt": wf, "client_id": "mulan-batch"}, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"prompt HTTP {r.status_code}: {r.text[:2000]}")
    data = r.json()
    if data.get("node_errors"):
        raise RuntimeError("node_errors: " + json.dumps(data["node_errors"], ensure_ascii=False)[:3000])
    if not data.get("prompt_id"):
        raise RuntimeError("no prompt_id: " + r.text[:2000])
    return data["prompt_id"]


def wait(pid, timeout=900):
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{ARGS.base}/history/{pid}", timeout=30)
            r.raise_for_status()
            h = r.json()
        except Exception as e:
            print(f"    poll error: {e}", flush=True)
            time.sleep(3)
            continue
        if pid in h:
            item = h[pid]
            status = item.get("status", {})
            return item
        time.sleep(2)
    raise TimeoutError(f"timeout waiting for {pid}")


def download(item, target):
    outputs = item.get("outputs", {})
    images = []
    for node in outputs.values():
        images.extend(node.get("images", []))
    if not images:
        raise RuntimeError("no images in outputs: " + json.dumps(outputs, ensure_ascii=False)[:1000])
    im = images[0]
    params = {
        "filename": im["filename"],
        "subfolder": im.get("subfolder", ""),
        "type": im.get("type", "output"),
    }
    r = requests.get(ARGS.base + "/view", params=params, timeout=120)
    r.raise_for_status()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if target.lower().endswith((".jpg", ".jpeg")):
        from PIL import Image
        import io
        with Image.open(io.BytesIO(r.content)) as image:
            if image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[-1])
                image = background
            else:
                image = image.convert("RGB")
            image.save(target, "JPEG", quality=90, subsampling=0, optimize=True, progressive=True)
    else:
        with open(target, "wb") as f:
            f.write(r.content)
    return target


def log(record):
    manifest = getattr(ARGS, "manifest", MANIFEST)
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    with open(manifest, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    jobs = json.load(open(ARGS.jobs, encoding="utf-8"))
    only = [s.strip() for s in (ARGS.only or "").split(",") if s.strip()]
    if only:
        jobs = [j for j in jobs if any(j["id"].startswith(p) for p in only)]
    if ARGS.kind:
        jobs = [j for j in jobs if j["kind"] == ARGS.kind]
    if ARGS.start:
        def _num(j):
            m = re.search(r"(\d+)(?:_16x9)?$", j["id"])
            return int(m.group(1)) if m else 0
        jobs = [j for j in jobs if _num(j) >= ARGS.start]
    if ARGS.limit:
        jobs = jobs[: ARGS.limit]

    print(f"jobs: {len(jobs)}", flush=True)
    done = 0
    for idx, job in enumerate(jobs, 1):
        target = os.path.join(ROOT, job["file"])
        if os.path.exists(target) and os.path.getsize(target) > 10240 and not ARGS.force:
            print(f"[{idx}/{len(jobs)}] skip {job['id']} (exists)", flush=True)
            done += 1
            continue
        print(f"[{idx}/{len(jobs)}] {job['id']} {job['width']}x{job['height']} seed={job['seed']} refs={len(job.get('refs') or [])}", flush=True)
        t0 = time.time()
        try:
            wf = build_workflow(job, _upload_cache)
            pid = submit(wf)
            item = wait(pid)
            status = item.get("status", {}).get("status_str", "?")
            if status != "success":
                raise RuntimeError(f"status={status} " + json.dumps(item.get("status"), ensure_ascii=False)[:2000])
            download(item, target)
            dt = time.time() - t0
            print(f"    ok {dt:.1f}s -> {job['file']}", flush=True)
            log({"id": job["id"], "kind": job["kind"], "file": job["file"], "prompt_id": pid,
                 "seed": job["seed"], "width": job["width"], "height": job["height"],
                 "refs": job.get("refs") or [], "seconds": round(dt, 1), "status": "success"})
            done += 1
        except KeyboardInterrupt:
            print("interrupted", flush=True)
            break
        except Exception as e:
            print(f"    FAILED: {e}", flush=True)
            log({"id": job["id"], "kind": job["kind"], "file": job["file"],
                 "seed": job["seed"], "status": "failed", "error": str(e)[:2000]})
            if ARGS.stop_on_error:
                break
    print(f"finished {done}/{len(jobs)}", flush=True)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=os.environ.get("COMFY_BASE", "http://172.16.30.35:8188"))
    p.add_argument("--jobs", default=JOBS_PATH, help="job list JSON (default: scripts/jobs.json)")
    p.add_argument("--manifest", default=MANIFEST, help="manifest JSONL path")
    p.add_argument("--only", default="", help="comma separated id prefixes")
    p.add_argument("--kind", default="", choices=["", "ref", "sheet", "prop", "scene", "shot"])
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--stop-on-error", action="store_true")
    ARGS = p.parse_args()
    main()
