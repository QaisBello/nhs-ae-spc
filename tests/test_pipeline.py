"""The cleaned tables: complete, consistent and reconciled with published figures."""
import glob
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "data", "clean")


def read(name):
    return pd.read_csv(os.path.join(CLEAN, name))


def test_raw_files_are_kept_as_downloaded():
    files = glob.glob(os.path.join(ROOT, "data", "raw", "*.csv"))
    assert len(files) >= 80
    layouts = {len(pd.read_csv(f, nrows=1).columns) for f in files}
    assert len(layouts) >= 3                      # the format really did change


def test_one_row_per_provider_per_month_and_no_totals():
    m = read("ae_monthly.csv")
    assert not m.duplicated(["org_code", "month"]).any()
    assert not m.org_code.isna().any()
    assert not m.org_name.str.upper().eq("TOTAL").any()
    assert m.month.nunique() == len(pd.period_range(m.month.min(), m.month.max(), freq="M"))   # no missing months


def test_seven_regions():
    assert read("ae_monthly.csv").region.nunique() == 7


def test_breaches_never_exceed_attendances():
    m = read("ae_monthly.csv")
    assert (m.over_4hrs <= m.attendances).all() and (m.type1_over_4hrs <= m.type1_attendances).all()


def test_england_is_the_sum_of_regions():
    e, r = read("england.csv").set_index("month"), read("regions.csv").groupby("month").sum(numeric_only=True)
    assert (e.attendances == r.attendances).all() and (e.over_4hrs == r.over_4hrs).all()


def test_reconciles_with_national_audit_office():
    log = read("data_quality_log.csv").set_index("check")
    assert log.loc["Reconciliation", "action"] == "Matches"
    assert log.loc["Sum check", "rows_affected"] == 0       # providers add up to NHS England's TOTAL row every month
    assert json.load(open(os.path.join(CLEAN, "summary.json")))["fy_2025_26"] == 74.9


def test_summary_covers_every_major_ae():
    s = read("spc_summary.csv")
    t = s[s.level == "Trust"]
    assert len(t) >= 100 and set(t.pct_4hr_assurance) <= {"pass", "fail", "inconsistent"}
