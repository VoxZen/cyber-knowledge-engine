"""
Splits large markdown/text into logical chunks based on headings.
This module ONLY splits text. It does not create notes or touch the vault.
"""
import re


def estimate_tokens(text):
    # Rough estimate for technical content (commands, hashes, IPs inflate tokens).
    # Uses ~1.8 tokens per word as a conservative heuristic.
    words = len(text.split())
    return int(words * 1.8)


def split_by_headings(text):
    """
    Split text into sections based on markdown headings (# or ## or ###).
    Returns a list of (heading, body) tuples. Text before the first heading
    is returned with an empty heading.
    """
    lines = text.split("\n")
    chunks = []
    current_heading = ""
    current_body = []

    heading_pattern = re.compile(r"^(#{1,3})\s+(.*)")

    for line in lines:
        match = heading_pattern.match(line.strip())
        if match:
            # Save the previous chunk before starting a new one
            if current_heading or current_body:
                chunks.append((current_heading, "\n".join(current_body).strip()))
            current_heading = match.group(2).strip()
            current_body = []
        else:
            current_body.append(line)

    # Save the last chunk
    if current_heading or current_body:
        chunks.append((current_heading, "\n".join(current_body).strip()))

    return chunks


def preview_chunks(text):
    """
    Show how the text would be split, with token estimates.
    Does NOT create any notes - this is for inspection only.
    """
    chunks = split_by_headings(text)
    print(f"Total text: ~{estimate_tokens(text)} tokens, {len(chunks)} chunk(s)")
    print("-" * 50)
    for i, (heading, body) in enumerate(chunks, 1):
        tokens = estimate_tokens(heading + " " + body)
        preview = body[:80].replace("\n", " ")
        print(f"{i}. [{tokens:>5} tok] {heading or '(no heading)'}")
        print(f"          {preview}...")
    print("-" * 50)
    return chunks
