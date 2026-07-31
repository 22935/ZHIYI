#!/bin/sh
set -eu
echo "This legacy release builder is retired because it used floating tags and incomplete images." >&2
echo "Run: python3 -m scripts.release.security_gate ... && python3 -m scripts.release.package_offline ..." >&2
exit 64
