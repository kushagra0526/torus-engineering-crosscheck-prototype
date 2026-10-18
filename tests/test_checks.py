import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from crosscheck.checks import aware, extract, literal
from crosscheck.project import make, rating
from crosscheck.units import parse

SPEC = ("PROJECT SPECIFICATION\nCentrifugal pumps shall comply with API 610 11th Edition or later.\n"
        "Maximum demand: continuous loads 100%, intermittent 30%, standby 0%.")


def docs(vessel, psvs, op="300 psig", xf="T-1: rating 2,000/2,300 kVA ONAN/ONAF", loads=(), pump=None):
    d = {
        "spec.txt": SPEC,
        "register.txt": "DOCUMENT REGISTER\nP&ID-001  rev C",
        "pipe_spec.txt": "PIPING MATERIAL SPECIFICATION\nClass A1: ASME B16.5 Class 150, carbon steel",
        "vessel_datasheets.txt": "MECH\n" + vessel,
        "process_datasheet.txt": f"PROCESS\nV-101: normal operating pressure {op}",
        "psv_list.csv": "Tag,Protects,Set pressure,Service,Reference\n" + "\n".join(psvs),
        "line_list.csv": 'Line No,Design Press,Design Temp,Pipe Class\n4"-P-1001-A1,250 psig,400 °F,A1',
        "transformers.txt": "TRANSFORMERS\n" + xf,
        "load_list.csv": "Tag,Bus,kW,PF,Duty\n" + "\n".join(loads),
    }
    return d


V = "Tag No.: V-101\nDesign Pressure: 450 psig\nDesign Temperature: 400 °F\nMAWP (hot & corroded): 495 psig"


class TestRules(unittest.TestCase):
    def rules(self, d):
        return {(f["rule"], f["tag"]) for f in aware(d)[0]}

    def test_set_above_design_but_below_mawp_is_fine(self):
        d = docs(V, ["PSV-101A,V-101,465 psig,process,P&ID-001 rev C"])
        self.assertNotIn(("PSV_SET_OVER_MAWP", "PSV-101A"), self.rules(d))
        self.assertIn(("PSV_SET_OVER_MAWP", "PSV-101A"), {(f["rule"], f["tag"]) for f in literal(d)})

    def test_set_above_mawp_and_second_valve_105(self):
        d = docs(V, ["PSV-101A,V-101,505 psig,process,P&ID-001 rev C"])
        self.assertIn(("PSV_SET_OVER_MAWP", "PSV-101A"), self.rules(d))
        d = docs(V, ["PSV-101A,V-101,450 psig,process,P&ID-001 rev C", "PSV-101B,V-101,515 psig,process,P&ID-001 rev C"])
        self.assertNotIn(("PSV_ADDL_OVER_105", "PSV-101B"), self.rules(d))       # 515 < 1.05 x 495
        d = docs(V, ["PSV-101A,V-101,450 psig,process,P&ID-001 rev C", "PSV-101B,V-101,525 psig,process,P&ID-001 rev C"])
        self.assertIn(("PSV_ADDL_OVER_105", "PSV-101B"), self.rules(d))

    def test_psia_is_converted(self):
        d = docs(V, ["PSV-101A,V-101,465 psig,process,P&ID-001 rev C"], op="430 psia")   # 415 psig < 0.9 x 465
        self.assertNotIn(("OP_TOO_CLOSE_TO_SET", "V-101"), self.rules(d))

    def test_pipe_rating_derates_with_temperature(self):
        self.assertEqual(rating(150, 100), 285)
        self.assertEqual(rating(150, 400), 200)
        d = docs(V, ["PSV-101A,V-101,450 psig,process,P&ID-001 rev C"])
        self.assertIn(('PIPE_CLASS_DERATED', '4"-P-1001-A1'), self.rules(d))   # 250 psig at 400 F > 200

    def test_transformer_uses_demand_and_onaf(self):
        loads = ["M-1,T-1,1700,0.85,C", "M-2,T-1,1000,0.85,Standby"]   # connected 3,176 kVA; demand 2,000
        d = docs(V, [], loads=loads)
        f, w = aware(d)
        self.assertFalse([x for x in f if x["rule"] == "XFMR_OVER_ONAF"])
        self.assertTrue([x for x in literal(d) if x["rule"] == "XFMR_OVER_ONAF"])

    def test_stale_reference(self):
        d = docs(V, ["PSV-101A,V-101,450 psig,process,P&ID-001 rev B"])
        self.assertIn(("STALE_REF", "PSV-101A"), self.rules(d))

    def test_unreadable_value_is_reported_not_passed(self):
        d = docs(V, [], xf="T-1: some unknown rating format", loads=["M-1,T-1,100,0.85,C"])
        f, w = aware(d)
        self.assertTrue([x for x in w if x["rule"] == "UNREAD" and x["tag"] == "T-1"])

    def test_units(self):
        self.assertAlmostEqual(parse("115 psia")[0], 100.304, places=3)
        self.assertAlmostEqual(parse("31.0 barg")[0], 449.6, places=1)


class TestGenerated(unittest.TestCase):
    def test_dev_projects_extract(self):
        for s in range(1, 6):
            M = extract(make(s)["docs"])
            self.assertTrue(M["vessel"] and M["psv"] and M["pump"])


if __name__ == "__main__":
    unittest.main()
