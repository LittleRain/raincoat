# Report Spec Questionnaire

Use this as the intake form for non-technical users. Free-form requirement docs
may prefill the answers, but missing required answers must be confirmed before
L1/L2 generation.

## 1. Report Goal

- report name:
- business domain:
- audience:
- decisions this report should support:
- what a good report must explain:

## 2. Time Window

- reporting period:
- comparison period:
- historical weeks or months to show:
- timezone or calendar rule:

## 3. Sections

Repeat for each report section.

- section id:
- title:
- purpose:
- primary data source:
- fallback data source:
- required metrics:
- required dimensions:
- expected charts count:
- expected tables count:
- chart splitting rule:
- required tables and columns:
- required conclusion style:

## 4. Data Sources

Repeat for each input file.

- contract id:
- file name pattern:
- required or optional:
- supported sections:
- period coverage:
- dimensions:
- metrics:
- known field aliases:
- quality risks:

## 5. Metric Formulas

Repeat for every official KPI.

- metric name:
- source fields:
- formula:
- formatter:
- zero denominator behavior:
- fallback formula:

## 6. Attribution Evidence

Repeat for each conclusion type.

- section:
- trigger condition:
- allowed evidence fields:
- allowed evidence datasets:
- forbidden claims:
- required direction words:

## 7. Empty Values

- fields that must block when empty:
- fields that may display as "unknown":
- numeric null handling:
- all-empty period column handling:

## 8. Downstream Skill

- skill name:
- skill title:
- target level: L0 / L1 / L2
- evidence directory:
- publishability requirement:
