# A&E, read with SPC: Power BI

Four-hour A&E performance for England, its 7 regions and 120 trusts, read with statistical process control (NHS England's Making Data Count).

This folder is a Power BI project (`AE_SPC.pbip`): a TMDL semantic model and a PBIR report. It is generated from one Python spec, checked against Microsoft's JSON schemas, and its numbers are recomputed independently in pandas.

## Open it

1. Open **`AE_SPC.pbip`** in Power BI Desktop. In versions before mid-2025, first turn on the preview features for Power BI Project (.pbip), the TMDL model format and the PBIR report format.
2. Click **Refresh**. The model reads this repo's cleaned CSVs from GitHub through the **BaseUrl** parameter. If asked, choose **Anonymous** access for `raw.githubusercontent.com`.
3. Check the visuals against [`docs/expected_values.md`](docs/expected_values.md).

## Pages

- **SPC chart:** pick a trust, region or England (single-select slicer); latest month, mean and process limits; the XmR chart with the 82% standard; 12-hour waits; variation and assurance.
- **Trusts:** every trust with its latest month, mean, limits, variation and assurance; regions ranked; counts of trusts consistently missing, improving and of concern.

## Model

- **Tables:** Entities, Monthly, Calendar.
- **Relationships:** Monthly[code] to Entities[code]; Monthly[month_start] to Calendar[month_start].
- **24 DAX measures** in display folders: Selection (Selected Code, Selected Name); Activity (A&E Attendances, Waited Over 4 Hours, Waits Over 12 Hours); Performance (% Within 4 Hours, 4-Hour Standard, Latest Month, Latest % Within 4 Hours); SPC (SPC Mean, SPC Average Moving Range, SPC Upper Limit, SPC Lower Limit, Assurance (DAX), Latest Variation, Assurance Rating); Trusts (Trust Latest %, Trust SPC Mean, Trust Lower Limit, Trust Upper Limit, Region Latest %, Trusts Consistently Missing, Trusts Improving, Trusts of Concern). The full DAX is in [`docs/measures.md`](docs/measures.md).

## The SPC is calculated in DAX

The process limits are not pasted in. `SPC Mean` and `SPC Average Moving Range` rebuild the XmR calculation in DAX for whatever is selected: mean of the last 24 months, average month-to-month moving range, moving ranges of 3.267 x the average or more screened out, limits at mean +/- 2.66 x average moving range. `tools/expected.py` recomputes this for all 128 entities and confirms it matches the Python SPC (`src/spc.py`) to 0.01 points, and that the DAX assurance agrees with Python for all 128.

Variation (special cause) needs the run rules (trends, shifts, two-of-three), which are kept in Python and loaded as columns.

## Rebuild and check

```bash
pip install jsonschema referencing pandas numpy
python tools/spec.py        # the spec: writes the .pbip and its folders
python tools/validate.py    # Microsoft schemas, field and DAX references, name clashes
python tools/expected.py    # what the report should show, checked against the project's own results
```

`tools/pbikit.py` is a small shared library for writing Power BI projects as code. It is used across the portfolio and encodes lessons from real Power BI Desktop runs: names are case-insensitive; a format string must not start with a quote; empty CSV cells must become null before a type change; in DAX, `BLANK() = FALSE()` is true.
