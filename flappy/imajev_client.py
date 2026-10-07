"""HTTP client for the imajev System One endpoint (POST /v1/systemone, TypeSafe Jev request format).

Images go as multipart `image` files next to the JSON `request` field (first image = reference, second = target).
The server accepts large images but the model was trained on images of at most 400,000 pixels, so the client
downscales before sending. Frames are sent as PNG: lossless and small for flat-colour graphics.
"""
from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass, field

import requests
from PIL import Image

from .render import resize_for_model

DEFAULT_URL = "http://127.0.0.1:8765"


@dataclass
class Answer:
    """One question's answer. `probabilities` cover the real options only (they sum to 1, unknown excluded, as the
    server reports them); `unknown` is the unknown probability; `full` is the distribution over options + unknown."""
    type: str
    probabilities: dict[str, float]
    unknown: float
    abstained: bool              # unknown was the most likely outcome
    choice: str | None = None    # choice questions: the most likely real option

    @property
    def full(self) -> dict[str, float]:
        return {**{k: v * (1 - self.unknown) for k, v in self.probabilities.items()}, "unknown": self.unknown}

    @property
    def top(self) -> str:
        """Most likely outcome including unknown."""
        full = self.full
        return max(full, key=full.get)


@dataclass
class SystemOneResult:
    answers: dict[str, Answer]
    latency_ms: float             # client round trip (encode + HTTP + server)
    server_ms: float              # server-reported total_ms
    input_tokens: int
    raw: dict = field(repr=False, default_factory=dict)


def parse_answer(raw: dict) -> Answer:
    unknown = float(raw["unknown_probability"])
    if raw["type"] == "noul":
        # noul = P(yes) + 0.5 * P(unknown)  ->  P(yes), P(no) over the known mass
        p_yes = max(0.0, float(raw["noul"]) - 0.5 * unknown)
        known = max(1e-12, 1.0 - unknown)
        probs = {"yes": min(1.0, p_yes / known), "no": max(0.0, 1.0 - p_yes / known)}
        return Answer("noul", probs, unknown, bool(raw["abstained"]), "yes" if probs["yes"] >= 0.5 else "no")
    probs = {k: float(v) for k, v in raw["probabilities"].items()}
    return Answer(raw["type"], probs, unknown, bool(raw["abstained"]), raw.get("choice"))


def uncalibrate(full: dict[str, float], temperature: float) -> dict[str, float]:
    """Undo temperature scaling: softmax(z / T) ** T renormalised is softmax(z)."""
    powered = {k: max(v, 1e-300) ** temperature for k, v in full.items()}
    total = sum(powered.values())
    return {k: v / total for k, v in powered.items()}


def encode_png(image: Image.Image, max_pixels: int) -> bytes:
    buffer = io.BytesIO()
    resize_for_model(image.convert("RGB"), max_pixels).save(buffer, format="PNG", compress_level=1)
    return buffer.getvalue()


class ImajevClient:
    def __init__(self, url: str = DEFAULT_URL, max_pixels: int = 400_000, timeout: float = 60.0):
        self.url = url.rstrip("/")
        self.max_pixels = max_pixels
        self.timeout = timeout
        self.session = requests.Session()   # keep-alive: no TCP handshake per decision

    def ask(self, questions: dict, images: list[Image.Image] = (), state: dict | str | None = None) -> SystemOneResult:
        if len(images) > 2:
            raise ValueError("imajev takes at most 2 images")
        start = time.perf_counter()
        payload = {"state": state if state is not None else {}, "questions": questions}
        files = [("image", (f"frame{i}.png", encode_png(im, self.max_pixels), "image/png")) for i, im in enumerate(images)]
        response = self.session.post(f"{self.url}/v1/systemone", data={"request": json.dumps(payload)},
                                     files=files, timeout=self.timeout)
        latency_ms = (time.perf_counter() - start) * 1000
        if response.status_code != 200:
            raise RuntimeError(f"imajev {response.status_code}: {response.text[:500]}")
        body = response.json()
        usage = body.get("usage", {})
        return SystemOneResult({k: parse_answer(v) for k, v in body["answers"].items()}, latency_ms,
                               float(usage.get("total_ms", 0.0)), int(usage.get("input_tokens", 0)), body)

    def info(self) -> dict:
        return self.session.get(f"{self.url}/v1/models", timeout=self.timeout).json()

    def warmup(self, image: Image.Image, questions: dict, n: int = 2) -> None:
        """The first requests compile Triton kernels / allocate graphs (seconds); keep them out of the metrics."""
        for _ in range(n):
            self.ask(questions, [image])
            self.ask(questions, [image, image])
