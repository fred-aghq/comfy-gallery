"""Extract ComfyUI metadata from image and video files."""

import json
import logging
import subprocess
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}


def extract_png_metadata(file_path: Path) -> tuple[dict | None, dict | None]:
    """Extract prompt and workflow JSON from PNG tEXt chunks."""
    try:
        with Image.open(file_path) as img:
            prompt_raw = img.info.get("prompt")
            workflow_raw = img.info.get("workflow")
            prompt = json.loads(prompt_raw) if prompt_raw else None
            workflow = json.loads(workflow_raw) if workflow_raw else None
            return prompt, workflow
    except Exception:
        logger.debug("Failed to extract PNG metadata from %s", file_path, exc_info=True)
        return None, None


def extract_jpeg_webp_metadata(file_path: Path) -> tuple[dict | None, dict | None]:
    """Check EXIF UserComment and sidecar JSON for metadata."""
    sidecar = file_path.with_suffix(".json")
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            return data.get("prompt"), data.get("workflow")
        except Exception:
            logger.debug("Failed to read sidecar JSON %s", sidecar, exc_info=True)

    try:
        with Image.open(file_path) as img:
            exif = img.getexif()
            user_comment = exif.get(0x9286)  # UserComment tag
            if user_comment:
                data = json.loads(user_comment)
                return data.get("prompt"), data.get("workflow")
    except Exception:
        logger.debug("Failed to extract EXIF metadata from %s", file_path, exc_info=True)

    return None, None


def extract_video_metadata(file_path: Path) -> tuple[dict | None, dict | None]:
    """Extract metadata from video files via ffprobe or sidecar JSON."""
    sidecar = file_path.with_suffix(".json")
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            return data.get("prompt"), data.get("workflow")
        except Exception:
            logger.debug("Failed to read sidecar JSON %s", sidecar, exc_info=True)

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            probe_data = json.loads(result.stdout)
            tags = probe_data.get("format", {}).get("tags", {})
            comment = tags.get("comment") or tags.get("description") or ""
            if comment:
                try:
                    data = json.loads(comment)
                    if isinstance(data, dict):
                        return data.get("prompt"), data.get("workflow")
                except json.JSONDecodeError:
                    pass
    except Exception:
        logger.debug("Failed to extract video metadata from %s", file_path, exc_info=True)

    return None, None


def extract_metadata(file_path: Path) -> tuple[dict | None, dict | None]:
    """Route to the correct extractor based on file extension."""
    ext = file_path.suffix.lower()
    if ext == ".png":
        return extract_png_metadata(file_path)
    elif ext in {".jpg", ".jpeg", ".webp"}:
        return extract_jpeg_webp_metadata(file_path)
    elif ext in VIDEO_EXTENSIONS:
        return extract_video_metadata(file_path)
    return None, None


def parse_searchable_fields(prompt_data: dict | None) -> dict:
    """Extract searchable fields from the ComfyUI prompt JSON.

    The prompt JSON is a dict of node_id -> node_config. We walk through
    all nodes looking for known class types and extract relevant values.
    """
    fields: dict = {
        "checkpoint_name": None,
        "positive_prompt": None,
        "negative_prompt": None,
        "sampler_name": None,
        "scheduler": None,
        "cfg_scale": None,
        "steps": None,
        "seed": None,
        "lora_names": [],
    }

    if not prompt_data or not isinstance(prompt_data, dict):
        return fields

    positive_prompts: list[str] = []
    negative_prompts: list[str] = []

    for _node_id, node in prompt_data.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})

        if class_type in ("CheckpointLoaderSimple", "CheckpointLoader", "UNETLoader"):
            ckpt = inputs.get("ckpt_name") or inputs.get("unet_name")
            if ckpt and not fields["checkpoint_name"]:
                fields["checkpoint_name"] = str(ckpt)

        if class_type in ("KSampler", "KSamplerAdvanced", "SamplerCustom"):
            if not fields["sampler_name"]:
                fields["sampler_name"] = inputs.get("sampler_name")
            if not fields["scheduler"]:
                fields["scheduler"] = inputs.get("scheduler")
            if fields["cfg_scale"] is None:
                cfg = inputs.get("cfg")
                if cfg is not None:
                    fields["cfg_scale"] = float(cfg)
            if fields["steps"] is None:
                steps = inputs.get("steps")
                if steps is not None:
                    fields["steps"] = int(steps)
            if fields["seed"] is None:
                seed = inputs.get("seed") or inputs.get("noise_seed")
                if seed is not None:
                    fields["seed"] = int(seed)

        if class_type in ("CLIPTextEncode",):
            text = inputs.get("text", "")
            if isinstance(text, str) and text.strip():
                positive_prompts.append(text.strip())

        if class_type in ("CLIPTextEncodeNegative", "ConditioningCombine"):
            text = inputs.get("text", "")
            if isinstance(text, str) and text.strip():
                negative_prompts.append(text.strip())

        if class_type in ("LoraLoader", "LoraLoaderModelOnly"):
            lora_name = inputs.get("lora_name")
            if lora_name:
                fields["lora_names"].append(str(lora_name))

    if positive_prompts:
        fields["positive_prompt"] = "\n---\n".join(positive_prompts)
    if negative_prompts:
        fields["negative_prompt"] = "\n---\n".join(negative_prompts)
    if not fields["lora_names"]:
        fields["lora_names"] = None

    return fields


def get_image_dimensions(file_path: Path) -> tuple[int | None, int | None]:
    """Get width and height of an image file."""
    try:
        with Image.open(file_path) as img:
            return img.width, img.height
    except Exception:
        return None, None


def get_video_dimensions(file_path: Path) -> tuple[int | None, int | None]:
    """Get width and height of a video file via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "v:0",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            if streams:
                return streams[0].get("width"), streams[0].get("height")
    except Exception:
        logger.debug("Failed to get video dimensions for %s", file_path, exc_info=True)
    return None, None
