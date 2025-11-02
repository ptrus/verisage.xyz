#!/usr/bin/env bash

set -euo pipefail

BUILDER_IMAGE="moby/buildkit:v0.23.2"
SOURCE_DATE_EPOCH="1755248916"
IMAGE_NAME="docker.io/ptrusr/verisage"
IMAGE_TAG="${IMAGE_TAG:-latest}"
if [[ -n "${IMAGE_TAG}" ]]; then
    FULL_IMAGE_REF="${IMAGE_NAME}:${IMAGE_TAG}"
else
    FULL_IMAGE_REF="${IMAGE_NAME}"
fi
BUILDER_NAME="buildkit_23"
COMPOSE_FILE_PATH="${COMPOSE_FILE_PATH:-compose.yaml}"

echo "Building: ${FULL_IMAGE_REF}"
if ! docker buildx inspect "${BUILDER_NAME}" &>/dev/null; then
    docker buildx create \
        --use \
        --driver-opt image="${BUILDER_IMAGE}" \
        --name "${BUILDER_NAME}"
fi

METADATA_FILE=$(mktemp)
cleanup() {
    rm -f "${METADATA_FILE}"
}
trap cleanup EXIT

export SOURCE_DATE_EPOCH

docker buildx build \
    --builder "${BUILDER_NAME}" \
    --file Dockerfile \
    --tag "${FULL_IMAGE_REF}" \
    --no-cache \
    --provenance false \
    --build-arg "SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH}" \
    --build-arg "VITE_API_URL=${VITE_API_URL:-}" \
    --metadata-file "${METADATA_FILE}" \
    --load \
    .

IMAGE_ID=$(jq -r '."containerimage.config.digest"' "${METADATA_FILE}")
MANIFEST_DIGEST=$(jq -r '."containerimage.digest"' "${METADATA_FILE}")

if [[ -n "${IMAGE_ID}" && "${IMAGE_ID}" != "null" ]]; then
    docker tag "${IMAGE_ID}" "${FULL_IMAGE_REF}"
    echo "Tagged ${IMAGE_ID} as ${FULL_IMAGE_REF}"
fi

if [[ -z "${MANIFEST_DIGEST}" || "${MANIFEST_DIGEST}" == "null" ]]; then
    echo "Failed to resolve manifest digest from build metadata" >&2
    exit 1
fi

if [[ "${PUSH_IMAGE:-false}" == "true" ]]; then
    echo "Pushing ${FULL_IMAGE_REF} to registry..."
    docker push "${FULL_IMAGE_REF}"
    REPO_DIGEST=$(docker image inspect "${FULL_IMAGE_REF}" --format '{{index .RepoDigests 0}}' 2>/dev/null || true)
    if [[ -n "${REPO_DIGEST}" ]]; then
        EXTRACTED_DIGEST="${REPO_DIGEST#*@}"
        if [[ -n "${EXTRACTED_DIGEST}" && "${EXTRACTED_DIGEST}" != "${REPO_DIGEST}" ]]; then
            MANIFEST_DIGEST="${EXTRACTED_DIGEST}"
        fi
    else
        REMOTE_DIGEST=$(docker buildx imagetools inspect "${FULL_IMAGE_REF}" --format '{{.Digest}}' 2>/dev/null | tr -d '\r' || true)
        if [[ -n "${REMOTE_DIGEST}" ]]; then
            MANIFEST_DIGEST="${REMOTE_DIGEST}"
        fi
    fi
    echo "Successfully pushed ${IMAGE_NAME}@${MANIFEST_DIGEST}"
else
    echo "Skipping push (set PUSH_IMAGE=true to push to registry)"
fi

if [[ -n "${IMAGE_TAG}" ]]; then
    NEW_IMAGE_REFERENCE="${IMAGE_NAME}:${IMAGE_TAG}@${MANIFEST_DIGEST}"
else
    NEW_IMAGE_REFERENCE="${IMAGE_NAME}@${MANIFEST_DIGEST}"
fi

if [[ -n "${OUTPUT_IMAGE_NAME_PATH:-}" ]]; then
    echo "${NEW_IMAGE_REFERENCE}" > "${OUTPUT_IMAGE_NAME_PATH}"
fi

if [[ "${UPDATE_COMPOSE_SHA:-false}" == "true" ]]; then
    echo "Updating ${COMPOSE_FILE_PATH} image references to ${NEW_IMAGE_REFERENCE}"
    yq eval --inplace \
        "(.services.server.image = \"${NEW_IMAGE_REFERENCE}\") | (.services.worker.image = \"${NEW_IMAGE_REFERENCE}\")" \
        "${COMPOSE_FILE_PATH}"
fi

echo "${NEW_IMAGE_REFERENCE}"
