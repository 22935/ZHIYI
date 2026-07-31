#!/bin/sh
set -eu
echo "This online installer is retired; it cannot prove architecture, digest, SBOM, or offline operation." >&2
echo "Use the architecture-specific P3 package and its scripts/preflight.sh and scripts/install.sh." >&2
exit 64
