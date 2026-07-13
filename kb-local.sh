#!/bin/bash

TMPFILE=$(mktemp /tmp/kb-note-XXXXXX.txt)

nano "$TMPFILE"

if [ ! -s "$TMPFILE" ]; then
    echo "Empty note. Nothing processed."
    rm -f "$TMPFILE"
    exit 0
fi

cd ~/cke
source venv/bin/activate
python3 -m engine.cli --file "$TMPFILE"

rm -f "$TMPFILE"
