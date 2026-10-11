"""Power BI version of the A&E SPC project: the spec. Run from the powerbi/ folder:

    python tools/spec.py        # writes AE_SPC.pbip and its folders
    python tools/validate.py    # schema and reference checks
    python tools/expected.py    # what the visuals should show, recomputed in pandas

The XmR process limits are calculated in DAX (mean +/- 2.66 x screened average moving range over the last 24 months),
so the Power BI chart re-derives Making Data Count's limits for whichever trust, region or England is selected.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbikit import C, M, build, card, color, lit, series_colors, slicer, text_box, visual  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "AE_SPC"
TEAL, ORANGE, GREY, BLUE, INK = "#0F766E", "#C2410C", "#9AA3A0", "#2443D6", "#13201B"
TARGET = 0.82          # the project's 4-hour standard (see README); a measure, so it can be changed in one place
WINDOW = 24            # months in the SPC baseline, as in src/summary.py

READ = '''
    Read = (file as text) as table =>
        Table.PromoteHeaders(
            Csv.Document(Web.Contents(BaseUrl, [RelativePath = file]), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
            [PromoteAllScalars = true]),'''

TABLES = {
    "Entities": dict(
        description="England, the 7 regions and the 120 trusts with a Type 1 department in every month of the SPC window (spc_summary.csv). "
                    "Variation and assurance come from the Python SPC rules (src/spc.py).",
        file="spc_summary.csv",
        columns=[("level", "string", {}), ("code", "string", {"isKey": True}), ("name", "string", {}), ("region", "string", {}),
                 ("pct_4hr_variation", "string", {"isHidden": True}), ("pct_4hr_special_6m", "int64", {}),
                 ("pct_4hr_assurance", "string", {"isHidden": True}),
                 ("pct_4hr_mean", "double", {"isHidden": True}), ("pct_4hr_lpl", "double", {"isHidden": True}),
                 ("pct_4hr_upl", "double", {"isHidden": True}),
                 ("dta_12hr_plus_variation", "string", {"isHidden": True})],
        added=[("Variation", "string", {}), ("Assurance", "string", {}), ("Level Order", "int64", {"isHidden": True})],
        m_extra='''
            #"Variation" = Table.AddColumn(#"Filtered Rows", "Variation", each
                if [pct_4hr_variation] = "improvement" then "Special cause: improving"
                else if [pct_4hr_variation] = "concern" then "Special cause: concern"
                else "Common cause", type text),
            #"Assurance" = Table.AddColumn(#"Variation", "Assurance", each
                if [pct_4hr_assurance] = "pass" then "Will consistently meet 82%"
                else if [pct_4hr_assurance] = "fail" then "Will consistently miss 82%"
                else "Hit and miss", type text),
            #"Level Order" = Table.AddColumn(#"Assurance", "Level Order", each
                if [level] = "England" then 1 else if [level] = "Region" then 2 else 3, Int64.Type)
        ''', m_last="Level Order"),
    "Monthly": dict(
        description="One row per entity per month, 2020 onwards. England and regions count every A&E type; trusts are their Type 1 "
                    "(major) departments, as in the SPC summary. Combined in Power Query from three CSVs.",
        m='''
let''' + READ + '''
    England = Table.AddColumn(Read("england.csv"), "code", each "ENG", type text),
    Regions = Table.RenameColumns(Read("regions.csv"), {{"region", "code"}}),
    Trusts = Table.RenameColumns(
        Table.SelectRows(Read("ae_monthly.csv"), each [provider_type] = "Major A&E (Type 1)"),
        {{"org_code", "code"}}),
    Keep = {"code", "month", "attendances", "over_4hrs", "type1_attendances", "type1_over_4hrs", "dta_12hr_plus"},
    Combined = Table.Combine({
        Table.SelectColumns(England, Keep), Table.SelectColumns(Regions, Keep), Table.SelectColumns(Trusts, Keep)}),
    Typed = Table.TransformColumnTypes(Combined, {
        {"code", type text}, {"month", type text}, {"attendances", Int64.Type}, {"over_4hrs", Int64.Type},
        {"type1_attendances", Int64.Type}, {"type1_over_4hrs", Int64.Type}, {"dta_12hr_plus", Int64.Type}}, "en-US"),
    Result = Table.AddColumn(Typed, "month_start", each #datetime(
        Number.FromText(Text.Start([month], 4)), Number.FromText(Text.End([month], 2)), 1, 0, 0, 0), type datetime)
in
    Result''',
        columns=[("code", "string", {"isHidden": True}), ("month", "string", {"isHidden": True}), ("attendances", "int64", {}),
                 ("over_4hrs", "int64", {}), ("type1_attendances", "int64", {}), ("type1_over_4hrs", "int64", {}),
                 ("dta_12hr_plus", "int64", {}), ("month_start", "dateTime", {"isHidden": True, "formatString": "mmm yyyy"})]),
    "Calendar": dict(
        description=f"One row per month. Month Index counts months from January 2020; In SPC Window = 1 for the last {WINDOW} months, "
                    "the baseline for the process limits.",
        m=f'''
let''' + READ + f'''
    Months = Table.SelectColumns(Read("england.csv"), {{"month"}}),
    Sorted = Table.Sort(Months, {{{{"month", Order.Ascending}}}}),
    Indexed = Table.AddIndexColumn(Sorted, "Month Index", 0, 1, Int64.Type),
    Last = List.Max(Indexed[Month Index]),
    WithStart = Table.AddColumn(Indexed, "month_start", each #datetime(
        Number.FromText(Text.Start([month], 4)), Number.FromText(Text.End([month], 2)), 1, 0, 0, 0), type datetime),
    Window = Table.AddColumn(WithStart, "In SPC Window", each if [Month Index] > Last - {WINDOW} then 1 else 0, Int64.Type),
    Result = Table.AddColumn(Window, "Month Name", each Date.ToText(Date.From([month_start]), "MMM yyyy", "en-GB"), type text)
in
    Result''',
        columns=[("month", "string", {"isHidden": True}), ("Month Index", "int64", {"isHidden": True}),
                 ("month_start", "dateTime", {"isKey": True, "formatString": "mmm yyyy"}),
                 ("In SPC Window", "int64", {"isHidden": True}), ("Month Name", "string", {"sortByColumn": "Month Index"})]),
}

RELATIONSHIPS = [
    (("Monthly", "code"), ("Entities", "code"), {}),
    (("Monthly", "month_start"), ("Calendar", "month_start"), {}),
]

# every measure resolves to one entity: the one in context, or England when none (or several) is selected
SEL = "VAR _code = [Selected Code]\n"
SPC_POINTS = """VAR _months =
    CALCULATETABLE ( VALUES ( 'Calendar'[Month Index] ), REMOVEFILTERS ( 'Calendar' ), 'Calendar'[In SPC Window] = 1 )
VAR _points =
    ADDCOLUMNS (
        _months,
        "@v",
            VAR _i = 'Calendar'[Month Index]
            RETURN CALCULATE ( [% Within 4 Hours], REMOVEFILTERS ( 'Calendar' ), 'Calendar'[Month Index] = _i )
    )
"""
MEASURES = [
    ("Selected Code", "Monthly", "Selection", "General", 'SELECTEDVALUE ( Entities[code], "ENG" )',
     "The trust, region or England in context; England when nothing (or more than one) is selected."),
    ("Selected Name", "Monthly", "Selection", "General", 'LOOKUPVALUE ( Entities[name], Entities[code], [Selected Code] )',
     "Name of the entity in context, for titles."),
    ("A&E Attendances", "Monthly", "Activity", "#,0", SEL + "RETURN CALCULATE ( SUM ( Monthly[attendances] ), REMOVEFILTERS ( Entities ), Entities[code] = _code )",
     "A&E attendances (England and regions: all types; trusts: Type 1)."),
    ("Waited Over 4 Hours", "Monthly", "Activity", "#,0", SEL + "RETURN CALCULATE ( SUM ( Monthly[over_4hrs] ), REMOVEFILTERS ( Entities ), Entities[code] = _code )",
     "Attendances that took more than 4 hours from arrival to admission, transfer or discharge."),
    ("% Within 4 Hours", "Monthly", "Performance", "0.0%", "DIVIDE ( [A&E Attendances] - [Waited Over 4 Hours], [A&E Attendances] )",
     "Share of attendances seen within 4 hours."),
    ("Waits Over 12 Hours", "Monthly", "Activity", "#,0", SEL + "RETURN CALCULATE ( SUM ( Monthly[dta_12hr_plus] ), REMOVEFILTERS ( Entities ), Entities[code] = _code )",
     "Patients waiting more than 12 hours from decision to admit to admission."),
    ("4-Hour Standard", "Monthly", "Performance", "0%", f"{TARGET}", "The 4-hour standard used for assurance in this project."),
    ("Latest Month", "Monthly", "Performance", "General",
     "VAR _last = CALCULATE ( MAX ( 'Calendar'[Month Index] ), REMOVEFILTERS ( 'Calendar' ) )\n"
     "RETURN CALCULATE ( MAX ( 'Calendar'[Month Name] ), REMOVEFILTERS ( 'Calendar' ), 'Calendar'[Month Index] = _last )", "Latest month in the data."),
    ("Latest % Within 4 Hours", "Monthly", "Performance", "0.0%",
     "VAR _last = CALCULATE ( MAX ( 'Calendar'[Month Index] ), REMOVEFILTERS ( 'Calendar' ) )\n"
     "RETURN CALCULATE ( [% Within 4 Hours], REMOVEFILTERS ( 'Calendar' ), 'Calendar'[Month Index] = _last )", "Performance in the latest month."),
    ("SPC Mean", "Monthly", "SPC", "0.0%", SPC_POINTS + """VAR _mean = AVERAGEX ( _points, [@v] )
RETURN
    IF ( MAX ( 'Calendar'[In SPC Window] ) = 1, _mean )""",
     f"Centre line: mean of the last {WINDOW} months. Blank outside the window so the chart draws it only there."),
    ("SPC Average Moving Range", "Monthly", "SPC", "0.00%", SPC_POINTS + """VAR _first = MINX ( _points, 'Calendar'[Month Index] )
VAR _ranges =
    ADDCOLUMNS (
        FILTER ( _points, 'Calendar'[Month Index] > _first ),
        "@mr",
            VAR _i = 'Calendar'[Month Index]
            RETURN ABS ( [@v] - MAXX ( FILTER ( _points, 'Calendar'[Month Index] = _i - 1 ), [@v] ) )
    )
VAR _amr = AVERAGEX ( _ranges, [@mr] )
VAR _screened = AVERAGEX ( FILTER ( _ranges, [@mr] < 3.267 * _amr ), [@mr] )
RETURN
    IF ( MAX ( 'Calendar'[In SPC Window] ) = 1, COALESCE ( _screened, _amr ) )""",
     "Average month-to-month change. Moving ranges of 3.267 x the average or more are screened out and the average recalculated, "
     "as in Making Data Count."),
    ("SPC Upper Limit", "Monthly", "SPC", "0.0%", "[SPC Mean] + 2.66 * [SPC Average Moving Range]", "Upper process limit: mean + 2.66 x average moving range."),
    ("SPC Lower Limit", "Monthly", "SPC", "0.0%", "[SPC Mean] - 2.66 * [SPC Average Moving Range]", "Lower process limit: mean - 2.66 x average moving range."),
    ("Assurance (DAX)", "Monthly", "SPC", "General",
     """VAR _upl = [SPC Upper Limit]
VAR _lpl = [SPC Lower Limit]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( _upl ), BLANK (),
        [4-Hour Standard] > _upl, "Will consistently miss",
        [4-Hour Standard] < _lpl, "Will consistently meet",
        "Hit and miss"
    )""", "Where the standard sits against the DAX process limits. Should agree with the Python assurance."),
    ("Latest Variation", "Monthly", "SPC", "General", "LOOKUPVALUE ( Entities[Variation], Entities[code], [Selected Code] )",
     "Latest-month variation from the Python SPC rules (single point, trend, two-of-three, shift)."),
    ("Assurance Rating", "Monthly", "SPC", "General", "LOOKUPVALUE ( Entities[Assurance], Entities[code], [Selected Code] )",
     "Assurance against the standard from the Python SPC rules."),
    ("Trust Latest %", "Monthly", "Trusts", "0.0%", 'IF ( SELECTEDVALUE ( Entities[level] ) = "Trust", [Latest % Within 4 Hours] )',
     "Latest performance, trusts only (blank for England and regions, so tables list trusts)."),
    ("Trust SPC Mean", "Monthly", "Trusts", "0.0%", 'IF ( SELECTEDVALUE ( Entities[level] ) = "Trust", CALCULATE ( [SPC Mean], REMOVEFILTERS ( \'Calendar\' ) ) )',
     "SPC centre line, trusts only."),
    ("Trust Lower Limit", "Monthly", "Trusts", "0.0%", 'IF ( SELECTEDVALUE ( Entities[level] ) = "Trust", CALCULATE ( [SPC Lower Limit], REMOVEFILTERS ( \'Calendar\' ) ) )',
     "Lower process limit, trusts only."),
    ("Trust Upper Limit", "Monthly", "Trusts", "0.0%", 'IF ( SELECTEDVALUE ( Entities[level] ) = "Trust", CALCULATE ( [SPC Upper Limit], REMOVEFILTERS ( \'Calendar\' ) ) )',
     "Upper process limit, trusts only."),
    ("Region Latest %", "Monthly", "Trusts", "0.0%", 'IF ( SELECTEDVALUE ( Entities[level] ) = "Region", [Latest % Within 4 Hours] )',
     "Latest performance, regions only."),
    ("Trusts Consistently Missing", "Monthly", "Trusts", "#,0",
     'COUNTROWS ( FILTER ( ALL ( Entities ), Entities[level] = "Trust" && Entities[pct_4hr_assurance] = "fail" ) )',
     "Trusts whose process limits sit wholly below the standard."),
    ("Trusts Improving", "Monthly", "Trusts", "#,0",
     'COUNTROWS ( FILTER ( ALL ( Entities ), Entities[level] = "Trust" && Entities[pct_4hr_variation] = "improvement" ) )',
     "Trusts showing special cause improvement in the latest month."),
    ("Trusts of Concern", "Monthly", "Trusts", "#,0",
     'COUNTROWS ( FILTER ( ALL ( Entities ), Entities[level] = "Trust" && Entities[pct_4hr_variation] = "concern" ) )',
     "Trusts showing special cause concern in the latest month."),
]

# ---------------------------------------------------------------- report
T = "Monthly"
p1, p2 = "spc", "trusts"
pct, mean, upl, lpl, std = (M(T, "% Within 4 Hours", "Within 4 hours"), M(T, "SPC Mean", "Mean"), M(T, "SPC Upper Limit", "Upper limit"),
                            M(T, "SPC Lower Limit", "Lower limit"), M(T, "4-Hour Standard", "Standard (82%)"))
line_objects = {"dataPoint": series_colors([pct, mean, upl, lpl, std], [INK, GREY, ORANGE, ORANGE, BLUE]),
                "lineStyles": [{"properties": {"strokeWidth": lit(2), "showMarker": lit(True)}}]}
PAGES = [
    (p1, "SPC chart", [
        text_box(p1, "title", 24, 12, 860, 52, "A&E four-hour performance, read with SPC (Making Data Count)", 18),
        slicer(p1, "entity", 900, 8, 356, 64, C("Entities", "name", "Trust, region or England"), None, single=True),
        card(p1, "latest", 24, 76, 236, 96, M(T, "Latest % Within 4 Hours", "Latest month")),
        card(p1, "mean", 272, 76, 236, 96, M(T, "SPC Mean", "Mean, last 24 months")),
        card(p1, "lpl", 520, 76, 236, 96, M(T, "SPC Lower Limit", "Lower process limit")),
        card(p1, "upl", 768, 76, 236, 96, M(T, "SPC Upper Limit", "Upper process limit")),
        card(p1, "assure", 1016, 76, 240, 96, M(T, "Assurance Rating", "Assurance"), size=13),
        visual(p1, "chart", "lineChart", 24, 184, 1232, 340,
               {"Category": [C("Calendar", "month_start", "Month")], "Y": [pct, mean, upl, lpl, std]},
               "Share seen within 4 hours, with process limits from the last 24 months (calculated in DAX)", objects=line_objects, z=10),
        visual(p1, "dta", "lineChart", 24, 536, 820, 172,
               {"Category": [C("Calendar", "month_start", "Month")], "Y": [M(T, "Waits Over 12 Hours", "Waits over 12 hours")]},
               "12-hour waits from decision to admit", objects={"dataPoint": [{"properties": {"fill": color(ORANGE)}}]}, z=11),
        card(p1, "variation", 860, 536, 396, 80, M(T, "Latest Variation", "Latest month: variation"), size=13),
        card(p1, "assure_dax", 860, 628, 396, 80, M(T, "Assurance (DAX)", "Assurance from the DAX limits"), size=13),
    ]),
    (p2, "Trusts", [
        text_box(p2, "title", 24, 12, 1000, 52, "120 trusts: latest month, process limits, variation and assurance", 18),
        card(p2, "fail", 24, 76, 300, 96, M(T, "Trusts Consistently Missing", "Trusts that will consistently miss 82%")),
        card(p2, "improving", 336, 76, 300, 96, M(T, "Trusts Improving", "Trusts improving (special cause)")),
        card(p2, "concern", 648, 76, 300, 96, M(T, "Trusts of Concern", "Trusts of concern (special cause)")),
        visual(p2, "table", "tableEx", 24, 184, 820, 524,
               {"Values": [C("Entities", "name", "Trust"), C("Entities", "region", "Region"), M(T, "Trust Latest %", "Latest"),
                           M(T, "Trust SPC Mean", "Mean"), M(T, "Trust Lower Limit", "Lower limit"), M(T, "Trust Upper Limit", "Upper limit"),
                           C("Entities", "Variation"), C("Entities", "Assurance")]},
               "Every trust (Type 1 departments)", sort=(M(T, "Trust Latest %"), "Descending"), z=10),
        visual(p2, "regions", "clusteredBarChart", 860, 184, 396, 524,
               {"Category": [C("Entities", "name", "Region")], "Y": [M(T, "Region Latest %", "Latest month")]},
               "Regions, latest month", objects={"dataPoint": [{"properties": {"fill": color(TEAL)}}], "labels": [{"properties": {"show": lit(True)}}]},
               sort=(M(T, "Region Latest %"), "Descending"), z=11),
    ]),
]

SPEC = dict(name=NAME, root=ROOT, tables=TABLES, measures=MEASURES, relationships=RELATIONSHIPS, pages=PAGES,
            base_url="https://raw.githubusercontent.com/QaisBello/nhs-ae-spc/main/data/clean/",
            base_desc="Folder of cleaned CSVs from this repo (data/clean). Point it at a local folder or another branch to test.")

if __name__ == "__main__":
    build(SPEC)
