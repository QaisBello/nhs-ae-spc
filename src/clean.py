"""Clean NHS England's monthly A&E Attendances and Emergency Admissions files (data/raw) into tidy tables.

Source: NHS England, A&E Attendances and Emergency Admissions, monthly provider-level CSVs, Jan 2020 – Sep 2026.
https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/

The files are not consistent over time: columns were renamed, booked-appointment columns were added,
one month carries stray empty columns, a TOTAL row sits among the providers, region names carry
trailing spaces, and the same month can be downloaded twice. Every fix is logged.

Outputs (data/clean):
  ae_monthly.csv        one row per provider per month, standard column names
  england.csv           England totals per month (recomputed from providers, checked against the TOTAL row)
  regions.csv           totals per NHS England region per month
  data_quality_log.csv  every check and fix
"""
import glob
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, OUT = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "data", "clean")
LOG = []

# every name the source has used for each measure -> one standard name
RENAME = {
    "Number of A&E attendances Type 1": "att_type1", "A&E attendances Type 1": "att_type1",
    "Number of A&E attendances Type 2": "att_type2", "A&E attendances Type 2": "att_type2",
    "Number of A&E attendances Other A&E Department": "att_other", "A&E attendances Other A&E Department": "att_other",
    "A&E attendances Booked Appointments Type 1": "att_booked_type1",
    "A&E attendances Booked Appointments Type 2": "att_booked_type2",
    "A&E attendances Booked Appointments Other Department": "att_booked_other",
    "Number of attendances over 4hrs Type 1": "over4_type1", "Attendances over 4hrs Type 1": "over4_type1",
    "Number of attendances over 4hrs Type 2": "over4_type2", "Attendances over 4hrs Type 2": "over4_type2",
    "Number of attendances over 4hrs Other A&E Department": "over4_other", "Attendances over 4hrs Other Department": "over4_other",
    "Attendances over 4hrs Booked Appointments Type 1": "over4_booked_type1",
    "Attendances over 4hrs Booked Appointments Type 2": "over4_booked_type2",
    "Attendances over 4hrs Booked Appointments Other Department": "over4_booked_other",
    "Patients who have waited 4-12 hs from DTA to admission": "dta_4_12hr",
    "Patients who have waited 12+ hrs from DTA to admission": "dta_12hr_plus",
    "Emergency admissions via A&E - Type 1": "adm_type1", "Emergency admissions via A&E - Type 2": "adm_type2",
    "Emergency admissions via A&E - Other A&E department": "adm_other", "Other emergency admissions": "adm_other_route",
}
MEASURES = sorted(set(RENAME.values()))


SMALL = {"and", "of", "the", "for", "in", "on", "at", "with"}
KEEP = {"NHS", "NHSFT", "UK", "UCLH", "WIC", "UTC", "MIU", "UCC", "GP", "CIC", "PCN", "ICB", "CCG", "LLP", "LTD", "IOW", "HCA"}


def nice_name(name):
    """'WIRRAL UNIVERSITY TEACHING HOSPITAL NHS FOUNDATION TRUST' -> 'Wirral University Teaching Hospital NHS Foundation Trust'."""
    if not isinstance(name, str) or name != name.upper():
        return name
    words = []
    for i, w in enumerate(name.split()):
        if w in KEEP:
            words.append(w)
        elif i and w.lower() in SMALL:
            words.append(w.lower())
        else:
            words.append("-".join(p[:1] + p[1:].lower() for p in w.split("-")).replace("'S", "'s"))
    return " ".join(words)


def log(check, rows, finding, action):
    LOG.append(dict(check=check, rows_affected=int(rows), finding=finding, action=action))


def main():
    os.makedirs(OUT, exist_ok=True)
    frames, seen, layouts = [], {}, {}
    files = sorted(glob.glob(os.path.join(RAW, "*.csv")))
    log("Files read", len(files), f"{len(files)} monthly CSV files as downloaded", "-")
    for f in files:
        d = pd.read_csv(f, dtype=str)
        d.columns = [c.strip() for c in d.columns]
        stray = [c for c in d.columns if c.startswith("Unnamed") or c == "a"]
        if stray:
            log("Stray columns", len(d), f"{os.path.basename(f)}: {len(stray)} empty columns with no header", "Dropped")
            d = d.drop(columns=stray)
        layouts.setdefault(len(d.columns), []).append(os.path.basename(f))
        period = d.Period[d.Period.str.startswith("MSitAE-", na=False)].iloc[0]
        d["Period"] = period            # the TOTAL row carries "Total" instead of the month
        if period in seen:
            log("Duplicate month", len(d), f"{os.path.basename(f)} repeats {period} (also in {seen[period]})", "Skipped")
            continue
        seen[period] = os.path.basename(f)
        unknown = set(d.columns) - set(RENAME) - {"Period", "Org Code", "Parent Org", "Org name"}
        assert not unknown, f"unmapped columns in {f}: {unknown}"
        d = d.rename(columns=RENAME)
        d["source_file"] = os.path.basename(f)
        frames.append(d)
    log("Column layouts", len(layouts), "; ".join(f"{k} columns in {len(v)} files" for k, v in sorted(layouts.items())),
        "Mapped every name the source has used to one standard set")

    df = pd.concat(frames, ignore_index=True)
    df["month"] = pd.to_datetime(df.Period.str.replace("MSitAE-", "", regex=False).str.title(), format="%B-%Y").dt.strftime("%Y-%m")
    for c in ("Org Code", "Parent Org", "Org name"):
        n = (df[c] != df[c].str.strip()).sum()
        df[c] = df[c].str.strip()
        if n:
            log(f"Whitespace in {c}", n, "Trailing spaces in names", "Trimmed")
    for c in MEASURES:
        if c not in df:
            df[c] = None
    before_missing = df[[c for c in MEASURES if not c.startswith(("att_booked", "over4_booked"))]].isna().sum().sum()
    df[MEASURES] = df[MEASURES].apply(lambda s: pd.to_numeric(s.str.replace(",", "", regex=False), errors="coerce")).fillna(0).astype(int)
    early = [f for k, v in layouts.items() if k == 16 for f in v]
    log("Booked-appointment columns", df.source_file.isin(early).sum(),
        "Booked appointments were not reported separately in Jan-Jul 2020 files", "Set to 0 for those months; totals unaffected")

    # the TOTAL row is flagged in Org Code from April 2020, but only in Org name (code blank) before that
    is_total = (df["Org Code"].fillna("").str.upper() == "TOTAL") | (df["Org name"].fillna("").str.upper() == "TOTAL")
    total, prov = df[is_total], df[~is_total].copy()
    log("TOTAL rows", len(total), "England total row mixed in with providers (Jan-Mar 2020: blank code, name 'Total')",
        "Removed; used only to check the sums")
    region = prov["Parent Org"].str.replace("NHS ENGLAND ", "", regex=False).str.title().str.replace(" And ", " and ").str.replace(" Of ", " of ")
    sub = region.str.contains(r"\(", regex=True)
    log("Region names", sub.sum(), "Jan-Mar 2020 files name sub-regions, e.g. 'Midlands (West Midlands)'",
        "Mapped to the seven NHS England regions")
    prov["region"] = region.str.replace(r"\s*\(.*\)$", "", regex=True)
    assert prov.region.nunique() == 7, prov.region.unique()

    # derived measures, as NHS England defines them: all A&E types, booked appointments included
    prov["attendances"] = prov[[c for c in MEASURES if c.startswith("att_")]].sum(axis=1)
    prov["over_4hrs"] = prov[[c for c in MEASURES if c.startswith("over4_")]].sum(axis=1)
    prov["type1_attendances"] = prov.att_type1 + prov.att_booked_type1
    prov["type1_over_4hrs"] = prov.over4_type1 + prov.over4_booked_type1
    prov["emergency_admissions"] = prov[["adm_type1", "adm_type2", "adm_other", "adm_other_route"]].sum(axis=1)
    has_type1 = prov.groupby("Org Code").type1_attendances.transform("max") > 0
    prov["provider_type"] = has_type1.map({True: "Major A&E (Type 1)", False: "Other A&E only"})

    # check: provider sums reproduce the published TOTAL row
    t = total.set_index("month")
    s = prov.groupby("month")[["attendances", "over_4hrs"]].sum()
    tot_att = t[[c for c in MEASURES if c.startswith("att_")]].sum(axis=1)
    diff = (s.attendances - tot_att.reindex(s.index)).abs()
    assert diff.notna().all() and len(t) == len(s), "every month needs a TOTAL row to check against"
    log("Sum check", int((diff > 0).sum()), f"Months (of {len(s)}) where providers do not sum to the TOTAL row (max gap {int(diff.max())} attendances)",
        "Provider sums used; gap reported")

    upper = (prov["Org name"] == prov["Org name"].str.upper()).sum()
    prov["Org name"] = prov["Org name"].map(nice_name)
    log("Name case", upper, "Organisation names in capitals in most files, mixed case in others", "Converted to title case, keeping NHS and acronyms")

    cols = ["month", "Org Code", "Org name", "region", "provider_type", "attendances", "over_4hrs", "type1_attendances", "type1_over_4hrs",
            "dta_4_12hr", "dta_12hr_plus", "emergency_admissions"]
    tidy = prov[cols].rename(columns={"Org Code": "org_code", "Org name": "org_name"}).sort_values(["org_code", "month"])
    tidy.to_csv(os.path.join(OUT, "ae_monthly.csv"), index=False)
    log("Provider-months", len(tidy), f"{tidy.org_code.nunique()} providers, {tidy.month.nunique()} months", "Written to ae_monthly.csv")

    agg = ["attendances", "over_4hrs", "type1_attendances", "type1_over_4hrs", "dta_4_12hr", "dta_12hr_plus", "emergency_admissions"]
    eng = tidy.groupby("month")[agg].sum().reset_index()
    reg = tidy.groupby(["region", "month"])[agg].sum().reset_index()
    for d in (eng, reg):
        d["pct_4hr"] = (100 * (1 - d.over_4hrs / d.attendances)).round(2)
        d["pct_4hr_type1"] = (100 * (1 - d.type1_over_4hrs / d.type1_attendances)).round(2)
    eng.to_csv(os.path.join(OUT, "england.csv"), index=False)
    reg.to_csv(os.path.join(OUT, "regions.csv"), index=False)

    # reconcile with the National Audit Office's published figure for 2025-26 (74.9%)
    fy = eng[(eng.month >= "2025-04") & (eng.month <= "2026-03")]
    pct = 100 * (1 - fy.over_4hrs.sum() / fy.attendances.sum())
    log("Reconciliation", 12, f"2025-26 four-hour performance recomputed as {pct:.1f}% (NAO reports 74.9%)", "Matches" if abs(pct - 74.9) < 0.15 else "Investigate")
    pd.DataFrame(LOG).to_csv(os.path.join(OUT, "data_quality_log.csv"), index=False)
    print(pd.DataFrame(LOG).to_string())


if __name__ == "__main__":
    main()
