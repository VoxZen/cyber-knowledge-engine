#!/bin/bash

# Flags that do not need note text (handled directly by engine.cli)
for arg in "$@"; do
    if [ "$arg" = "--delete" ]; then
        cd ~/cke
        source venv/bin/activate
        python3 -m engine.cli "$@"
        exit 0
    fi
done

TMPFILE=$(mktemp /tmp/kb-note-XXXXXX)
mv "$TMPFILE" "$TMPFILE.md"
TMPFILE="$TMPFILE.md"

nano "$TMPFILE"

if [ ! -s "$TMPFILE" ]; then
    echo "Empty note. Nothing processed."
    rm -f "$TMPFILE"
    exit 0
fi

cd ~/cke
source venv/bin/activate
python3 -m engine.cli "$@" --file "$TMPFILE"

rm -f "$TMPFILE"
