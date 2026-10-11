# Expected values

From `tools/expected.py`: the DAX logic recomputed in pandas, and checked against the Python SPC in `src/spc.py`.

Process limits for all 128 entities (England, 7 regions, 120 trusts) match the Python SPC to 0.01 points: **yes**. DAX assurance agrees with Python for 128 of 128.

## Page 1, nothing selected (England)

| Card | Expected |
|---|---:|
| Latest month (2026-09) | 74.4% |
| Mean, last 24 months | 74.5% |
| Lower process limit | 72.5% |
| Upper process limit | 76.6% |
| Assurance | fail |

## Page 2

| Card | Expected |
|---|---:|
| Trusts that will consistently miss 82% | 100 |
| Trusts improving | 31 |
| Trusts of concern | 8 |

Top 5 trusts, latest month:

| Trust | Latest | Mean | Lower | Upper |
|---|---:|---:|---:|---:|
| Northumbria Healthcare NHS Foundation Trust | 90.8% | 89.1% | 86.0% | 92.3% |
| Sheffield Children's NHS Foundation Trust | 90.3% | 92.4% | 86.9% | 98.0% |
| West Hertfordshire Teaching Hospitals NHS Trust | 87.2% | 83.9% | 80.1% | 87.7% |
| George Eliot Hospital NHS Trust | 86.7% | 77.8% | 70.3% | 85.3% |
| Alder Hey Children's NHS Foundation Trust | 85.9% | 84.0% | 75.8% | 92.2% |

Regions, latest month:

| Region | Latest |
|---|---:|
| London | 77.0% |
| South East | 76.2% |
| North East and Yorkshire | 75.2% |
| East of England | 74.0% |
| Midlands | 72.9% |
| North West | 71.8% |
| South West | 71.8% |
