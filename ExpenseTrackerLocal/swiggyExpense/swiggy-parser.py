import pdfplumber
import re
from pathlib import Path
import pandas as pd

def parse_pdf_invoice(path):
    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"

    def find(pattern):
        m = re.search(pattern, text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    # Try to find total - could be "Invoice Total" or "Invoice Value"
    # For merged PDFs, "Invoice Value" is the actual total, while "Invoice Total" might be 0
    invoice_value = find(r"Invoice Value[:\s]*₹?\s*([\d,.]+)")
    invoice_total = find(r"Invoice Total[:\s]*₹?\s*([\d,.]+)")
    
    # Prefer Invoice Value if it exists, otherwise use Invoice Total
    # If Invoice Total is 0 and Invoice Value exists, use Invoice Value
    if invoice_value:
        total = invoice_value
    elif invoice_total and invoice_total != "0":
        total = invoice_total
    else:
        total = invoice_total  # Could be 0 or None
    
    # Try to find restaurant/seller name
    restaurant = find(r"Restaurant Name[:\s]*(.+?)(?:\n|Restaurant|Seller|$)")
    if not restaurant:
        restaurant = find(r"Seller Name[:\s]*(.+?)(?:\n|Restaurant|Seller|$)")
    
    return {
        "file": path.name,
        "order_id": find(r"Order ID[:\s]*([A-Z0-9]+)"),
        "date": find(r"Date of Invoice[:\s]*([\d\-\/ ]+)"),
        "restaurant": restaurant,
        "total": total
    }

rows = []
for pdf in Path("swiggy_invoices").glob("*.pdf"):
    rows.append(parse_pdf_invoice(pdf))

df = pd.DataFrame(rows)
# Handle None values and convert to float
df["total"] = df["total"].fillna("").str.replace(",", "").replace("", None)
df["total"] = pd.to_numeric(df["total"], errors="coerce")
df.to_csv("swiggy_expenses.csv", index=False)

print(df.head())
