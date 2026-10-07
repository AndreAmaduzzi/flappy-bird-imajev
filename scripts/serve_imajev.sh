#!/usr/bin/env bash
# Start the official imajev server (installed by scripts/setup_imajev.sh) on http://127.0.0.1:<port>.
#
#   scripts/serve_imajev.sh                      # Linux: default GPU, port 8765 · macOS: MLX (Apple silicon)
#   scripts/serve_imajev.sh 1                    # Linux: GPU index 1
#   scripts/serve_imajev.sh GPU-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx 8766 --fast
#
# Arguments: [gpu] [port] [extra server flags...]. `gpu` is "auto" (default), an index or a UUID from `nvidia-smi -L`
# (prefer the UUID on machines where CUDA and nvidia-smi number the GPUs differently). --fast records CUDA graphs at
# start (about a minute) and makes each decision ~20% faster.
# Env overrides: IMAJEV_DIR, ROTATIONS (default 1), CALIBRATION (path, or "none").
set -euo pipefail

GPU=${1:-auto}
PORT=${2:-8765}
shift $(( $# >= 2 ? 2 : $# ))

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
R=${IMAJEV_DIR:-$HERE/third_party/imajev}
ROTATIONS=${ROTATIONS:-1}
CALIBRATION=${CALIBRATION:-$R/adapters/imajev-4b/calibration.json}

if [[ ! -x "$R/.venv/bin/python" ]]; then
  echo "imajev is not installed in $R: run scripts/setup_imajev.sh first" >&2
  exit 1
fi

CAL_ARGS=()
[[ "$CALIBRATION" != "none" ]] && CAL_ARGS=(--calibration "$CALIBRATION")

if [[ "$(uname -s)" == "Darwin" ]]; then
  BACKEND=(--backend mlx --adapter adapters/imajev-4b/mlx)
else
  BACKEND=(--backend torch --adapter adapters/imajev-4b)
  [[ "$GPU" != "auto" ]] && export CUDA_VISIBLE_DEVICES=$GPU
fi

cd "$R"
PYTHONPATH="$R/src:$R/scripts" exec "$R/.venv/bin/python" scripts/playground/server.py \
  "${BACKEND[@]}" \
  --model-bundle artifacts/model-qwen4b.json \
  --rotations "$ROTATIONS" \
  "${CAL_ARGS[@]}" \
  --model-name imajev-4b \
  --port "$PORT" \
  "$@"
