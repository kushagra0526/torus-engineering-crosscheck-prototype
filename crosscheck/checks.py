"""Extract a project model from the documents, then run cross-document checks.

`aware` rules follow the code / project spec; `literal` rules are what a check sheet
written as "A <= B" does (the same comparisons without the engineering context).
Every flag carries the rule, both values with their source document, and a citation.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict

from .project import rating
from .units import parse, parse_naive

TAG = re.compile(r"\b(PSV|V|P|T|M)[\s-]?(\d{1,3}[A-Z]?)\b")


def norm_tag(s):
    m = TAG.search(s)
    return f"{m.group(1)}-{m.group(2)}" if m else None


def extract(docs, naive=False):
    def q(text):
        r = (parse_naive if naive else parse)(text)
        return r if r else (None,)

    M = {"vessel": defaultdict(dict), "psv": {}, "line": {}, "pump": defaultdict(dict), "xfmr": {}, "load": [], "spec": {}, "rev": {}}
    # vessel datasheets: blocks start at a tag line
    cur = None
    for ln in docs["vessel_datasheets.txt"].splitlines()[1:]:
        if re.match(r"\s*(Tag No\.|VESSEL)", ln):
            cur = norm_tag(ln)
            continue
        if cur and ":" in ln or (cur and "...." in ln):
            key = ln.lower()
            val = q(ln)
            if val[0] is None:
                continue
            src = ("vessel_datasheets.txt", ln.strip())
            if "maw" in key.replace(".", ""):
                M["vessel"][cur]["mawp"] = (val[0], src)
            elif "press" in key:
                M["vessel"][cur]["dp"] = (val[0], src)
            elif "temp" in key:
                M["vessel"][cur]["dt"] = (val[0], src)
    for ln in docs["process_datasheet.txt"].splitlines()[1:]:
        tag = norm_tag(ln)
        src = ("process_datasheet.txt", ln.strip())
        if "operating pressure" in ln:
            M["vessel"][tag]["op"] = (q(ln.split("pressure")[1])[0], src)
        if "normal flow" in ln:
            M["pump"][tag]["flow"] = (q(ln.split("flow")[1])[0], src)
            M["pump"][tag]["npsha"] = (float(re.search(r"NPSHa\s*([\d.]+)", ln).group(1)), src)
    for row in list(csv.reader(docs["psv_list.csv"].splitlines()))[1:]:
        tag, prot, sp, service, ref = row
        ln = ",".join(row)
        M["psv"][norm_tag(tag)] = {"vessel": norm_tag(prot), "sp": (q(sp)[0], ("psv_list.csv", ln)),
                                   "service": service.strip(), "ref": ref.strip()}
    for row in list(csv.reader(docs["line_list.csv"].splitlines()))[1:]:
        tag, p, t, cls = row
        ln = ",".join(row)
        M["line"][tag] = {"dp": (q(p)[0], ("line_list.csv", ln)), "dt": (q(t)[0], ("line_list.csv", ln)), "cls": cls.strip()}
    for ln in docs["pipe_spec.txt"].splitlines()[1:]:
        m = re.match(r"Class (\w+): ASME B16\.5 Class (\d+)", ln)
        M["spec"][f"class_{m.group(1)}"] = int(m.group(2))
    for name, text in docs.items():
        if name.startswith("vendor_"):
            tag = norm_tag(text.splitlines()[0])
            P = M["pump"][tag]
            for ln in text.splitlines()[1:]:
                src = (name, ln)
                k = ln.split(":")[0].lower() if ":" in ln else ln.lower()
                if k.startswith("rated flow"):
                    P["rated"] = (q(ln.split(":")[1])[0], src)
                elif k.startswith("npshr"):
                    P["npshr"] = (q(ln.split(":")[1] + " ft")[0], src)
                elif k.startswith("rated power"):
                    P["power"] = (q(ln.split(":")[1])[0], src)
                elif k.startswith("driver"):
                    P["motor"] = (q(ln.split(":")[1])[0], src)
                elif "api 610" in k:
                    P["ed"] = (int(re.search(r"(\d+)th", ln).group(1)), src)
    for ln in docs["transformers.txt"].splitlines()[1:]:
        tag = norm_tag(ln)
        m = re.search(r"([\d,]+)/([\d,]+) kVA", ln)
        mva = re.findall(r"[\d.]+ MVA", ln)
        if m:
            onan, onaf = float(m.group(1).replace(",", "")), float(m.group(2).replace(",", ""))
        elif len(mva) == 2:
            onan, onaf = (q(x)[0] for x in mva)
        else:
            continue   # unread: reported by the checks as missing data
        M["xfmr"][tag] = {"onan": (onan, ("transformers.txt", ln)), "onaf": (onaf, ("transformers.txt", ln))}
    for ln in docs["load_list.csv"].splitlines()[1:]:
        tag, bus, kw, pf, duty = ln.split(",")
        M["load"].append({"tag": tag, "bus": norm_tag(bus), "kva": float(kw) / float(pf), "duty": duty.strip()[0].upper()})
    spec = docs["spec.txt"]
    m = re.search(r"API 610 (\d+)th Edition( or later)?", spec)
    M["spec"]["api610"] = (int(m.group(1)), bool(m.group(2)))
    M["spec"]["demand"] = {"C": float(re.search(r"continuous loads (\d+)%", spec).group(1)) / 100,
                           "I": float(re.search(r"intermittent (\d+)%", spec).group(1)) / 100,
                           "S": float(re.search(r"standby (\d+)%", spec).group(1)) / 100}
    for ln in docs["register.txt"].splitlines()[1:]:
        m = re.match(r"(\S+)\s+rev (\w)", ln)
        M["rev"][m.group(1)] = m.group(2)
    return M


def _flag(rule, tag, msg, cite, *srcs):
    return {"rule": rule, "tag": tag, "msg": msg, "cite": cite, "sources": [s[1] for s in srcs if s]}


def _unread(W, tag, e):
    W.append(_flag("UNREAD", tag, f"could not read a value needed for this check ({type(e).__name__}: {e}); needs a person", ""))


def aware(docs):
    M = extract(docs)
    F, W = [], []
    by_vessel = defaultdict(list)
    for t, s in M["psv"].items():
        by_vessel[s["vessel"]].append((t, s))
    for vt, valves in by_vessel.items():
      try:
        v = M["vessel"][vt]
        mawp = v.get("mawp", v["dp"])
        proc = sorted([x for x in valves if x[1]["service"] == "process"], key=lambda x: x[1]["sp"][0])
        for i, (t, s) in enumerate(proc):
            lim, rule = (1.0, "PSV_SET_OVER_MAWP") if i == 0 else (1.05, "PSV_ADDL_OVER_105")
            if s["sp"][0] > lim * mawp[0] + 0.5:
                F.append(_flag(rule, t, f"set {s['sp'][0]:.0f} psig > {lim:.0%} of MAWP {mawp[0]:.0f} psig ({vt})",
                               "ASME VIII-1 UG-134(a) (2019 ed.; Section XIII in 2021+)", s["sp"], mawp))
        for t, s in valves:
            if s["service"] == "fire" and s["sp"][0] > 1.10 * mawp[0] + 0.5:
                F.append(_flag("PSV_SET_OVER_MAWP", t, "fire valve set > 110% MAWP", "ASME VIII-1 UG-134(b)", s["sp"], mawp))
        if proc and "op" in v:
            lowest = min(proc[0][1]["sp"][0], mawp[0])
            if v["op"][0] > 0.9 * lowest + 0.5:
                F.append(_flag("OP_TOO_CLOSE_TO_SET", vt, f"operating {v['op'][0]:.0f} psig > 90% of lowest set {lowest:.0f} psig",
                               "project spec SP-MECH-001 (operating margin)", v["op"], proc[0][1]["sp"]))
      except (KeyError, TypeError, ValueError) as e:
        _unread(W, vt, e)
    for t, l in M["line"].items():
      try:
        cls = M["spec"][f"class_{l['cls']}"]
        r = rating(cls, l["dt"][0])
        if l["dp"][0] > r + 0.5:
            F.append(_flag("PIPE_CLASS_DERATED", t, f"design {l['dp'][0]:.0f} psig > Class {cls} rating {r:.0f} psig at {l['dt'][0]:.0f} °F",
                           "ASME B16.5-2020 Table 2-1.1 (Group 1.1)", l["dp"]))
      except (KeyError, TypeError, ValueError) as e:
        _unread(W, t, e)
    dem = M["spec"]["demand"]
    for t in {l["bus"] for l in M["load"]} - set(M["xfmr"]):
        _unread(W, t, KeyError("transformer rating"))
    for t, x in M["xfmr"].items():
        d = sum(l["kva"] * dem[l["duty"]] for l in M["load"] if l["bus"] == t)
        if d > x["onaf"][0]:
            F.append(_flag("XFMR_OVER_ONAF", t, f"max demand {d:,.0f} kVA > ONAF {x['onaf'][0]:,.0f} kVA", "load list + spec demand factors", x["onaf"]))
        elif d > x["onan"][0]:
            W.append(_flag("XFMR_NEEDS_FANS", t, f"max demand {d:,.0f} kVA > ONAN {x['onan'][0]:,.0f} kVA (fans required)", "", x["onan"]))
    ed, later = M["spec"]["api610"]
    for t, p in M["pump"].items():
      try:
        if "ed" in p and (p["ed"][0] < ed or (not later and p["ed"][0] != ed)):
            F.append(_flag("CODE_EDITION", t, f"vendor API 610 {p['ed'][0]}th vs spec {ed}th{' or later' if later else ''}", "SP-MECH-001", p["ed"]))
        pw = p["power"][0]
        need = pw * (1.25 if pw < 22 else 1.15 if pw <= 55 else 1.10)
        if p["motor"][0] < need - 0.05:
            F.append(_flag("MOTOR_MARGIN", t, f"driver {p['motor'][0]:.1f} kW < {need:.1f} kW required for {pw:.1f} kW rated",
                           "API 610 driver sizing (per SP-MECH-001)", p["motor"], p["power"]))
        a, r = p["npsha"][0], p["npshr"][0]
        if a < 1.1 * r or a < r + 3:
            F.append(_flag("NPSH_MARGIN", t, f"NPSHa {a} ft vs NPSHr {r} ft", "SP-MECH-001 NPSH margin", p["npsha"], p["npshr"]))
        if p["rated"][0] < 1.1 * p["flow"][0] - 0.5:
            F.append(_flag("RATED_FLOW_MARGIN", t, f"rated {p['rated'][0]:.0f} < 110% of normal {p['flow'][0]:.0f} m3/h", "SP-MECH-001", p["rated"], p["flow"]))
      except (KeyError, TypeError, ValueError) as e:
        _unread(W, t, e)
    for t, s in M["psv"].items():
        m = re.match(r"(\S+) rev (\w)", s["ref"])
        if m and M["rev"].get(m.group(1), m.group(2)) != m.group(2):
            F.append(_flag("STALE_REF", t, f"references {m.group(1)} rev {m.group(2)}, current is rev {M['rev'][m.group(1)]}", "document register", s["sp"]))
    return F, W


def literal(docs):
    """Same extraction (gauge/absolute ignored), comparisons taken literally. Unreadable items are skipped."""
    M = extract(docs, naive=True)
    F = []

    def guard(fn):
        try:
            fn()
        except (KeyError, TypeError, ValueError):
            pass

    def psv(t, s):
        v = M["vessel"][s["vessel"]]
        if s["sp"][0] > v["dp"][0] + 0.5:
            F.append(_flag("PSV_SET_OVER_MAWP" if t.endswith("A") else "PSV_ADDL_OVER_105", t, "set > design pressure", "", s["sp"]))
        if "op" in v and v["op"][0] > 0.9 * s["sp"][0] + 0.5:
            F.append(_flag("OP_TOO_CLOSE_TO_SET", s["vessel"], "operating > 90% set", "", v["op"]))

    def line(t, l):
        if l["dp"][0] > rating(M["spec"][f"class_{l['cls']}"], 100) + 0.5:
            F.append(_flag("PIPE_CLASS_DERATED", t, "design > class rating", "", l["dp"]))

    def xfmr(t, x):
        if sum(l["kva"] for l in M["load"] if l["bus"] == t) > x["onan"][0]:
            F.append(_flag("XFMR_OVER_ONAF", t, "connected load > rating", "", x["onan"]))

    def pump(t, p):
        if p["ed"][0] != M["spec"]["api610"][0]:
            F.append(_flag("CODE_EDITION", t, "edition mismatch", "", p["ed"]))
        if p["motor"][0] < p["power"][0]:
            F.append(_flag("MOTOR_MARGIN", t, "driver < pump power", "", p["motor"]))
        if p["npsha"][0] < p["npshr"][0]:
            F.append(_flag("NPSH_MARGIN", t, "NPSHa < NPSHr", "", p["npsha"]))
        if p["rated"][0] < p["flow"][0]:
            F.append(_flag("RATED_FLOW_MARGIN", t, "rated < normal flow", "", p["rated"]))

    for t, s in M["psv"].items():
        guard(lambda: psv(t, s))
    for t, l in M["line"].items():
        guard(lambda: line(t, l))
    for t, x in M["xfmr"].items():
        guard(lambda: xfmr(t, x))
    for t, p in M["pump"].items():
        guard(lambda: pump(t, p))
    return F
