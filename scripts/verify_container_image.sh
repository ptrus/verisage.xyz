#!/usr/bin/env bash

set -e

COMPOSE_FILE=$(yq -r '.artifacts.container.compose' rofl.yaml)
VERISAGE_IMAGE=$(yq -r '.services."talos-agent".image' ${COMPOSE_FILE})

if [[ "${VERISAGE_IMAGE}" != "${EXPECTED_VERISAGE_IMAGE}" ]]; then
  echo "Talos agent image mismatch:"
  echo ""
  echo "  Configured in ${COMPOSE_FILE}:"
  echo "    ${VERISAGE_IMAGE}"
  echo ""
  echo "  Built locally:"
  echo "    ${EXPECTED_VERISAGE_IMAGE}"
  echo ""
  exit 1
fi
