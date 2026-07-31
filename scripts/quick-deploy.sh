#!/bin/sh
set -eu
echo "This legacy quick deploy path is retired because it downloads tools and bypasses release gates." >&2
echo "Use the P3 online publisher or an architecture-specific offline package." >&2
exit 64
