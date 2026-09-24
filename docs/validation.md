# v0.1 validation record

Validated locally on Windows with CPython 3.12.10.

- 34 Python tests passed: development, GRNs, inheritance and structural mutation, bounded learning, genome isolation, energy/food/death/birth, exact continuation in all learning modes and across controlled generations, invalid snapshot handling, CLI conditions, paired statistics and HTTP behavior.
- Python compilation, JavaScript syntax and Git whitespace checks passed.
- Browser checks exercised world controls, snapshot download and checksum-preserving import, rejection of corrupted imports, embryo scrubbing, all seven views, real paired results, seed/population configuration, controlled offspring and responsive layout. The 390-pixel viewport had no horizontal page overflow. Expected HTTP 400 responses occur for deliberate corrupt imports.
- A clean environment installed the wheel, resolved all four packaged viewer assets, and passed a snapshot/continuation smoke test.
- The release learning example ran five paired seeds for 300 ticks per arm. All ten exported snapshots validated; the receipt's source hash matched the engine used at final verification. Results are in `results/release-learning/` in this working copy; generated runs are excluded from Git.

Snapshots preserve raw JSON text through the browser, including floating-point number representations. This fixed a detected browser roundtrip checksum failure. CLI organism artifacts also retain developmental conditions, fixing a detected low-nutrient phenotype mismatch.

Browser automation initially encountered a stalled headed session and timing assumptions about a shared live world. A fresh automation session and response-based checks were used. The isolated API tests verify failed imports do not alter state; another active browser can independently advance the shared world during a UI check.

These are software validation and small exploratory experiment receipts. They are not evidence of biological realism, open-ended evolution, or an advantage of developmental encoding over a matched direct comparator.
