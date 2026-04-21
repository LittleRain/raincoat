# Validation Checklist

## L0 Documentation

- normalized spec exists
- expected output inventory exists
- runner is a failing documentation stub
- package does not claim runnable output

## L1 Runnable MVP

- all L0 checks pass
- real sample files cover at least two comparable periods
- real runner generates HTML and runtime logs
- chart/table counts and required metric labels match expected-output-inventory.json
- HTML is non-placeholder
- sample test findings are resolved or classified for downstream-only, create-report backflow, or test-note handling

## L2 Publishable

- all L1 checks pass
- package is self-contained
- no required external CDN
- local file:// browser validation passes
- regression evidence is packaged
