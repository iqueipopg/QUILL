"""Sample N essays from LEAF for the experiment.
Picks diverse-length essays with non-empty human feedback."""
import json, random, re
from pathlib import Path

N = 10  # final experiment size
SRC = "data/leaf/leaf.jsonl"
OUT = "data/leaf/subset_full.json"
random.seed(42)

ESSAY_FIELD = "essay_text"
FEEDBACK_FIELD = "human_feedback_text"
PROMPT_FIELD = "essay_title"  # LEAF has no rubric field; title acts as topic/prompt

def clean_essay(text):
    """Clean LEAF essay text: convert literal \\n to real newlines,
    strip 'QUESTION:' prefix, cut off the moderator footer that follows '--'."""
    if not text:
        return ""
    text = text.replace("\\n", "\n")
    text = re.sub(r"\n[ \t]+", "\n", text)
    stripped = text.lstrip()
    if stripped.lower().startswith("question:"):
        text = stripped[len("question:"):].lstrip()
    for sep in ["\n--\n", "\n-- \n", "\n --\n", " -- ", "\n-- "]:
        if sep in text:
            text = text.split(sep)[0]
            break
    return text.strip()

with open(SRC) as f:
    entries = [json.loads(l) for l in f]

def word_count(s): return len(s.split())
filtered = [
    e for e in entries
    if e.get(ESSAY_FIELD) and e.get(FEEDBACK_FIELD)
    and 150 <= word_count(e[ESSAY_FIELD]) <= 800
]
print(f"filtered pool: {len(filtered)}")

random.shuffle(filtered)
subset = filtered[:N]

out = []
for i, e in enumerate(subset):
    fb = e[FEEDBACK_FIELD]
    out.append({
        "essay_id": f"leaf_{i:03d}",
        "essay_text": clean_essay(e[ESSAY_FIELD]),
        "prompt": clean_essay(e.get(PROMPT_FIELD, "")),
        "human_feedback": fb if isinstance(fb, str) else json.dumps(fb),
    })

Path(OUT).parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"wrote {len(out)} essays to {OUT}")
print("\nessay word counts:", [word_count(e["essay_text"]) for e in out])
print("feedback word counts:", [word_count(e["human_feedback"]) for e in out])
