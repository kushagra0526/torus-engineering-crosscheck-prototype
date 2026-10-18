"""Score aware vs literal checks on synthetic projects.

usage: python evaluate.py dev|heldout
dev: seeds 1-40, the document layouts the extractor was written for.
heldout: seeds 9001-9060, plus 4 document variants it was NOT written for (units in column
headers, kg/cm2(g), reordered PSV columns, a new transformer phrasing). Frozen in git first.
"""

import json
import sys
from collections import Counter
from pathlib import Path

from crosscheck.checks import aware, literal
from crosscheck.project import DEFECTS, make

SPLITS = {"dev": (range(1, 41), False), "heldout": (range(9001, 9061), True)}


def run(split):
    seeds, variants = SPLITS[split]
    res = {m: {"caught": 0, "missed": 0, "false": 0, "false_on_lookalike": 0, "by_rule": Counter(), "miss_by_rule": Counter()}
           for m in ("aware", "literal")}
    planted, n_look, unread, examples = 0, 0, 0, []
    for s in seeds:
        P = make(s, variants)
        T = set(P["truth"])
        look_tags = {t for _, t in P["lookalikes"]}
        planted += len(T)
        n_look += len([1 for a, t in P["lookalikes"] if t != "*"])
        fa, warns = aware(P["docs"])
        unread += sum(1 for w in warns if w["rule"] == "UNREAD")
        for m, flags in (("aware", fa), ("literal", literal(P["docs"]))):
            F = {(f["rule"], f["tag"]) for f in flags}
            r = res[m]
            r["caught"] += len(F & T)
            r["missed"] += len(T - F)
            r["false"] += len(F - T)
            r["false_on_lookalike"] += sum(1 for _, t in F - T if t in look_tags)
            for rule, _ in F & T:
                r["by_rule"][rule] += 1
            for rule, _ in T - F:
                r["miss_by_rule"][rule] += 1
        if len(examples) < 3 and fa:
            examples.append({"seed": s, "flags": fa[:3]})
    out = {"split": split, "projects": len(seeds), "planted": planted, "lookalikes": n_look, "aware_unread_items": unread,
           "results": {m: {**r, "by_rule": dict(r["by_rule"]), "miss_by_rule": dict(r["miss_by_rule"])} for m, r in res.items()},
           "examples": examples}
    return out


if __name__ == "__main__":
    split = sys.argv[1] if len(sys.argv) > 1 else "dev"
    o = run(split)
    Path("out").mkdir(exist_ok=True)
    Path(f"out/{split}.json").write_text(json.dumps(o, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{split}: {o['projects']} projects, {o['planted']} planted defects, {o['lookalikes']} planted look-alikes\n")
    for m, r in o["results"].items():
        print(f"  {m:8} caught {r['caught']:4}/{o['planted']}   false flags {r['false']:4} ({r['false_on_lookalike']} on look-alikes)")
        if r["miss_by_rule"]:
            print(f"           missed by rule: {r['miss_by_rule']}")
    print(f"\n  aware: {o['aware_unread_items']} items reported as UNREAD (needs a person) instead of passing silently")
