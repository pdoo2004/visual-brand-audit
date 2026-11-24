#!/bin/bash
# One-time: save Hugging Face token for BrandLens ARC jobs + future shells.
# Usage (on ARC login node — paste your own token, do not commit it):
#   bash setup_hf_token.sh hf_xxxxxxxx
set -euo pipefail

TOKEN="${1:-}"
if [[ -z "$TOKEN" ]]; then
  echo "Usage: $0 hf_your_token_here" >&2
  exit 1
fi

mkdir -p "$HOME/.config/brandlens"
ENV_FILE="$HOME/.config/brandlens/env"
umask 077
printf 'export HF_TOKEN=%q\n' "$TOKEN" >"$ENV_FILE"
chmod 600 "$ENV_FILE"

# Load for interactive + future login shells
MARKER="# brandlens HF_TOKEN"
if ! grep -qF "$MARKER" "$HOME/.bashrc" 2>/dev/null; then
  cat >>"$HOME/.bashrc" <<EOF

$MARKER
[ -f "\$HOME/.config/brandlens/env" ] && . "\$HOME/.config/brandlens/env"
EOF
fi

# Also store for huggingface-cli / transformers default lookup
source "$HOME/venvs/brandlens-train/bin/activate" 2>/dev/null || true
if command -v huggingface-cli >/dev/null 2>&1; then
  huggingface-cli login --token "$TOKEN" --add-to-git-credential 2>/dev/null || true
fi

echo "Saved $ENV_FILE (chmod 600) and wired ~/.bashrc"
echo "New shells and sbatch jobs will see HF_TOKEN."
