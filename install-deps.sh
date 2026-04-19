#!/bin/sh
# Render (Python nativo): instala PyTorch CPU antes del resto para no arrastrar ruedas CUDA (varios GB + OOM en 512Mi).
set -e
python -m pip install --upgrade pip
python -m pip install --no-cache-dir "torch>=2.2.0,<3.0.0" --index-url https://download.pytorch.org/whl/cpu
python -m pip install --no-cache-dir -r requirements.txt
