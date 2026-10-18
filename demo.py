"""One held-out project: what the aware checks flag (with sources + rule), and what literal rules get wrong."""
from crosscheck.checks import aware, literal
from crosscheck.project import make

P = make(9004, variants=True)
T = set(P["truth"])
f, w = aware(P["docs"])
print(f"project 9004 (held-out): {len(P['docs'])} documents, {len(T)} planted defects\n")
print("AWARE FLAGS")
for x in f:
    ok = "planted" if (x["rule"], x["tag"]) in T else "NOT planted"
    print(f"  {x['rule']:20} {x['tag']:14} {x['msg']}\n  {'':20} rule: {x['cite']}   [{ok}]")
    for s in x["sources"]:
        print(f"  {'':20}   source: {s}")
lit = {(x["rule"], x["tag"]) for x in literal(P["docs"])}
print("\nLITERAL RULES (same documents)")
print(f"  caught {len(lit & T)}/{len(T)}   false flags: {sorted(lit - T)}")
print(f"  look-alikes planted here: {[a for a in P['lookalikes'] if a[1] != '*']}")
