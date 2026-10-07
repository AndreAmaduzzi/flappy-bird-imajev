import io
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image

from flappy.imajev_client import ImajevClient, parse_answer, uncalibrate

CHOICE = {"type": "choice", "choice": "wait", "probabilities": {"flap": 0.25, "wait": 0.75}, "confidence": 0.5,
          "unknown_probability": 0.2, "abstained": False}
NOUL = {"type": "noul", "noul": 0.9, "unknown_probability": 0.1, "abstained": False}


def test_parse_choice():
    a = parse_answer(CHOICE)
    assert a.probabilities == {"flap": 0.25, "wait": 0.75} and a.unknown == 0.2
    assert a.full == pytest.approx({"flap": 0.2, "wait": 0.6, "unknown": 0.2})
    assert a.top == "wait"


def test_parse_noul():
    a = parse_answer(NOUL)    # P(yes) = 0.9 - 0.05 = 0.85, P(no) = 0.05, P(unknown) = 0.1
    assert a.full == pytest.approx({"yes": 0.85, "no": 0.05, "unknown": 0.1})
    assert a.choice == "yes"


def test_uncalibrate_inverts_temperature():
    logits = {"flap": 1.3, "wait": -0.4, "unknown": -2.0}
    softmax = lambda z, t: {k: math.exp(v / t) / sum(math.exp(x / t) for x in z.values()) for k, v in z.items()}  # noqa: E731
    assert uncalibrate(softmax(logits, 1.305), 1.305) == pytest.approx(softmax(logits, 1.0))


class FakeServer(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        FakeServer.seen.append((self.headers["Content-Type"], body))
        reply = json.dumps({"model": "imajev-4b", "answers": {"action": CHOICE},
                            "usage": {"total_ms": 12.5, "input_tokens": 300}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, *args):
        pass


def test_client_multipart_roundtrip():
    server = HTTPServer(("127.0.0.1", 0), FakeServer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = ImajevClient(f"http://127.0.0.1:{server.server_port}")
        big = Image.new("RGB", (1152, 2048), (10, 20, 30))
        result = client.ask({"action": {"type": "choice", "instructions": "q", "criteria": {"flap": None, "wait": None}}},
                            [big, big])
    finally:
        server.shutdown()
    content_type, body = FakeServer.seen[-1]
    assert content_type.startswith("multipart/form-data")
    assert body.count(b'name="image"') == 2 and b'name="request"' in body
    png = body[body.index(b"\x89PNG"):]
    assert Image.open(io.BytesIO(png)).size[0] * Image.open(io.BytesIO(png)).size[1] <= 400_000
    assert result.server_ms == 12.5 and result.input_tokens == 300
    assert result.answers["action"].probabilities["wait"] == 0.75
