#!/usr/bin/env bash

set -euo pipefail

BUILDER_IMAGE="moby/buildkit:v0.23.2"
SOURCE_DATE_EPOCH="1755248916"
IMAGE_NAME="docker.io/ptrusr/verisage"
IMAGE_TAG="${IMAGE_TAG:-latest}"
BUILDER_NAME="buildkit_23"

echo "Building: ${IMAGE_NAME}:${IMAGE_TAG}"
# Create buildx builder with fixed BuildKit version.
if ! docker buildx inspect "$BUILDER_NAME" &>/dev/null; then
    docker buildx create \
        --use \
        --driver-opt image="${BUILDER_IMAGE}" \
        --name "$BUILDER_NAME"
fi

# Metadata file for image digest.
METADATA_FILE=$(mktemp)
trap "rm -f $METADATA_FILE" EXIT

# Build with reproducibility flags.
docker buildx build \
    --builder "$BUILDER_NAME" \
    --file Dockerfile \
    --tag "${IMAGE_NAME}" \
    --no-cache \
    --provenance false \
    --build-arg "SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}" \
    --build-arg "VITE_API_URL=${VITE_API_URL:-}" \
    --metadata-file "$METADATA_FILE" \
    --load \
    .

# Get the image ID that was loaded.
IMAGE_ID=$(jq -r '."containerimage.config.digest"' "${METADATA_FILE}")
DIGEST=$(jq -r '."containerimage.digest"' "${METADATA_FILE}")

# Explicitly tag the loaded image with the specified tag.
if [ -n "$IMAGE_ID" ] && [ "$IMAGE_ID" != "null" ]; then
    docker tag "$IMAGE_ID" "${IMAGE_NAME}:${IMAGE_TAG}"
    echo "Tagged ${IMAGE_ID} as ${IMAGE_NAME}:${IMAGE_TAG}"
fi

if [[ -n "${OUTPUT_IMAGE_NAME_PATH:-}" ]]; then
    echo "${IMAGE_NAME}" > ${OUTPUT_IMAGE_NAME_PATH}
fi

# Push to registry only if PUSH_IMAGE is set to true.
if [[ "${PUSH_IMAGE:-false}" == "true" ]]; then
    echo "Pushing ${IMAGE_NAME}:${IMAGE_TAG} to registry..."
    docker push "${IMAGE_NAME}:${IMAGE_TAG}"
    echo "Successfully pushed ${IMAGE_NAME}:${IMAGE_TAG}"
else
    echo "Skipping push (set PUSH_IMAGE=true to push to registry)"
fi

# Output the image digest.
echo "${IMAGE_NAME}:${IMAGE_TAG}@${DIGEST}"
