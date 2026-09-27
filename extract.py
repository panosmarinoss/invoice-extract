#!/usr/bin/env python3
import base64, json, sys
from typing import List, Optional
from pydantic import BaseModel
import anthropic


class LineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None


class Invoice(BaseModel):
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    currency: Optional[str] = None
    line_items: List[LineItem] = []
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None


client = anthropic.Anthropic()


def extract(pdf_path: str) -> Invoice:
    with open(pdf_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")

    resp = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=4096,
        tools=[{
            "name": "record_invoice",
            "description": "Record the fields extracted from the invoice.",
            "input_schema": Invoice.model_json_schema(),
        }],
        tool_choice={"type": "tool", "name": "record_invoice"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "document",
                 "source": {"type": "base64",
                            "media_type": "application/pdf",
                            "data": data}},
                {"type": "text",
                 "text": "Extract the invoice fields. Use null for anything "
                         "not present on the document. Do not guess or infer "
                         "values that aren't printed."},
            ],
        }],
    )

    for block in resp.content:
        if block.type == "tool_use":
            return Invoice(**block.input)
    raise RuntimeError("Model returned no tool_use block")


def validate(inv: Invoice) -> tuple[List[str], List[str]]:
    """Catch arithmetic the model got wrong.
    Returns (problems, checks_run) so a silent skip can't look like a pass."""
    problems = []
    checks_run = []

    totals = [li.total for li in inv.line_items if li.total is not None]
    line_sum = round(sum(totals), 2) if totals else None

    if None not in (inv.subtotal, inv.tax_amount, inv.total_amount):
        checks_run.append("subtotal + tax == total")
        expected = round(inv.subtotal + inv.tax_amount, 2)
        if abs(expected - inv.total_amount) > 0.02:
            problems.append(
                f"subtotal + tax = {expected}, but total reads {inv.total_amount}"
            )

    if line_sum is not None and inv.subtotal is not None:
        checks_run.append("line items == subtotal")
        if abs(line_sum - inv.subtotal) > 0.02:
            problems.append(
                f"line items sum to {line_sum}, subtotal reads {inv.subtotal}"
            )

    # Fallback: no subtotal printed, but we can still check the line items
    if line_sum is not None and inv.subtotal is None and inv.total_amount is not None:
        checks_run.append("line items == total (no subtotal on document)")
        expected = round(line_sum + (inv.tax_amount or 0), 2)
        if abs(expected - inv.total_amount) > 0.02:
            problems.append(
                f"line items (+tax) = {expected}, but total reads {inv.total_amount}"
            )

    return problems, checks_run


if __name__ == "__main__":
    invoice = extract(sys.argv[1])
    print(json.dumps(invoice.model_dump(), indent=2, ensure_ascii=False))
    issues, checks = validate(invoice)

    if not checks:
        print("\nUNVERIFIED - no arithmetic check could run on this document")
    elif issues:
        print("\nVALIDATION FAILED:")
        for i in issues:
            print(f"  - {i}")
    else:
        print(f"\nOK - passed {len(checks)} check(s): {', '.join(checks)}")
