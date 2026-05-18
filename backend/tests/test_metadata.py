"""Tests for app.services.metadata — extraction and parsing of ComfyUI metadata."""

import json
from unittest.mock import patch

from app.services.metadata import (
    _collect_conditioning_sources,
    _resolve_text,
    _sanitize_json,
    extract_jpeg_webp_metadata,
    extract_metadata,
    extract_png_metadata,
    extract_video_metadata,
    get_image_dimensions,
    get_video_dimensions,
    parse_searchable_fields,
)

# ---------------------------------------------------------------------------
# extract_png_metadata
# ---------------------------------------------------------------------------

class TestExtractPngMetadata:
    def test_valid_comfyui_png(self, sample_png_path):
        prompt, workflow = extract_png_metadata(sample_png_path)
        assert prompt is not None
        assert isinstance(prompt, dict)
        assert workflow is not None
        assert isinstance(workflow, dict)
        # Verify specific known values from the fixture
        assert "4" in prompt
        assert prompt["4"]["class_type"] == "CheckpointLoaderSimple"

    def test_png_no_metadata(self, tmp_path):
        from PIL import Image

        plain = tmp_path / "plain.png"
        Image.new("RGB", (10, 10), "red").save(plain)
        prompt, workflow = extract_png_metadata(plain)
        assert prompt is None
        assert workflow is None

    def test_png_malformed_json(self, tmp_path):
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo

        info = PngInfo()
        info.add_text("prompt", "{invalid json")
        info.add_text("workflow", "also bad")
        bad = tmp_path / "bad.png"
        Image.new("RGB", (10, 10)).save(bad, pnginfo=info)
        prompt, workflow = extract_png_metadata(bad)
        assert prompt is None
        assert workflow is None

    def test_png_prompt_only(self, tmp_path):
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo

        info = PngInfo()
        info.add_text("prompt", '{"1": {"class_type": "Test"}}')
        img_path = tmp_path / "prompt_only.png"
        Image.new("RGB", (10, 10)).save(img_path, pnginfo=info)
        prompt, workflow = extract_png_metadata(img_path)
        assert prompt == {"1": {"class_type": "Test"}}
        assert workflow is None

    def test_corrupt_file(self, tmp_path):
        corrupt = tmp_path / "corrupt.png"
        corrupt.write_bytes(b"not a real png")
        prompt, workflow = extract_png_metadata(corrupt)
        assert prompt is None
        assert workflow is None


# ---------------------------------------------------------------------------
# extract_jpeg_webp_metadata
# ---------------------------------------------------------------------------

class TestExtractJpegWebpMetadata:
    def test_sidecar_json(self, tmp_path):
        from PIL import Image

        img_path = tmp_path / "image.jpg"
        Image.new("RGB", (10, 10)).save(img_path)

        sidecar = tmp_path / "image.json"
        sidecar.write_text(json.dumps({
            "prompt": {"1": {"class_type": "Test"}},
            "workflow": {"nodes": []},
        }))

        prompt, workflow = extract_jpeg_webp_metadata(img_path)
        assert prompt == {"1": {"class_type": "Test"}}
        assert workflow == {"nodes": []}

    def test_no_metadata(self, tmp_path):
        from PIL import Image

        img_path = tmp_path / "plain.jpg"
        Image.new("RGB", (10, 10)).save(img_path)
        prompt, workflow = extract_jpeg_webp_metadata(img_path)
        assert prompt is None
        assert workflow is None

    def test_invalid_sidecar_json(self, tmp_path):
        from PIL import Image

        img_path = tmp_path / "image.jpg"
        Image.new("RGB", (10, 10)).save(img_path)
        sidecar = tmp_path / "image.json"
        sidecar.write_text("not valid json")
        prompt, workflow = extract_jpeg_webp_metadata(img_path)
        assert prompt is None
        assert workflow is None

    def test_webp_with_sidecar(self, tmp_path):
        from PIL import Image

        img_path = tmp_path / "image.webp"
        Image.new("RGB", (10, 10)).save(img_path)
        sidecar = tmp_path / "image.json"
        sidecar.write_text(json.dumps({
            "prompt": {"1": {"class_type": "WebpTest"}},
            "workflow": None,
        }))
        prompt, workflow = extract_jpeg_webp_metadata(img_path)
        assert prompt == {"1": {"class_type": "WebpTest"}}


# ---------------------------------------------------------------------------
# extract_video_metadata
# ---------------------------------------------------------------------------

class TestExtractVideoMetadata:
    def test_sidecar_json(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 100)
        sidecar = tmp_path / "video.json"
        sidecar.write_text(json.dumps({
            "prompt": {"1": {"class_type": "VideoTest"}},
            "workflow": {"id": "abc"},
        }))
        prompt, workflow = extract_video_metadata(video)
        assert prompt == {"1": {"class_type": "VideoTest"}}
        assert workflow == {"id": "abc"}

    def test_no_metadata(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 100)
        # Mock ffprobe returning nothing useful
        with patch("app.services.metadata.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps({"format": {"tags": {}}})
            prompt, workflow = extract_video_metadata(video)
        assert prompt is None
        assert workflow is None

    def test_ffprobe_timeout(self, tmp_path):
        import subprocess

        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 100)
        timeout_err = subprocess.TimeoutExpired("ffprobe", 30)
        with patch("app.services.metadata.subprocess.run", side_effect=timeout_err):
            prompt, workflow = extract_video_metadata(video)
        assert prompt is None
        assert workflow is None

    def test_ffprobe_comment_tag(self, tmp_path):
        video = tmp_path / "video.mp4"
        video.write_bytes(b"\x00" * 100)
        metadata = json.dumps({
            "prompt": {"1": {"class_type": "FromFFprobe"}},
            "workflow": None,
        })
        with patch("app.services.metadata.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps({
                "format": {"tags": {"comment": metadata}}
            })
            prompt, workflow = extract_video_metadata(video)
        assert prompt == {"1": {"class_type": "FromFFprobe"}}


# ---------------------------------------------------------------------------
# extract_metadata (router)
# ---------------------------------------------------------------------------

class TestExtractMetadata:
    def test_routes_png(self, sample_png_path):
        prompt, workflow = extract_metadata(sample_png_path)
        assert prompt is not None
        assert "4" in prompt

    def test_routes_jpg(self, tmp_path):
        from PIL import Image

        img_path = tmp_path / "test.jpg"
        Image.new("RGB", (10, 10)).save(img_path)
        prompt, workflow = extract_metadata(img_path)
        assert prompt is None
        assert workflow is None

    def test_routes_video(self, tmp_path):
        video = tmp_path / "test.mp4"
        video.write_bytes(b"\x00" * 100)
        sidecar = tmp_path / "test.json"
        sidecar.write_text(json.dumps({"prompt": {"1": {}}, "workflow": None}))
        prompt, workflow = extract_metadata(video)
        assert prompt == {"1": {}}

    def test_unknown_extension(self, tmp_path):
        f = tmp_path / "file.xyz"
        f.write_bytes(b"data")
        prompt, workflow = extract_metadata(f)
        assert prompt is None
        assert workflow is None


# ---------------------------------------------------------------------------
# parse_searchable_fields
# ---------------------------------------------------------------------------

class TestParseSearchableFields:
    def test_none_input(self):
        fields = parse_searchable_fields(None)
        assert fields["checkpoint_name"] is None
        assert fields["positive_prompt"] is None
        assert fields["seed"] is None
        assert fields["lora_names"] == []

    def test_empty_dict(self):
        fields = parse_searchable_fields({})
        assert fields["checkpoint_name"] is None
        assert fields["lora_names"] == []  # {} is falsy, returns early

    def test_non_dict_input(self):
        fields = parse_searchable_fields("not a dict")
        assert fields["checkpoint_name"] is None

    def test_full_comfyui_prompt(self, sample_png_path):
        """Test with the actual ComfyUI prompt from the fixture image."""
        from PIL import Image

        with Image.open(sample_png_path) as img:
            prompt = json.loads(img.info["prompt"])
        fields = parse_searchable_fields(prompt)
        assert fields["checkpoint_name"] == "safe/SDXL/natvisNaturalVision_v10.safetensors"
        assert fields["sampler_name"] == "euler"
        assert fields["scheduler"] == "normal"
        assert fields["cfg_scale"] == 8.0
        assert fields["steps"] == 25
        assert fields["seed"] == 721897303308196
        assert fields["positive_prompt"] is not None
        assert "evening sunset scenery" in fields["positive_prompt"]
        # Negative prompt is now correctly classified via KSampler connections
        assert fields["negative_prompt"] is not None
        assert "text, watermark" in fields["negative_prompt"]
        # Duplicate prompts from base+refiner passes are deduplicated
        assert fields["positive_prompt"].count("evening sunset scenery") == 1

    def test_multiple_clip_text_nodes(self):
        """Without KSampler connections, CLIPTextEncode nodes use fallback (positive)."""
        prompt = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt one"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt two"}},
        }
        fields = parse_searchable_fields(prompt)
        assert "prompt one" in fields["positive_prompt"]
        assert "prompt two" in fields["positive_prompt"]
        assert "\n---\n" in fields["positive_prompt"]

    def test_lora_loader_nodes(self):
        prompt = {
            "1": {"class_type": "LoraLoader", "inputs": {"lora_name": "lora_a.safetensors"}},
            "2": {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {"lora_name": "lora_b.safetensors"},
            },
        }
        fields = parse_searchable_fields(prompt)
        assert fields["lora_names"] == ["lora_a.safetensors", "lora_b.safetensors"]

    def test_non_dict_node_values(self):
        prompt = {"1": "not_a_dict", "2": 42, "3": None}
        fields = parse_searchable_fields(prompt)
        assert fields["checkpoint_name"] is None

    def test_unet_loader(self):
        prompt = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "my_unet.safetensors"}},
        }
        fields = parse_searchable_fields(prompt)
        assert fields["checkpoint_name"] == "my_unet.safetensors"

    def test_ksampler_with_noise_seed(self):
        prompt = {
            "1": {
                "class_type": "KSamplerAdvanced",
                "inputs": {
                    "noise_seed": 999888777666,
                    "steps": 30,
                    "cfg": 7.5,
                    "sampler_name": "dpmpp_2m",
                    "scheduler": "karras",
                },
            },
        }
        fields = parse_searchable_fields(prompt)
        assert fields["seed"] == 999888777666
        assert fields["steps"] == 30
        assert fields["cfg_scale"] == 7.5
        assert fields["sampler_name"] == "dpmpp_2m"
        assert fields["scheduler"] == "karras"

    def test_ksampler_with_seed_field(self):
        prompt = {
            "1": {
                "class_type": "KSampler",
                "inputs": {"seed": 12345, "steps": 20, "cfg": 7.0,
                           "sampler_name": "euler_ancestral", "scheduler": "normal"},
            },
        }
        fields = parse_searchable_fields(prompt)
        assert fields["seed"] == 12345

    def test_negative_prompt_nodes(self):
        """CLIPTextEncodeNegative class_type fallback still works without KSampler."""
        prompt = {
            "1": {"class_type": "CLIPTextEncodeNegative", "inputs": {"text": "bad quality"}},
        }
        fields = parse_searchable_fields(prompt)
        assert fields["negative_prompt"] == "bad quality"

    def test_ksampler_positive_negative_classification(self):
        """CLIPTextEncode nodes are classified via KSampler connections."""
        prompt = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "beautiful scenery"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "ugly, blurry"}},
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 42, "steps": 20, "cfg": 7.0,
                    "sampler_name": "euler", "scheduler": "normal",
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                },
            },
        }
        fields = parse_searchable_fields(prompt)
        assert fields["positive_prompt"] == "beautiful scenery"
        assert fields["negative_prompt"] == "ugly, blurry"

    def test_text_from_string_node(self):
        """CLIPTextEncode text input referencing a String node is resolved."""
        prompt = {
            "1": {"class_type": "String", "inputs": {"string": "a cat sitting on a mat"}},
            "2": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": ["1", 0], "clip": ["4", 1]},
            },
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad quality"}},
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "model.safetensors"},
            },
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 1, "steps": 20, "cfg": 7.0,
                    "sampler_name": "euler", "scheduler": "normal",
                    "positive": ["2", 0],
                    "negative": ["3", 0],
                },
            },
        }
        fields = parse_searchable_fields(prompt)
        assert fields["positive_prompt"] == "a cat sitting on a mat"
        assert fields["negative_prompt"] == "bad quality"

    def test_text_from_chained_string_nodes(self):
        """References through multiple nodes are resolved recursively."""
        prompt = {
            "1": {"class_type": "StringLiteral", "inputs": {"value": "deep prompt"}},
            "2": {"class_type": "StringPassthrough", "inputs": {"string": ["1", 0]}},
            "3": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": ["2", 0], "clip": ["5", 1]},
            },
            "4": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 1, "steps": 20, "cfg": 7.0,
                    "sampler_name": "euler", "scheduler": "normal",
                    "positive": ["3", 0],
                    "negative": ["3", 0],
                },
            },
            "5": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "m.safetensors"}},
        }
        fields = parse_searchable_fields(prompt)
        assert fields["positive_prompt"] == "deep prompt"

    def test_duplicate_prompts_deduplicated(self):
        """Identical prompts from multiple KSampler passes are deduplicated."""
        prompt = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "same prompt"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "same prompt"}},
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 1, "steps": 20, "cfg": 7.0,
                    "sampler_name": "euler", "scheduler": "normal",
                    "positive": ["1", 0],
                    "negative": ["2", 0],
                },
            },
        }
        fields = parse_searchable_fields(prompt)
        # "same prompt" appears both as positive and negative
        assert fields["positive_prompt"] == "same prompt"
        assert fields["negative_prompt"] == "same prompt"

    def test_conditioning_combine_traced(self):
        """Conditioning nodes between CLIPTextEncode and KSampler are traversed."""
        prompt = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt A"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "prompt B"}},
            "3": {
                "class_type": "ConditioningCombine",
                "inputs": {"conditioning_1": ["1", 0], "conditioning_2": ["2", 0]},
            },
            "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "bad"}},
            "5": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": 1, "steps": 20, "cfg": 7.0,
                    "sampler_name": "euler", "scheduler": "normal",
                    "positive": ["3", 0],
                    "negative": ["4", 0],
                },
            },
        }
        fields = parse_searchable_fields(prompt)
        assert "prompt A" in fields["positive_prompt"]
        assert "prompt B" in fields["positive_prompt"]
        assert fields["negative_prompt"] == "bad"

    def test_empty_text_skipped(self):
        prompt = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "  "}},
        }
        fields = parse_searchable_fields(prompt)
        assert fields["positive_prompt"] is None


# ---------------------------------------------------------------------------
# _resolve_text
# ---------------------------------------------------------------------------

class TestResolveText:
    def test_literal_string(self):
        assert _resolve_text("hello", {}) == "hello"

    def test_none_returns_none(self):
        assert _resolve_text(None, {}) is None

    def test_empty_string(self):
        assert _resolve_text("", {}) == ""

    def test_reference_to_string_node(self):
        prompt = {
            "1": {"class_type": "String", "inputs": {"string": "resolved text"}},
        }
        assert _resolve_text(["1", 0], prompt) == "resolved text"

    def test_reference_to_text_key(self):
        prompt = {
            "1": {"class_type": "Note", "inputs": {"text": "note content"}},
        }
        assert _resolve_text(["1", 0], prompt) == "note content"

    def test_reference_to_value_key(self):
        prompt = {
            "1": {"class_type": "Primitive", "inputs": {"value": "prim value"}},
        }
        assert _resolve_text(["1", 0], prompt) == "prim value"

    def test_chained_references(self):
        prompt = {
            "1": {"class_type": "StringLiteral", "inputs": {"string": "final"}},
            "2": {"class_type": "Reroute", "inputs": {"string": ["1", 0]}},
        }
        assert _resolve_text(["2", 0], prompt) == "final"

    def test_max_depth_guard(self):
        # Create a circular reference
        prompt = {
            "1": {"class_type": "A", "inputs": {"string": ["2", 0]}},
            "2": {"class_type": "B", "inputs": {"string": ["1", 0]}},
        }
        assert _resolve_text(["1", 0], prompt) is None

    def test_missing_node(self):
        assert _resolve_text(["999", 0], {}) is None

    def test_non_dict_node(self):
        prompt = {"1": "not a dict"}
        assert _resolve_text(["1", 0], prompt) is None


# ---------------------------------------------------------------------------
# _collect_conditioning_sources
# ---------------------------------------------------------------------------

class TestCollectConditioningSources:
    def test_direct_clip_text_encode(self):
        prompt = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "hi"}},
        }
        result = _collect_conditioning_sources(["1", 0], prompt)
        assert result == {"1"}

    def test_through_conditioning_combine(self):
        prompt = {
            "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "a"}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "b"}},
            "3": {
                "class_type": "ConditioningCombine",
                "inputs": {"conditioning_1": ["1", 0], "conditioning_2": ["2", 0]},
            },
        }
        result = _collect_conditioning_sources(["3", 0], prompt)
        assert result == {"1", "2"}

    def test_missing_node_returns_empty(self):
        result = _collect_conditioning_sources(["999", 0], {})
        assert result == set()

    def test_non_list_returns_empty(self):
        result = _collect_conditioning_sources("not_a_ref", {})
        assert result == set()

    def test_circular_reference_safe(self):
        prompt = {
            "1": {"class_type": "CondA", "inputs": {"cond": ["2", 0]}},
            "2": {"class_type": "CondB", "inputs": {"cond": ["1", 0]}},
        }
        result = _collect_conditioning_sources(["1", 0], prompt)
        assert result == set()


# ---------------------------------------------------------------------------
# get_image_dimensions / get_video_dimensions
# ---------------------------------------------------------------------------

class TestGetDimensions:
    def test_image_dimensions(self, sample_png_path):
        w, h = get_image_dimensions(sample_png_path)
        assert w == 1024
        assert h == 1024

    def test_image_dimensions_corrupt(self, tmp_path):
        f = tmp_path / "bad.png"
        f.write_bytes(b"not an image")
        w, h = get_image_dimensions(f)
        assert w is None
        assert h is None

    def test_image_dimensions_nonexistent(self, tmp_path):
        f = tmp_path / "nonexistent.png"
        w, h = get_image_dimensions(f)
        assert w is None
        assert h is None

    def test_video_dimensions_with_ffprobe(self, tmp_path):
        f = tmp_path / "video.mp4"
        f.write_bytes(b"\x00")
        with patch("app.services.metadata.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps({
                "streams": [{"width": 1920, "height": 1080}]
            })
            w, h = get_video_dimensions(f)
        assert w == 1920
        assert h == 1080

    def test_video_dimensions_no_streams(self, tmp_path):
        f = tmp_path / "video.mp4"
        f.write_bytes(b"\x00")
        with patch("app.services.metadata.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = json.dumps({"streams": []})
            w, h = get_video_dimensions(f)
        assert w is None
        assert h is None

    def test_video_dimensions_nonexistent(self, tmp_path):
        f = tmp_path / "nonexistent.mp4"
        w, h = get_video_dimensions(f)
        assert w is None
        assert h is None


# ---------------------------------------------------------------------------
# _sanitize_json
# ---------------------------------------------------------------------------

class TestSanitizeJson:
    def test_nan_replaced(self):
        assert _sanitize_json(float("nan")) is None

    def test_inf_replaced(self):
        assert _sanitize_json(float("inf")) is None
        assert _sanitize_json(float("-inf")) is None

    def test_normal_float_preserved(self):
        assert _sanitize_json(3.14) == 3.14

    def test_nested_dict(self):
        data = {"a": 1, "b": float("nan"), "c": {"d": float("inf"), "e": "ok"}}
        result = _sanitize_json(data)
        assert result == {"a": 1, "b": None, "c": {"d": None, "e": "ok"}}

    def test_nested_list(self):
        data = [1, float("nan"), [float("-inf"), "hello"]]
        result = _sanitize_json(data)
        assert result == [1, None, [None, "hello"]]

    def test_none_passthrough(self):
        assert _sanitize_json(None) is None

    def test_string_passthrough(self):
        assert _sanitize_json("NaN") == "NaN"

    def test_large_workflow_with_nan(self):
        """Simulate a ComfyUI workflow containing NaN values."""
        workflow = {
            "nodes": [
                {"id": 1, "pos": [float("nan"), 100.0]},
                {"id": 2, "pos": [200.0, float("inf")]},
            ],
            "version": 0.4,
        }
        result = _sanitize_json(workflow)
        assert result["nodes"][0]["pos"] == [None, 100.0]
        assert result["nodes"][1]["pos"] == [200.0, None]
        assert result["version"] == 0.4

    def test_png_with_nan_in_workflow(self, tmp_path):
        """Ensure extract_png_metadata sanitizes NaN values."""
        from PIL import Image
        from PIL.PngImagePlugin import PngInfo

        info = PngInfo()
        # Python's json.dumps produces "NaN" for float('nan')
        prompt_data = '{"1": {"inputs": {"value": NaN}}}'
        workflow_data = '{"nodes": [{"pos": [NaN, Infinity]}]}'
        info.add_text("prompt", prompt_data)
        info.add_text("workflow", workflow_data)
        img_path = tmp_path / "nan_test.png"
        Image.new("RGB", (10, 10)).save(img_path, pnginfo=info)

        prompt, workflow = extract_png_metadata(img_path)
        assert prompt == {"1": {"inputs": {"value": None}}}
        assert workflow == {"nodes": [{"pos": [None, None]}]}
