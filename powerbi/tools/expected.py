"""What the Power BI report should show, recomputed in pandas with the same rules as the DAX, and checked against
the Python SPC (src/spc.py, via data/clean/spc_summary.csv). Run from powerbi/:

    python tools/expected.py        # writes docs/expected_values.md; exit code 1 if DAX logic and Python SPC disagree
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(os.path.dirname(ROOT), "data", "clean")
WINDOW, LIMIT, SCREEN, TARGET = 24, 2.66, 3.267, 0.82

eng = pd.read_csv(os.path.join(CLEAN, "england.csv")).assign(code="ENG")
reg = pd.read_csv(os.path.join(CLEAN, "regions.csv")).rename(columns={"region": "code"})
tr = pd.read_csv(os.path.join(CLEAN, "ae_monthly.csv"))
tr = tr[tr.provider_type == "Major A&E (Type 1)"].rename(columns={"org_code": "code"})
monthly = pd.concat([eng, reg, tr])[["code", "month", "attendances", "over_4hrs", "dta_12hr_plus"]]
ent = pd.read_csv(os.path.join(CLEAN, "spc_summary.csv"))
months = sorted(eng.month)
window = months[-WINDOW:]


def dax_like(code):
    g = monthly[monthly.code == code].groupby("month")[["attendances", "over_4hrs"]].sum()
    pct = (g.attendances - g.over_4hrs) / g.attendances
    v = pct.reindex(window)
    mean = v.mean()
    mr = v.diff().abs().iloc[1:]
    amr = mr.mean()
    kept = mr[mr < SCREEN * amr]
    amr = kept.mean() if len(kept) else amr
    return dict(latest=pct.get(months[-1]), mean=mean, lpl=mean - LIMIT * amr, upl=mean + LIMIT * amr)


rows, bad = [], []
for _, e in ent.iterrows():
    d = dax_like(e.code)
    rows.append({**e[["level", "code", "name", "pct_4hr_variation", "pct_4hr_assurance"]].to_dict(), **d})
    for k in ("mean", "lpl", "upl"):
        if abs(100 * d[k] - e[f"pct_4hr_{k}"]) > 0.006:
            bad.append(f"{e['name']} {k}: DAX logic {100 * d[k]:.3f} vs Python SPC {e[f'pct_4hr_{k}']}")
    if abs(100 * d["latest"] - e.pct_4hr_latest) > 0.006:
        bad.append(f"{e['name']} latest: {100 * d['latest']:.3f} vs {e.pct_4hr_latest}")
out = pd.DataFrame(rows)
dax_assure = out.apply(lambda r: "fail" if TARGET > r.upl else "pass" if TARGET < r.lpl else "inconsistent", axis=1)
mismatch = (dax_assure != out.pct_4hr_assurance).sum()
trusts = out[out.level == "Trust"]
e = out.iloc[0]
lines = ["# Expected values", "",
         "From `tools/expected.py`: the DAX logic recomputed in pandas, and checked against the Python SPC in `src/spc.py`.", "",
         f"Process limits for all {len(out)} entities (England, 7 regions, {len(trusts)} trusts) match the Python SPC to 0.01 points: "
         f"**{'yes' if not bad else 'NO, ' + str(len(bad)) + ' differences'}**. DAX assurance agrees with Python for "
         f"{len(out) - mismatch} of {len(out)}.", "",
         "## Page 1, nothing selected (England)", "", "| Card | Expected |", "|---|---:|",
         f"| Latest month ({months[-1]}) | {e.latest:.1%} |", f"| Mean, last 24 months | {e['mean']:.1%} |",
         f"| Lower process limit | {e.lpl:.1%} |", f"| Upper process limit | {e.upl:.1%} |",
         f"| Assurance | {e.pct_4hr_assurance} |", "",
         "## Page 2", "", "| Card | Expected |", "|---|---:|",
         f"| Trusts that will consistently miss 82% | {(trusts.pct_4hr_assurance == 'fail').sum()} |",
         f"| Trusts improving | {(trusts.pct_4hr_variation == 'improvement').sum()} |",
         f"| Trusts of concern | {(trusts.pct_4hr_variation == 'concern').sum()} |", "",
         "Top 5 trusts, latest month:", "", "| Trust | Latest | Mean | Lower | Upper |", "|---|---:|---:|---:|---:|"]
lines += [f"| {r['name']} | {r.latest:.1%} | {r['mean']:.1%} | {r.lpl:.1%} | {r.upl:.1%} |" for _, r in trusts.sort_values("latest", ascending=False).head(5).iterrows()]
lines += ["", "Regions, latest month:", "", "| Region | Latest |", "|---|---:|"]
lines += [f"| {r['name']} | {r.latest:.1%} |" for _, r in out[out.level == "Region"].sort_values("latest", ascending=False).iterrows()]
os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
open(os.path.join(ROOT, "docs", "expected_values.md"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines[:22]))
for b in bad[:20]:
    print("DIFF", b)
sys.exit(1 if bad else 0)
