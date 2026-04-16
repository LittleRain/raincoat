# Report Skill Acceptance Matrix

This matrix defines the generation and acceptance levels for downstream report
skills created by `create-report`.

## Levels

### L0 Documentation

Use when requirements can be normalized, but real samples or execution details
are not complete yet.

Must pass:
- normalized spec exists
- section order is fixed
- output format is HTML
- missing fields, samples, and unresolved口径 are documented
- the downstream skill clearly states it is documentation-only

Allowed:
- script stubs
- placeholder outline HTML
- incomplete input inventory

Forbidden:
- claiming runnable output
- presenting placeholder HTML as execution evidence

### L1 Runnable MVP

Use when the downstream skill can generate one real internal report from real
sample-backed data.

Must pass:
- all L0 checks
- real sample files exist
- samples cover at least two comparable periods
- explicit core metric formulas are declared when known
- core table schemas and WoW columns are declared
- expected chart/table counts and explicit required metrics are derived from the source requirement
- ambiguous desired metrics may be delegated to model judgment with source-field evidence
- `scripts/run-report.sh` invokes real generation logic, not a stub
- one real `report.html` is generated from samples
- runtime logs include file discovery, read checks, period detection, section build progress, and output path
- smoke validation confirms the HTML is non-placeholder, uses the standard report structure, and matches expected chart/table/required-metric inventory

Allowed:
- limited manual visual review
- non-core formatter gaps if documented
- repo-local operation

Forbidden:
- missing real samples
- stub runner
- placeholder output HTML
- ambiguous official KPI formulas
- undocumented multi-source precedence
- missing or mismatched chart/table/metric inventory

### L2 Publishable / Stable

Use when the downstream skill is safe to publish or hand off for repeated use.

Must pass:
- all L1 checks
- package is self-contained and avoids absolute repo-local paths
- Chart.js and chart defaults are local or inlined; no required CDN
- `file://` browser validation confirms charts render
- console has no blocking errors
- HTML validator passes required structure and dependency checks
- metric formatter map exists for all declared metrics
- regression tests cover missing values, zero denominators, and at least one fallback path
- validation evidence is stored with the generated package

Forbidden:
- upstream-only references required for operation
- CDN-only chart runtime
- unresolved formatter or formula ambiguity
- relying on visual inspection as the only proof

## Gate Matrix

| Check | L0 Docs | L1 Runnable MVP | L2 Publishable |
|---|---:|---:|---:|
| normalized spec exists | Must | Must | Must |
| section order fixed | Must | Must | Must |
| output format is HTML | Must | Must | Must |
| missing gaps documented | Must | Must | Must |
| real sample data | No | Must | Must |
| two comparable periods | No | Must | Must |
| explicit core metric formulas declared | Gap allowed | Must when known | Must when known |
| ambiguous metric judgment documented | Should | Must when used | Must when used |
| core formatter map | No | Must | Must |
| full formatter map | No | Optional | Optional |
| table schemas and WoW rules | Gap allowed | Must for rendered tables | Must |
| real runner | No | Must | Must |
| non-placeholder report.html | No | Must | Must |
| chart/table inventory declared | Should | Must | Must |
| rendered chart/table counts match inventory | No | Must | Must |
| required_metrics appear in rendered HTML | No | Must | Must |
| runtime logs | No | Must | Must |
| HTML structure validation | No | Smoke | Must |
| browser file:// validation | No | Should | Must |
| local/inlined chart runtime | No | Should | Must |
| regression tests | No | Smoke | Must |
| standalone package | No | No | Must |

## Acceptance Evidence

Every generated downstream skill should include `skill-manifest.yaml` with:

- `declared_level`
- `effective_level`
- `acceptance_status`
- `acceptance_date`
- `acceptance_evidence`
- `blocking_gaps`

A downstream skill may not claim a higher effective level than the evidence
supports.
