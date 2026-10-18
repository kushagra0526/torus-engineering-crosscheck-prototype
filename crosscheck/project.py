"""Synthetic capital-project document sets with planted defects and planted look-alikes.

Each project renders ~10 text documents in mixed layouts, key spellings, tag spellings
and units. `truth` lists the real defects (rule, tag); look-alikes are values that a
literal check would flag but are fine by code or by the project spec.
"""

from __future__ import annotations

import csv
import io
import random

DEFECTS = ["PSV_SET_OVER_MAWP", "PSV_ADDL_OVER_105", "OP_TOO_CLOSE_TO_SET", "PIPE_CLASS_DERATED",
           "XFMR_OVER_ONAF", "CODE_EDITION", "MOTOR_MARGIN", "NPSH_MARGIN", "RATED_FLOW_MARGIN", "STALE_REF"]
LOOKALIKES = ["SET_ABOVE_DESIGN_BELOW_MAWP", "ADDL_VALVE_WITHIN_105", "FIRE_VALVE_WITHIN_110",
              "OP_IN_PSIA", "CONNECTED_OVER_ONAN_DEMAND_OK", "EDITION_OR_LATER", "MIXED_UNITS_AGREE",
              "HOT_LINE_WITHIN_RATING"]
BAR = 14.5038
ATM = 14.696
# ASME B16.5-2020 Table 2-1.1 (Group 1.1, e.g. A105), psig by degF
PT = {150: [(100, 285), (200, 260), (300, 230), (400, 200), (500, 170), (600, 140), (650, 125), (700, 110)],
      300: [(100, 740), (200, 680), (300, 655), (400, 635), (500, 605), (600, 570), (650, 550), (700, 530)]}


def rating(cls, t):
    pts = PT[cls]
    if t <= pts[0][0]:
        return pts[0][1]
    for (t0, p0), (t1, p1) in zip(pts, pts[1:]):
        if t <= t1:
            return p0 + (p1 - p0) * (t - t0) / (t1 - t0)
    return pts[-1][1]


def _csv(rows):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    return buf.getvalue().strip()


def _tag(rng, t):
    a, b = t.split("-")
    return rng.choice([f"{a}-{b}", f"{a} {b}", f"{a}{b}"])


VARIANTS = False   # held-out only: document variants the extractor was not written for


def _p(rng, psig, allow_abs=False):
    """Render a gauge pressure in a random unit."""
    u = rng.choice(["psig", "psig", "barg", "kPa(g)"] + (["psia"] if allow_abs else []) + (["kg/cm2(g)"] if VARIANTS else []))
    if u == "kg/cm2(g)":
        return f"{psig / 14.2233:.2f} kg/cm2(g)"
    if u == "psig":
        return f"{psig:,.0f} psig"
    if u == "barg":
        return f"{psig / BAR:.2f} barg"
    if u == "kPa(g)":
        return f"{psig / BAR * 100:,.0f} kPa(g)"
    return f"{psig + ATM:,.1f} psia"


def _t(rng, f):
    return rng.choice([f"{f:.0f} °F", f"{(f - 32) * 5 / 9:.0f} °C"])


def make(seed: int, variants: bool = False):
    global VARIANTS
    VARIANTS = variants
    rng = random.Random(seed)
    truth, looks = [], []
    docs = {}
    plant = rng.sample(DEFECTS, rng.randint(2, 5))
    alike = rng.sample(LOOKALIKES, rng.randint(3, 6))
    spec_ed, or_later = rng.choice([11, 12]), rng.random() < 0.5
    if "EDITION_OR_LATER" in alike:
        spec_ed, or_later = 11, True
    if "CODE_EDITION" in plant:
        or_later = rng.random() < 0.5

    # ---- vessels + PSVs ----
    vessels, psvs = [], []
    for i in range(rng.randint(3, 5)):
        tag = f"V-1{i + 1:02d}"
        dp = rng.choice(range(150, 600, 25))
        mawp = dp if rng.random() < 0.4 else round(dp * rng.uniform(1.05, 1.15))
        dt = rng.choice(range(200, 650, 50))
        op = round(dp * rng.uniform(0.55, 0.75))
        vessels.append({"tag": tag, "dp": dp, "mawp": mawp, "dt": dt, "op": op, "op_abs": False})
        n_valves = 2 if rng.random() < 0.3 else 1
        for k in range(n_valves):
            psvs.append({"tag": f"PSV-1{i + 1:02d}{'AB'[k]}", "vessel": tag, "sp": dp if k == 0 else round(dp * 1.0),
                         "service": "process", "ref_rev": "C"})
    # ---- lines ----
    lines = []
    for i in range(rng.randint(4, 7)):
        cls = rng.choice([150, 300])
        t = rng.choice(range(100, 650, 50))
        p = round(rating(cls, t) * rng.uniform(0.5, 0.85))
        lines.append({"tag": f'{rng.choice([2, 3, 4, 6, 8])}"-P-{1001 + i}-{"A1" if cls == 150 else "B1"}', "cls": cls, "dt": t, "dp": p})
    # ---- pumps ----
    pumps = []
    for i in range(rng.randint(2, 3)):
        flow = rng.choice(range(40, 400, 10))
        npsha = rng.uniform(15, 40)
        power = round(flow * rng.uniform(0.15, 0.4), 1)
        mot_req = power * (1.25 if power < 22 else 1.15 if power <= 55 else 1.10)
        motor = round(mot_req * rng.uniform(1.05, 1.3), 1)
        pumps.append({"tag": f"P-1{i + 1:02d}A", "flow": flow, "rated": round(flow * rng.uniform(1.12, 1.25)),
                      "npsha": round(npsha, 1), "npshr": round(min(npsha / 1.25, npsha - 4), 1),
                      "power": power, "motor": motor, "ed": spec_ed if not or_later else rng.choice([spec_ed, spec_ed + 1] if spec_ed < 12 else [12])})
    # ---- transformers + loads ----
    xfmrs, loads = [], []
    for i in range(2):
        onan = rng.choice([1000, 1500, 2000, 2500])
        onaf = round(onan * (1.15 if onan <= 2000 else 1.25))
        xfmrs.append({"tag": f"T-{i + 1}", "onan": onan, "onaf": onaf})
        target = onan * rng.uniform(0.6, 0.85)
        dem, j = 0.0, 0
        while dem < target:
            duty = rng.choice("CCCIS")
            kw = rng.choice([15, 22, 30, 45, 55, 75, 90, 110, 150])
            pf = rng.choice([0.8, 0.85, 0.9])
            loads.append({"tag": f"M-{i + 1}{j:02d}", "bus": f"T-{i + 1}", "kw": kw, "pf": pf, "duty": duty})
            dem += kw / pf * {"C": 1.0, "I": 0.3, "S": 0.0}[duty]
            j += 1

    def demand(t):
        return sum(l["kw"] / l["pf"] * {"C": 1.0, "I": 0.3, "S": 0.0}[l["duty"]] for l in loads if l["bus"] == t)

    def add_load(t, kva, duty):
        loads.append({"tag": f"M-{t[-1]}9{len(loads) % 10}", "bus": t, "kw": round(kva * 0.85), "pf": 0.85, "duty": duty})

    # ---- plant defects ----
    for d in plant:
        if d == "PSV_SET_OVER_MAWP":
            # only single-valve vessels: with two valves, one may legally sit up to 105% MAWP
            single = [v for v in vessels if sum(p["vessel"] == v["tag"] for p in psvs) == 1]
            if not single:
                continue
            v = rng.choice(single)
            s = next(p for p in psvs if p["vessel"] == v["tag"])
            s["sp"] = round(v["mawp"] * rng.uniform(1.03, 1.08))
            truth.append((d, s["tag"]))
        elif d == "PSV_ADDL_OVER_105":
            cands = [p for p in psvs if p["tag"].endswith("B")]
            if not cands:
                v = rng.choice(vessels)
                cands = [{"tag": v["tag"].replace("V", "PSV") + "B", "vessel": v["tag"], "sp": v["dp"], "service": "process", "ref_rev": "C"}]
                psvs.append(cands[0])
            s = cands[0]
            v = next(x for x in vessels if x["tag"] == s["vessel"])
            s["sp"] = round(v["mawp"] * rng.uniform(1.07, 1.10))
            truth.append((d, s["tag"]))
        elif d == "OP_TOO_CLOSE_TO_SET":
            v = rng.choice(vessels)
            s = next(p for p in psvs if p["vessel"] == v["tag"])
            v["op"] = round(min(s["sp"], v["mawp"]) * rng.uniform(0.93, 0.97))
            truth.append((d, v["tag"]))
        elif d == "PIPE_CLASS_DERATED":
            l = rng.choice(lines)
            l["dt"] = rng.choice([400, 500, 600])
            r100, rt = rating(l["cls"], 100), rating(l["cls"], l["dt"])
            l["dp"] = round(rng.uniform(rt * 1.05, min(r100 * 0.95, rt * 1.3)))
            truth.append((d, l["tag"]))
        elif d == "XFMR_OVER_ONAF":
            x = rng.choice(xfmrs)
            add_load(x["tag"], x["onaf"] * rng.uniform(1.05, 1.2) - demand(x["tag"]), "C")
            truth.append((d, x["tag"]))
        elif d == "CODE_EDITION":
            spec_ed = 12
            p = rng.choice(pumps)
            p["ed"] = 11
            truth.append((d, p["tag"]))
        elif d == "MOTOR_MARGIN":
            p = rng.choice(pumps)
            req = p["power"] * (1.25 if p["power"] < 22 else 1.15 if p["power"] <= 55 else 1.10)
            p["motor"] = round(rng.uniform(p["power"] * 1.01, req * 0.97), 1)
            truth.append((d, p["tag"]))
        elif d == "NPSH_MARGIN":
            p = rng.choice(pumps)
            p["npshr"] = round(p["npsha"] / rng.uniform(1.0, 1.07), 1)
            truth.append((d, p["tag"]))
        elif d == "RATED_FLOW_MARGIN":
            p = rng.choice(pumps)
            p["rated"] = round(p["flow"] * rng.uniform(1.0, 1.07))
            truth.append((d, p["tag"]))
        elif d == "STALE_REF":
            s = rng.choice(psvs)
            s["ref_rev"] = "B"
            truth.append((d, s["tag"]))
    if "CODE_EDITION" in plant:
        for p in pumps:
            if (("CODE_EDITION", p["tag"]) not in truth) and p["ed"] < spec_ed:
                p["ed"] = spec_ed
    planted_tags = {t for _, t in truth}

    # ---- plant look-alikes (only on items without a planted defect) ----
    for a in alike:
        if a == "SET_ABOVE_DESIGN_BELOW_MAWP":
            vs = [v for v in vessels if v["mawp"] >= v["dp"] * 1.05 and v["tag"] not in planted_tags]
            for v in vs[:1]:
                s = next(p for p in psvs if p["vessel"] == v["tag"])
                if s["tag"] in planted_tags:
                    continue
                s["sp"] = round(rng.uniform(v["dp"] * 1.01, v["mawp"]))
                looks.append((a, s["tag"]))
        elif a == "ADDL_VALVE_WITHIN_105":
            for s in [p for p in psvs if p["tag"].endswith("B") and p["tag"] not in planted_tags][:1]:
                v = next(x for x in vessels if x["tag"] == s["vessel"])
                s["sp"] = round(v["mawp"] * rng.uniform(1.01, 1.045))
                looks.append((a, s["tag"]))
        elif a == "FIRE_VALVE_WITHIN_110":
            v = rng.choice([v for v in vessels if v["tag"] not in planted_tags] or vessels)
            s = {"tag": v["tag"].replace("V", "PSV") + "F", "vessel": v["tag"], "sp": round(v["mawp"] * rng.uniform(1.06, 1.095)),
                 "service": "fire", "ref_rev": "C"}
            psvs.append(s)
            looks.append((a, s["tag"]))
        elif a == "OP_IN_PSIA":
            for v in [v for v in vessels if v["tag"] not in planted_tags][:1]:
                s = next(p for p in psvs if p["vessel"] == v["tag"])
                lim = min(s["sp"], v["mawp"])
                v["op"] = round(lim * rng.uniform(0.86, 0.89))   # OK as gauge, but +14.7 crosses 90 %
                if v["op"] + ATM > 0.9 * lim:
                    v["op_abs"] = True
                    looks.append((a, v["tag"]))
        elif a == "CONNECTED_OVER_ONAN_DEMAND_OK":
            for x in [x for x in xfmrs if x["tag"] not in planted_tags][:1]:
                conn = sum(l["kw"] / l["pf"] for l in loads if l["bus"] == x["tag"])
                add_load(x["tag"], max(50, x["onan"] * 1.1 - conn), "S")   # standby spare: connected, not demand
                looks.append((a, x["tag"]))
        elif a == "EDITION_OR_LATER":
            for p in pumps:
                if p["tag"] not in planted_tags:
                    p["ed"] = 12
                    looks.append((a, p["tag"]))
                    break
        elif a == "MIXED_UNITS_AGREE":
            looks.append((a, "*"))      # units are always mixed; marker only
        elif a == "HOT_LINE_WITHIN_RATING":
            for l in [l for l in lines if l["tag"] not in planted_tags][:1]:
                l["dt"] = rng.choice([500, 600])
                l["dp"] = round(rating(l["cls"], l["dt"]) * rng.uniform(0.85, 0.97))
                looks.append((a, l["tag"]))

    # ---- render documents ----
    spec = [f"PROJECT SPECIFICATION SP-MECH-001 rev 2",
            f"Centrifugal pumps shall comply with API 610 {spec_ed}th Edition{' or later' if or_later else ''}.",
            "Pump rated flow shall be not less than 110% of normal flow.",
            "NPSH margin: NPSHa shall be at least 1.1 x NPSHr and at least NPSHr + 3 ft.",
            "Driver rating per API 610: 125% of rated power below 22 kW, 115% for 22-55 kW, 110% above 55 kW.",
            "Maximum demand: continuous loads 100%, intermittent 30%, standby 0%.",
            "Normal operating pressure shall not exceed 90% of the lowest relief set pressure."]
    docs["spec.txt"] = "\n".join(spec)
    docs["register.txt"] = "DOCUMENT REGISTER\nP&ID-001  rev C  issued for construction\nP&ID-002  rev A"
    docs["pipe_spec.txt"] = ("PIPING MATERIAL SPECIFICATION\nClass A1: ASME B16.5 Class 150, carbon steel ASTM A105 (Group 1.1)\n"
                             "Class B1: ASME B16.5 Class 300, carbon steel ASTM A105 (Group 1.1)")
    out = ["MECHANICAL DATASHEETS - PRESSURE VESSELS"]
    for v in vessels:
        if variants and rng.random() < 0.3:
            out += [f"Item: {_tag(rng, v['tag'])} | Design pressure (barg): {v['dp'] / BAR:.2f} | "
                    f"Max. allowable working pressure (barg): {v['mawp'] / BAR:.2f} | Design temp (degF): {v['dt']}", ""]
        elif rng.random() < 0.5:
            out += [f"Tag No.: {_tag(rng, v['tag'])}", f"Design Pressure: {_p(rng, v['dp'])}",
                    f"Design Temperature: {_t(rng, v['dt'])}", f"MAWP (hot & corroded): {_p(rng, v['mawp'])}", ""]
        else:
            out += [f"VESSEL {_tag(rng, v['tag'])}", f"DES. PRESS. ...... {_p(rng, v['dp'])}",
                    f"DES. TEMP ........ {_t(rng, v['dt'])}", f"M.A.W.P. ........ {_p(rng, v['mawp'])}", ""]
    docs["vessel_datasheets.txt"] = "\n".join(out)
    out = ["PROCESS DATASHEET v3"]
    for v in vessels:
        op = f"{v['op'] + ATM:,.1f} psia" if v["op_abs"] else _p(rng, v["op"])
        out.append(f"{_tag(rng, v['tag'])}: normal operating pressure {op}")
    for p in pumps:
        out.append(f"{_tag(rng, p['tag'])}: normal flow {p['flow']} m3/h; NPSHa {p['npsha']} ft")
    docs["process_datasheet.txt"] = "\n".join(out)
    reorder = variants and rng.random() < 0.3
    out = [["Tag", "Set pressure", "Protects", "Reference", "Service"] if reorder else ["Tag", "Protects", "Set pressure", "Service", "Reference"]]
    for s in psvs:
        row = [_tag(rng, s["tag"]), _tag(rng, s["vessel"]), _p(rng, s["sp"]), s["service"], f"P&ID-001 rev {s['ref_rev']}"]
        out.append([row[0], row[2], row[1], row[4], row[3]] if reorder else row)
    docs["psv_list.csv"] = _csv(out)
    out = [["Line No", "Design Press", "Design Temp", "Pipe Class"]]
    for l in lines:
        out.append([l["tag"], _p(rng, l["dp"]), _t(rng, l["dt"]), "A1" if l["cls"] == 150 else "B1"])
    docs["line_list.csv"] = _csv(out)
    for p in pumps:
        pw = rng.choice([f"{p['power']} kW", f"{p['power'] / 0.7457:.1f} hp"])
        mw = rng.choice([f"{p['motor']} kW", f"{p['motor'] / 0.7457:.0f} hp"])
        flow = rng.choice([f"{p['rated']} m3/h", f"{p['rated'] / 0.22712:.0f} gpm"])
        docs[f"vendor_{p['tag']}.txt"] = (f"VENDOR PUMP DATASHEET {_tag(rng, p['tag'])}\nRated flow: {flow}\nNPSHr: {p['npshr']} ft\n"
                                          f"Rated power: {pw}\nDriver rating: {mw}\nDesign to API 610 {p['ed']}th Edition")
    out = ["TRANSFORMER DATASHEETS"]
    for x in xfmrs:
        out.append(rng.choice([f"{x['tag']}: rating {x['onan']:,}/{x['onaf']:,} kVA ONAN/ONAF",
                               f"{x['tag']}: ONAN {x['onan'] / 1000:.2f} MVA, ONAF {x['onaf'] / 1000:.3f} MVA"]
                              + ([f"{x['tag']}: {x['onan']} kVA (ONAN) / {x['onaf']} kVA (ONAF)"] if variants else [])))
    docs["transformers.txt"] = "\n".join(out)
    out = ["Tag,Bus,kW,PF,Duty"]
    for l in loads:
        duty = {"C": rng.choice(["C", "Continuous"]), "I": rng.choice(["I", "Intermittent"]), "S": rng.choice(["S", "Standby"])}[l["duty"]]
        out.append(f"{l['tag']},{l['bus']},{l['kw']},{l['pf']},{duty}")
    docs["load_list.csv"] = "\n".join(out)
    return {"docs": docs, "truth": sorted(set(truth)), "lookalikes": looks}
