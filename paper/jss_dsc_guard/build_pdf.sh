#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

TEXROOT="$REPO_ROOT/tools/basictex_pkg/expanded/BasicTeX-2026-Start.pkg/Payload/usr/local/texlive/2026basic"
TEXBIN="$TEXROOT/bin/universal-darwin"

if [ ! -x "$TEXBIN/pdflatex" ]; then
  echo "Local BasicTeX was not found at: $TEXROOT" >&2
  echo "Expected pdflatex at: $TEXBIN/pdflatex" >&2
  exit 1
fi

export TEXROOT
export PATH="$TEXBIN:$PATH"
export TEXMFVAR="$REPO_ROOT/tools/texlive-local/texmf-var"
export TEXMFCONFIG="$REPO_ROOT/tools/texlive-local/texmf-config"
export TEXMFHOME="$REPO_ROOT/tools/texlive-local/texmf-home"

mkdir -p "$TEXMFVAR" "$TEXMFCONFIG" "$TEXMFHOME"

cd "$SCRIPT_DIR"

if [ ! -f elsarticle.cls ]; then
  pdflatex -interaction=nonstopmode elsarticle.ins
fi

pdflatex -interaction=nonstopmode main.tex
bibtex main
pdflatex -interaction=nonstopmode main.tex
pdflatex -interaction=nonstopmode main.tex

echo "Generated $SCRIPT_DIR/main.pdf"
