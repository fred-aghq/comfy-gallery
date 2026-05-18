"""Extract ComfyUI metadata from image and video files."""

import json
import logging
import math
import subprocess
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}


def _sanitize_json(obj: object) -> object:
    """Recursively replace NaN/Infinity floats with None for JSONB compatibility.

    ComfyUI workflows may contain non-standard JSON values (NaN, Infinity)
    which Python's json.loads accepts but PostgreSQL JSONB rejects.
    """
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json(item) for item in obj]
    return obj


def extract_png_metadata(file_path: Path) -> tuple[dict | None, dict | None]:
    """Extract prompt and workflow JSON from PNG tEXt chunks."""
    try:
        with Image.open(file_path) as img:
            prompt_raw = img.info.get("prompt")
            workflow_raw = img.info.get("workflow")
            prompt = json.loads(prompt_raw) if prompt_raw else None
            workflow = json.loads(workflow_raw) if workflow_raw else None
            return _sanitize_json(prompt), _sanitize_json(workflow)
    except Exception:
        logger.debug("Failed to extract PNG metadata from %s", file_path, exc_info=True)
        return None, None


def extract_jpeg_webp_metadata(file_path: Path) -> tuple[dict | None, dict | None]:
    """Check EXIF UserComment and sidecar JSON for metadata."""
    sidecar = file_path.with_suffix(".json")
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            return _sanitize_json(data.get("prompt")), _sanitize_json(data.get("workflow"))
        except Exception:
            logger.debug("Failed to read sidecar JSON %s", sidecar, exc_info=True)

    try:
        with Image.open(file_path) as img:
            exif = img.getexif()
            user_comment = exif.get(0x9286)  # UserComment tag
            if user_comment:
                data = json.loads(user_comment)
                return (
                    _sanitize_json(data.get("prompt")),
                    _sanitize_json(data.get("workflow")),
                )
    except Exception:
        logger.debug("Failed to extract EXIF metadata from %s", file_path, exc_info=True)

    return None, None


def extract_video_metadata(file_path: Path) -> tuple[dict | None, dict | None]:
    """Extract metadata from video files via ffprobe or sidecar JSON."""
    sidecar = file_path.with_suffix(".json")
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            return _sanitize_json(data.get("prompt")), _sanitize_json(data.get("workflow"))
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
                        return (
                            _sanitize_json(data.get("prompt")),
                            _sanitize_json(data.get("workflow")),
                        )
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


def _resolve_input(value, prompt_data: dict) -> object:
    """Resolve a node input value, following node references if needed.

    In ComfyUI prompt JSON, inputs that come from other nodes are stored
    as [node_id, output_index] lists. This helper follows one level of
    reference to try to retrieve the underlying scalar value.
    """
    if not isinstance(value, list) or len(value) != 2:
        return value
    ref_node_id, _output_index = value
    ref_node = prompt_data.get(str(ref_node_id), {})
    ref_inputs = ref_node.get("inputs", {}) if isinstance(ref_node, dict) else {}
    for key in ("seed", "noise_seed", "value", "Value", "SEED"):
        v = ref_inputs.get(key)
        if v is not None and not isinstance(v, list):
            return v
    return None


def _resolve_text(value: object, prompt_data: dict, depth: int = 0) -> str | None:
    """Resolve a text input value, following node references recursively.

    When a CLIPTextEncode node receives its text from a String/PrimitiveNode
    or similar text-producing node, the input is stored as [node_id, output_index].
    This helper traverses the reference chain to find the actual text string.
    """
    if depth > 10:
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, list) or len(value) != 2:
        return None
    ref_node_id = str(value[0])
    ref_node = prompt_data.get(ref_node_id, {})
    if not isinstance(ref_node, dict):
        return None
    inputs = ref_node.get("inputs", {})
    if not isinstance(inputs, dict):
        return None
    # Try common text-holding keys used by String/Primitive/ShowText nodes
    for key in ("string", "text", "value", "STRING", "TEXT", "str"):
        v = inputs.get(key)
        if v is not None:
            resolved = _resolve_text(v, prompt_data, depth + 1)
            if resolved is not None:
                return resolved
    return None


def _collect_conditioning_sources(
    node_ref: object, prompt_data: dict, visited: set | None = None
) -> set:
    """Trace conditioning connections to find all CLIPTextEncode source node IDs.

    Starting from a KSampler's positive/negative input reference, walks backwards
    through conditioning combination/modification nodes to find all originating
    CLIPTextEncode nodes.
    """
    if visited is None:
        visited = set()
    if not isinstance(node_ref, list) or len(node_ref) != 2:
        return set()
    node_id = str(node_ref[0])
    if node_id in visited:
        return set()
    visited.add(node_id)
    node = prompt_data.get(node_id, {})
    if not isinstance(node, dict):
        return set()
    class_type = node.get("class_type", "")
    if "CLIPTextEncode" in class_type:
        return {node_id}
    # Trace through conditioning manipulation nodes
    result: set = set()
    inputs = node.get("inputs", {})
    if isinstance(inputs, dict):
        for v in inputs.values():
            if isinstance(v, list) and len(v) == 2:
                result.update(
                    _collect_conditioning_sources(v, prompt_data, visited)
                )
    return result


def _safe_int(value, prompt_data: dict) -> int | None:
    """Convert a node input to int, resolving references and ignoring bad types."""
    resolved = _resolve_input(value, prompt_data)
    if resolved is None:
        return None
    try:
        return int(resolved)
    except (TypeError, ValueError):
        return None


def _safe_float(value, prompt_data: dict) -> float | None:
    """Convert a node input to float, resolving references and ignoring bad types."""
    resolved = _resolve_input(value, prompt_data)
    if resolved is None:
        return None
    try:
        return float(resolved)
    except (TypeError, ValueError):
        return None


def parse_searchable_fields(prompt_data: dict | None) -> dict:
    """Extract searchable fields from the ComfyUI prompt JSON.

    The prompt JSON is a dict of node_id -> node_config. We walk through
    all nodes looking for known class types and extract relevant values.

    Prompt classification uses KSampler positive/negative connections to
    determine which CLIPTextEncode nodes produce positive vs negative prompts.
    When text inputs are references to other nodes (e.g. String nodes), the
    references are resolved recursively.
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

    # --- Phase 1: Classify CLIPTextEncode nodes via KSampler connections ---
    positive_node_ids: set = set()
    negative_node_ids: set = set()
    sampler_class_types = ("KSampler", "KSamplerAdvanced", "SamplerCustom")

    for _node_id, node in prompt_data.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        if class_type not in sampler_class_types:
            continue
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue
        pos_ref = inputs.get("positive")
        neg_ref = inputs.get("negative")
        if pos_ref is not None:
            positive_node_ids.update(
                _collect_conditioning_sources(pos_ref, prompt_data)
            )
        if neg_ref is not None:
            negative_node_ids.update(
                _collect_conditioning_sources(neg_ref, prompt_data)
            )

    has_sampler_connections = bool(positive_node_ids or negative_node_ids)

    # --- Phase 2: Extract fields from all nodes ---
    positive_prompts: list[str] = []
    negative_prompts: list[str] = []

    for node_id, node in prompt_data.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if not isinstance(inputs, dict):
            continue

        if class_type in ("CheckpointLoaderSimple", "CheckpointLoader", "UNETLoader"):
            ckpt = inputs.get("ckpt_name") or inputs.get("unet_name")
            if ckpt and not fields["checkpoint_name"]:
                fields["checkpoint_name"] = str(ckpt)

        if class_type in sampler_class_types:
            if not fields["sampler_name"]:
                fields["sampler_name"] = inputs.get("sampler_name")
            if not fields["scheduler"]:
                fields["scheduler"] = inputs.get("scheduler")
            if fields["cfg_scale"] is None:
                cfg = inputs.get("cfg")
                if cfg is not None:
                    fields["cfg_scale"] = _safe_float(cfg, prompt_data)
            if fields["steps"] is None:
                steps = inputs.get("steps")
                if steps is not None:
                    fields["steps"] = _safe_int(steps, prompt_data)
            if fields["seed"] is None:
                seed = inputs.get("seed") or inputs.get("noise_seed")
                if seed is not None:
                    fields["seed"] = _safe_int(seed, prompt_data)

        if "CLIPTextEncode" in class_type:
            text_value = inputs.get("text", "")
            text = _resolve_text(text_value, prompt_data)
            if text and text.strip():
                text = text.strip()
                if has_sampler_connections:
                    if node_id in positive_node_ids:
                        positive_prompts.append(text)
                    if node_id in negative_node_ids:
                        negative_prompts.append(text)
                    # Nodes not connected to any sampler are skipped
                else:
                    # Fallback: no KSampler connections found, use class_type hint
                    if "Negative" in class_type:
                        negative_prompts.append(text)
                    else:
                        positive_prompts.append(text)

        if class_type in ("LoraLoader", "LoraLoaderModelOnly"):
            lora_name = inputs.get("lora_name")
            if lora_name:
                fields["lora_names"].append(str(lora_name))

    # Deduplicate prompts while preserving order
    seen_pos: set = set()
    unique_positive: list[str] = []
    for p in positive_prompts:
        if p not in seen_pos:
            seen_pos.add(p)
            unique_positive.append(p)

    seen_neg: set = set()
    unique_negative: list[str] = []
    for p in negative_prompts:
        if p not in seen_neg:
            seen_neg.add(p)
            unique_negative.append(p)

    if unique_positive:
        fields["positive_prompt"] = "\n---\n".join(unique_positive)
    if unique_negative:
        fields["negative_prompt"] = "\n---\n".join(unique_negative)
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
