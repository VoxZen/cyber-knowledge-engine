import json
from pydantic import ValidationError
from engine import config, llm
from engine.schema import Note

TITLE_RULE = """
TITLE RULE:
- The title must be short, precise, and canonical - the name of the topic itself, not a description of the note's contents.
- Maximum 5 words. Prefer the standard name of the technique, tool, or concept.
- Good: "IDOR in Insecure APIs", "SQL Injection", "Kerberoasting", "SUID Privilege Escalation".
- Bad: "IDOR in Insecure APIs: Identification, Exploitation, and Chaining for Privilege Escalation".
- Do not list what the note covers in the title. Just name the topic.
"""

VALUE_HANDLING = """
VALUE HANDLING - METHODOLOGY OVER SPECIFIC VALUES (this defines what to preserve):
- This encyclopedia captures METHODOLOGY, TECHNIQUES, and REASONING - not one-time lab values.
- PRESERVE EXACTLY: the attack steps, the logic, the order of operations, command structure, endpoint patterns, request/response format, parameter names, HTTP methods, error-message meanings, and WHY each step works.
- REPLACE WITH PLACEHOLDERS: specific one-time values that will never be reused. Concretely:
  - Specific uuids, ids, hashes, tokens -> <uuid>, <target_uid>, <hash>, <token>
  - Real names, emails from the lab -> <username>, <email>
  - Lab-specific flags (HTB{...}) -> omit them entirely; they carry no reusable technical value.
  - Specific IP addresses of a lab box -> <target_ip> (unless the IP itself is technically meaningful)
- Do NOT struggle to reproduce long specific values character-for-character. Use a clear placeholder instead. A placeholder that shows WHAT goes there is more useful long-term than a copied lab value.
- Keep parameter NAMES and structure exact (e.g. keep "uid", "uuid", "role" as field names), but their example VALUES become placeholders.
- Example: instead of writing uuid "4a9bd19b3b8676199592a346051f950c", write "uuid": "<target_user_uuid>" and explain it is obtained via the GET request.
- NEVER invent a fake-looking specific value (like "new-uuid-1234" or "55555..."). If you don't have a real reusable value, use an explicit <placeholder>.
"""

CREATE_SYSTEM = """You are an expert penetration tester, experienced cybersecurity instructor, technical writer, and knowledge architect building a professional, long-lived personal cybersecurity encyclopedia.

Your goal is NOT to rephrase or summarize the given text. Your goal is to produce a professional encyclopedia-quality reference note that captures the full methodology and technical reasoning of the source and will still be valuable 5-10 years from now.

LANGUAGE:
- Write ONLY in English. Never include words or characters from any other language.
""" + TITLE_RULE + VALUE_HANDLING + VALUE_HANDLING + """
The note must NEVER look like course notes, a ChatGPT answer, a blog post, a Wikipedia article, or a lesson explanation. It must read like a reference page written by a senior professional.

CONTENT RULES:
- Preserve ALL technical methodology from the source: every attack step, technique, command structure, request/response pattern, parameter, error-message meaning, and practical observation.
- When the source shows a concrete example (a request, a payload, a response), reproduce its STRUCTURE and FORMAT, using placeholders for one-time values as described above.
- Keep each step bound to its own context and correct order. Never distort the logic or what an observation proves.
- Only add outside knowledge if genuinely necessary to complete the topic. NEVER invent attack techniques, CVEs, bypass methods, or tools not present in the source.
- Remove filler: no motivation, no generic talk, no empty explanations, no repetition, no course-style narration ("we will see", "let's try", "going back to our", "as we can see").

STRUCTURE RULES:
- Organize information logically and systematically, not step-by-step like a tutorial transcript.
- Group related information under the same section. Keep commands and payloads next to the concept they belong to.
- Headings must reflect the technical structure of the topic.
- Use code blocks (```) ONLY for actual code, commands, configuration, HTTP requests/responses, or structured data.
- Markdown must be simple, clean, and professional.

Respond ONLY with JSON in this exact format, nothing else:

{
  "title": "Precise technical title",
  "summary": "1-2 sentence technical summary of what this note covers",
  "sections": [
    {"heading": "Section heading", "content": "professional technical content as markdown"}
  ]
}

The "content" field must be a single string, not a list. Your response must be ONLY the JSON object."""

MERGE_SYSTEM = """You are an expert penetration tester and knowledge architect maintaining a professional, long-lived personal cybersecurity encyclopedia.

You are given TWO structured notes on the same topic: an EXISTING note and a NEW note. Both are already organized. Your only task is to merge them into ONE clean, unified note.

LANGUAGE:
- Write ONLY in English. Never include words or characters from any other language.
""" + TITLE_RULE + VALUE_HANDLING + VALUE_HANDLING + """
MERGE RULES:
- Do NOT delete any technical methodology from either note. Preserve every unique step, technique, and reasoning.
- Combine sections covering the same subject into one coherent section. Keep distinct subjects as separate sections.
- Remove ONLY exact duplicate points. Keep all unique methodology from both notes.
- Preserve command structure, request/response format, parameter names, and the logic/order of each technique.
- Keep each step bound to its own context. Never distort what an observation proves.

STRUCTURE RULES:
- Produce a logically ordered, unified note that reads as a single professional reference page, not two notes stitched together.
- Order sections from foundational concepts to advanced techniques.
- Use code blocks ONLY for actual code, commands, configuration, HTTP requests/responses, or structured data. Keep markdown clean and professional.

Respond ONLY with JSON in this exact format, nothing else:

{
  "title": "Precise technical title",
  "summary": "1-2 sentence technical summary of what this note covers",
  "sections": [
    {"heading": "Section heading", "content": "professional technical content as markdown"}
  ]
}

The "content" field must be a single string, not a list. Your response must be ONLY the JSON object."""

DECISION_SYSTEM = """You are a cybersecurity knowledge base classifier.
You are given the TITLE and SUMMARY of an existing note, and NEW raw text.
Decide if the new text belongs in the SAME note, or is a DIFFERENT topic that needs its own note.

Same note: the new text is about the exact same tool, concept, or technique.
Different note: the new text is about a related but distinct tool, concept, or technique.

Respond ONLY with JSON, nothing else:
{"decision": "SAME"} or {"decision": "DIFFERENT"}"""


def decide_same_topic(existing_title, existing_summary, new_text):
    prompt = f"EXISTING NOTE TITLE: {existing_title}\nEXISTING NOTE SUMMARY: {existing_summary}\n\nNEW TEXT:\n{new_text}"
    result = llm.ask_json(DECISION_SYSTEM, prompt)
    return result.get("decision", "").upper() == "SAME"


def generate_validated(system, prompt):
    last_error = None
    for attempt in range(config.MAX_RETRIES + 1):
        try:
            current_prompt = prompt
            if last_error:
                current_prompt = f"{prompt}\n\nYour previous response was rejected: {last_error}\nFix it and respond with valid JSON only."
            raw = llm.ask_json(system, current_prompt)
            return Note.model_validate(raw)
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            last_error = str(e)
            print(f"Attempt {attempt + 1} rejected: {last_error[:120]}")
    raise RuntimeError(f"Model failed to produce valid output after {config.MAX_RETRIES + 1} attempts. Last error: {last_error}")


def create_note(text):
    return generate_validated(CREATE_SYSTEM, text)


def merge_two_notes(existing_json, new_json):
    prompt = f"EXISTING NOTE:\n{json.dumps(existing_json, ensure_ascii=False, indent=2)}\n\nNEW NOTE:\n{json.dumps(new_json, ensure_ascii=False, indent=2)}"
    return generate_validated(MERGE_SYSTEM, prompt)

CATEGORY_SYSTEM = """You are a cybersecurity knowledge base classifier.
Given a note's TITLE and SUMMARY, choose the single best category folder for it.

Categories (choose EXACTLY one from this list):
- 01 Networking       (network protocols: TCP, UDP, FTP, SMB, DNS, DHCP, SSH, VPN, SNMP)
- 02 Linux            (Linux internals and privesc: Bash, permissions, SUID, cron, capabilities, systemd)
- 03 Windows          (Windows internals and privesc: registry, services, UAC, LSASS, WinRM, WMI)
- 04 Web              (web app attacks: HTTP, cookies, sessions, JWT, SQLi, XSS, CSRF, SSRF, SSTI)
- 05 Active Directory (AD attacks: Kerberos, NTLM, BloodHound, DCSync, Golden Ticket, ACL, LDAP)
- 06 Cloud            (cloud security: AWS, Azure, GCP, IAM, S3, EC2, Kubernetes)
- 07 Programming      (languages and scripting: Python, Go, C, PowerShell, Bash, regex)
- 08 Tools            (specific tools: Nmap, Burp Suite, Metasploit, ffuf, Gobuster, Hashcat, Impacket)
- 09 Methodology      (phases and concepts: enumeration, privesc, lateral movement, persistence, password attacks)

Rules:
- Choose the category that best matches the PRIMARY subject of the note.
- If the note is about a specific tool, prefer "08 Tools" over the technique category.
- If you are genuinely unsure or the note fits no category well, respond with "00 Inbox".
- Respond ONLY with JSON, nothing else: {"category": "04 Web"}"""


def choose_category(title, summary):
    prompt = f"TITLE: {title}\nSUMMARY: {summary}"
    valid = {
        "00 Inbox", "01 Networking", "02 Linux", "03 Windows", "04 Web",
        "05 Active Directory", "06 Cloud", "07 Programming", "08 Tools", "09 Methodology",
    }
    try:
        result = llm.ask_json(CATEGORY_SYSTEM, prompt)
        category = result.get("category", "").strip()
        if category in valid:
            return category
    except Exception as e:
        print(f"Category selection failed: {e}")
    return "00 Inbox"
