#!/usr/bin/env sh
# Pluggable M6 alerting hook (POSIX sh).
# Reads JSON payload from $1 or stdin and writes a single-line JSON alert to stderr
# (and optionally appends to $AISHOPPING_ALERT_LOG).
set -eu

if [ $# -ge 1 ]; then
    PAYLOAD="$1"
else
    PAYLOAD="$(cat)"
fi

printf '%s\n' "$PAYLOAD" >&2

if [ -n "${AISHOPPING_ALERT_LOG:-}" ]; then
    mkdir -p "$(dirname "$AISHOPPING_ALERT_LOG")"
    printf '%s\n' "$PAYLOAD" >> "$AISHOPPING_ALERT_LOG"
fi
