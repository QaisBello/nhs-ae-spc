"""The dashboard's JavaScript SPC must give exactly the same answers as src/spc.py, on every real series."""
import json
import os
import shutil
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from spc import assurance, spc  # noqa: E402

NODE = shutil.which("node")


def js_spc():
    html = open(os.path.join(ROOT, "web", "template.html"), encoding="utf-8").read()
    return html.split("/*SPC-START*/")[1].split("/*SPC-END*/")[0]


def cases():
    t = pd.read_csv(os.path.join(ROOT, "data", "clean", "ae_monthly.csv"))
    out = []
    for code, g in t[t.provider_type == "Major A&E (Type 1)"].groupby("org_code"):
        g = g.sort_values("month")
        y = (100 * (1 - g.over_4hrs / g.attendances)).round(6).tolist()
        out.append(dict(x=g.month.tolist(), y=y, dir="increase", rebase=["2022-04"]))
        out.append(dict(x=g.month.tolist(), y=g.dta_12hr_plus.astype(float).tolist(), dir="decrease", rebase=[]))
    return out


@pytest.mark.skipif(NODE is None, reason="node not installed")
def test_js_and_python_agree_on_every_trust():
    cs = cases()
    script = js_spc() + """
const cs=JSON.parse(require('fs').readFileSync(0,'utf8'));
console.log(JSON.stringify(cs.map(c=>{const p=SPC.spc(c.x,c.y,c.dir,c.rebase);
  return {v:p.map(d=>d.variation),r:p.map(d=>d.rule),m:p.map(d=>d.mean),u:p.map(d=>d.upl),a:SPC.assurance(p,82,c.dir)};})));"""
    r = subprocess.run([NODE, "-e", script], input=json.dumps(cs), capture_output=True, text=True, check=True)
    js = json.loads(r.stdout)
    assert len(js) == len(cs) > 200
    for c, j in zip(cs, js):
        p = spc(c["x"], c["y"], c["dir"], c["rebase"])
        assert j["v"] == [d.variation for d in p]
        assert j["r"] == [d.rule for d in p]
        assert j["m"] == pytest.approx([d.mean for d in p])
        assert j["u"] == pytest.approx([d.upl for d in p])
        assert j["a"] == assurance(p, 82, c["dir"])
