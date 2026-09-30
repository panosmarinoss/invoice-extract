# invoice-extract

Extracts structured data from PDF invoices and independently verifies the
arithmetic. Built for European B2B documents — Greek, multi-currency, mixed
VAT rates.

**Live demo:** https://web-production-0777c.up.railway.app

Upload a PDF, get structured JSON plus a verdict on whether the document's
own numbers add up.

## Why the validation matters more than the extraction

Getting an LLM to read an invoice is easy. Knowing when it read one wrong is
the hard part, and it's the only part a business can act on.

This pipeline reports three states, never two:

This pipeline reports three states, never two:

| State | Meaning |
|---|---|
| **passed** | Arithmetic independently verified against the document |
| **flagged** | Extracted, but the numbers do not reconcile |
| **unverified** | Not enough fields present to check anything |

A document that cannot be checked is never reported as correct. That
distinction caught two real problems during development (below).

## Measured accuracy

Evaluated against 12 real European invoices with hand-written ground truth
across 7 fields plus line-item count (84 comparisons per run).

| Run | Field accuracy |
|---|---|
| 1 | 97.6% |
| 2 | 97.6% |
| 3 | 98.8% |

Reported as a range because identical inputs do not produce identical
outputs. A single-run accuracy figure is not reproducible.

Cost: approximately €0.03 per invoice.

## What the eval set found

**A document that genuinely doesn't reconcile.** One invoice computes VAT on
a pre-levy value (372.05) while printing a different net total (382.05), and
omits the levy from the amount payable. Printed subtotal + printed VAT does
not equal the printed total. Flagged on every run, correctly.

**A silent total failure.** In 1 of 36 extraction attempts, the model
returned every field as null — no error, no exception, just empty output.
At that rate a business processing 400 invoices a month would hit it
roughly 11 times. It was caught only because "unverified" is a state the
system can report. Now guarded explicitly: an all-null extraction raises
rather than returning.

**Script substitution.** Greek documents produced Latin lookalike characters
(T for Τ, A for Α, o for ο) unless the prompt forbids it. Visually identical,
byte-different — silently breaks ERP lookups on invoice numbers.


## Running it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=your-key" > .env

python extract.py invoice.pdf      # single document
python evals/run_eval.py           # accuracy report
fastapi dev app.py                 # web interface
```

## Known limitations

- Assumes one invoice per PDF; multi-invoice files must be split first
- No field for per-line discounts, levies, or Greek withholding tax
- Series and invoice number are joined into one string rather than stored
  separately, which is how Greek ERPs actually hold them
- Ground truth set is 12 documents. It is a real sample, not a large one.

## Stack

Python · Pydantic · Claude API · FastAPI · Railway

---

Built by [Panos Marinos](https://github.com/panosmarinoss) ·
panos@panosmarinos.com
