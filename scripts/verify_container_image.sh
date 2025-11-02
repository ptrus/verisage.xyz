#!/usr/bin/env bash

set -e

COMPOSE_FILE=$(yq -r '.artifacts.container.compose' rofl.yaml)
VERISAGE_IMAGE=$(yq -r '.services."server".image' ${COMPOSE_FILE})

if [[ "${VERISAGE_IMAGE}" != "${EXPECTED_VERISAGE_IMAGE}" ]]; then
  echo "Verisage image mismatch:"
  echo ""
  echo "  Configured in ${COMPOSE_FILE}:"
  echo "    ${VERISAGE_IMAGE}"
  echo ""
  echo "  Built locally:"
  echo "    ${EXPECTED_VERISAGE_IMAGE}"
  echo ""
  exit 1
fi

echo "Verisage image verified: ${VERISAGE_IMAGE}"
exit 0
