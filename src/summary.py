"""Make Data Count summary: an SPC chart for every major A&E trust, region and England, read the way an
NHS board report reads them: what the latest point says (variation) and whether the target will be hit (assurance).

Window: the last 24 months (Making Data Count recommends at least 20 points for reliable limits).
Targets: 82% within four hours for 2026/27 (the interim target in the Urgent and Emergency Care Plan),
95% being the constitutional standard.

Writes data/clean/spc_summary.csv and data/clean/summary.json (headline figures for the dashboard and README).
"""
import json
import os

import pandas as pd

from spc import assurance, spc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "data", "clean")
WINDOW, TARGET = 24, 82.0

# measure -> (improvement direction, target)
MEASURES = {"pct_4hr": ("increase", TARGET), "pct_4hr_type1": ("increase", None),
            "dta_12hr_plus": ("decrease", None), "attendances": ("neutral", None)}


def pct(df):
    df = df.copy()
    df["pct_4hr"] = 100 * (1 - df.over_4hrs / df.attendances)
    df["pct_4hr_type1"] = 100 * (1 - df.type1_over_4hrs / df.type1_attendances)
    return df


def summarise(level, code, name, region, g, months):
    g = g.set_index("month").reindex(months)
    row = dict(level=level, code=code, name=name, region=region)
    for m, (direction, target) in MEASURES.items():
        y = g[m]
        if y.isna().any():
            return None                       # needs a complete run of months
        pts = spc(months, [float(v) for v in y], improvement=direction)
        last = pts[-1]
        row[f"{m}_latest"] = round(last.y, 2)
        row[f"{m}_mean"] = round(last.mean, 2)
        row[f"{m}_lpl"], row[f"{m}_upl"] = round(last.lpl, 2), round(last.upl, 2)
        row[f"{m}_variation"] = last.variation
        row[f"{m}_special_6m"] = sum(p.variation not in ("common_cause",) for p in pts[-6:])
        if target is not None:
            row[f"{m}_assurance"] = assurance(pts, target, direction)
    return row


def main():
    t = pd.read_csv(os.path.join(CLEAN, "ae_monthly.csv"))
    months = sorted(t.month.unique())[-WINDOW:]
    rows = []

    eng = pct(pd.read_csv(os.path.join(CLEAN, "england.csv")))
    rows.append(summarise("England", "ENG", "England", "", eng, months))
    reg = pct(pd.read_csv(os.path.join(CLEAN, "regions.csv")))
    for r, g in reg.groupby("region"):
        rows.append(summarise("Region", r, r, r, g, months))

    major = t[(t.provider_type == "Major A&E (Type 1)") & t.month.isin(months)]
    names = t.sort_values("month").groupby("org_code").last()
    for code, g in pct(major).groupby("org_code"):
        if g.type1_attendances.min() == 0:
            continue                          # Type 1 rate undefined in some month (e.g. department closed)
        rows.append(summarise("Trust", code, names.org_name[code], names.region[code], g, months))

    out = pd.DataFrame([r for r in rows if r])
    out.to_csv(os.path.join(CLEAN, "spc_summary.csv"), index=False)

    trusts = out[out.level == "Trust"]
    e = out.iloc[0]
    eng_all = eng.set_index("month")
    fy = lambda a, b: eng_all.loc[a:b]
    def fy_pct(a, b):
        f = fy(a, b)
        return round(100 * (1 - f.over_4hrs.sum() / f.attendances.sum()), 1)
    summary = dict(
        window=[months[0], months[-1]], target=TARGET,
        england_latest=round(e.pct_4hr_latest, 1), england_latest_month=months[-1],
        england_mean=round(e.pct_4hr_mean, 1), england_upl=round(e.pct_4hr_upl, 1), england_lpl=round(e.pct_4hr_lpl, 1),
        england_assurance=e.pct_4hr_assurance, england_variation=e.pct_4hr_variation,
        fy_2025_26=fy_pct("2025-04", "2026-03"), fy_2024_25=fy_pct("2024-04", "2025-03"),
        fy_2026_27_to_date=fy_pct("2026-04", months[-1]),
        trusts=int(len(trusts)),
        trusts_consistent_fail=int((trusts.pct_4hr_assurance == "fail").sum()),
        trusts_consistent_pass=int((trusts.pct_4hr_assurance == "pass").sum()),
        trusts_inconsistent=int((trusts.pct_4hr_assurance == "inconsistent").sum()),
        trusts_improving=int((trusts.pct_4hr_variation == "improvement").sum()),
        trusts_concern=int((trusts.pct_4hr_variation == "concern").sum()),
        trusts_above_target_latest=int((trusts.pct_4hr_latest >= TARGET).sum()),
        dta12_first=int(eng_all.dta_12hr_plus.iloc[0]), dta12_first_month=eng_all.index[0],
        dta12_latest=int(eng_all.dta_12hr_plus.iloc[-1]),
        dta12_last12=int(eng_all.dta_12hr_plus.iloc[-12:].sum()),
        dta12_prev12=int(eng_all.dta_12hr_plus.iloc[-24:-12].sum()),
    )
    with open(os.path.join(CLEAN, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    print(out.groupby("level").size().to_string())


if __name__ == "__main__":
    main()
