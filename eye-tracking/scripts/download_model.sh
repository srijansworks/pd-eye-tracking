#!/usr/bin/env bash
# Downloads Google's official MediaPipe Face Landmarker model (Apache-2.0, ~3.7 MB).
# Model weights are not committed to git.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p models
curl -sSfL -o models/face_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
echo "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff  models/face_landmarker.task" | shasum -a 256 -c -
