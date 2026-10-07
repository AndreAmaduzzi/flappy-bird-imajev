#!/usr/bin/env bash
# Install the official imajev server and download imajev-4b into third_party/imajev (~10 GB on disk).
#
#   scripts/setup_imajev.sh            # then: scripts/serve_imajev.sh
#
# Linux + NVIDIA GPU: PyTorch backend (CUDA 12.6 wheels, which run on drivers >= 525).
# macOS (Apple silicon): MLX backend, as in the model card (not tested by this repo).
# Env overrides: IMAJEV_DIR (install dir), IMAJEV_REF (git commit), TORCH_INDEX (PyTorch wheel index),
# PYTHON (an interpreter >= 3.11, < 3.15).
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
R=${IMAJEV_DIR:-$HERE/third_party/imajev}
REF=${IMAJEV_REF:-ccf586d}          # the commit this demo was tested with
TORCH_INDEX=${TORCH_INDEX:-https://download.pytorch.org/whl/cu126}
PYTHON=${PYTHON:-3.11}

if [[ ! -d "$R/.git" ]]; then
  git clone https://github.com/mohit67890/imajev "$R"
fi
git -C "$R" checkout -q "$REF"

cd "$R"
[[ -d .venv ]] || uv venv -q -p "$PYTHON" .venv
PIP=(uv pip install -q --python .venv/bin/python)

if [[ "$(uname -s)" == "Darwin" ]]; then
  "${PIP[@]}" -e ".[serve,mlx]"
  EXCLUDE=()
else
  "${PIP[@]}" torch torchvision --index-url "$TORCH_INDEX"
  "${PIP[@]}" -e ".[serve,torch]"
  # Triton kernels for Qwen3.5's gated-delta-rule layers (transformers otherwise uses a slow pure-PyTorch path):
  # ~20% lower latency per decision, same decisions.
  "${PIP[@]}" flash-linear-attention
  EXCLUDE=(--exclude 'mlx/*')
fi

.venv/bin/python scripts/download_model.py --model 4b          # Qwen/Qwen3.5-4B @851bf6e8 (8.7 GiB)
.venv/bin/hf download mohit67890/imajev-4b --local-dir adapters/imajev-4b "${EXCLUDE[@]}"
(cd adapters/imajev-4b && { sha256sum -c --ignore-missing SHA256SUMS 2>/dev/null || shasum -a 256 -c SHA256SUMS; })

echo "imajev ready in $R. Start it with: scripts/serve_imajev.sh"
