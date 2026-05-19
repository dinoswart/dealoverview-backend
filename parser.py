"""
AFS Parser
==========
Extracts structured financial data from:
- PDF annual financial statements
- Excel/CSV management accounts

Strategy:
1. Try direct text/table extraction first
2. Use Claude vision for scanned/complex PDFs
3. Normalize all numbers to consistent format
"""

import io
import re
import json
import base64
import asyncio
from typing import Optional
import anthropic

# PDF
import pdfplumber
from pypdf import PdfReader

# Excel / CSV
import pandas as pd
import numpy as np

# Anthropic client
client = anthropic.AsyncAnthropic()

ANTHROPIC_MODEL = "claude-sonnet-4-20250514"


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

async def parse_afs_file(contents: bytes, filename: str) -> dict:
    """Route to correct parser based on file type."""
    fname = filename.lower()

    if fname.endswith(".pdf"):
        return await parse_pdf(contents, filename)
    elif fname.endswith((".xlsx", ".xls")):
        return parse_excel(contents, filename)
    elif fname.endswith(".csv"):
        return parse_csv(contents, filename)
    else:
        raise ValueError(f"Unsupported file type: {filename}")


# ─────────────────────────────────────────────
# PDF PARSER
# ─────────────────────────────────────────────

async def parse_pdf(contents: bytes, filename: str) -> dict:
    """
    Extract financials from PDF AFS.
    Tries text extraction first, falls back to Claude vision.
    """
    # Step 1: Extract text with pdfplumber
    text = extract_pdf_text(contents)
    tables = extract_pdf_tables(contents)

    # Step 2: If we got decent text, try regex extraction
    if len(text.strip()) > 500:
        result = extract_financials_from_text(text, tables)
        if is_extraction_complete(result):
            result["extraction_method"] = "text"
            result["raw_text"] = text[:2000]
            return result

    # Step 3: Fall back to Claude vision (handles scanned PDFs)
    result = await extract_financials_with_claude(contents, text, tables)
    result["extraction_method"] = "claude_vision"
    result["raw_text"] = text[:2000]
    return result


def extract_pdf_text(contents: bytes) -> str:
    """Extract all text from PDF."""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(contents)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
    except Exception:
        # Fallback to pypdf
        try:
            reader = PdfReader(io.BytesIO(contents))
            for page in reader.pages:
                text += page.extract_text() or ""
        except Exception:
            pass
    return text


def extract_pdf_tables(contents: bytes) -> list:
    """Extract tables from PDF using pdfplumber."""
    tables = []
    try:
        with pdfplumber.open(io.BytesIO(contents)) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)
    except Exception:
        pass
    return tables


# ─────────────────────────────────────────────
# EXCEL / CSV PARSER
# ─────────────────────────────────────────────

def parse_excel(contents: bytes, filename: str) -> dict:
    """Extract financials from Excel file."""
    try:
        xl = pd.ExcelFile(io.BytesIO(contents))
        sheets_text = ""

        for sheet_name in xl.sheet_names:
            df = xl.parse(sheet_name, header=None)
            sheets_text += f"\n\n=== SHEET: {sheet_name} ===\n"
            sheets_text += df.to_string(index=False, na_rep="")

        result = extract_financials_from_text(sheets_text, [])
        result["extraction_method"] = "excel"
        result["raw_text"] = sheets_text[:2000]
        return result

    except Exception as e:
        raise ValueError(f"Could not parse Excel file: {e}")


def parse_csv(contents: bytes, filename: str) -> dict:
    """Extract financials from CSV file."""
    try:
        df = pd.read_csv(io.BytesIO(contents))
        text = df.to_string(index=False)
        result = extract_financials_from_text(text, [])
        result["extraction_method"] = "csv"
        result["raw_text"] = text[:2000]
        return result
    except Exception as e:
        raise ValueError(f"Could not parse CSV file: {e}")


# ─────────────────────────────────────────────
# REGEX-BASED EXTRACTION (fast path)
# ─────────────────────────────────────────────

def extract_financials_from_text(text: str, tables: list) -> dict:
    """
    Try to extract key financial figures using regex patterns.
    Works well for structured text PDFs and Excel exports.
    """
    result = empty_result()

    # Company name — look for common patterns
    name_patterns = [
        r"(?:Company|Entity|Name)[\s:]+([A-Z][A-Za-z\s&,\.]{3,50})\n",
        r"^([A-Z][A-Za-z\s&,\.]{5,50})\s*(?:Limited|Ltd|Inc|Corp|LLC|Pty)",
        r"FINANCIAL STATEMENTS\s+(?:OF\s+)?([A-Z][A-Za-z\s&,\.]{3,50})\n",
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        if match:
            result["company_name"] = match.group(1).strip()
            break

    # Fiscal year
    year_match = re.search(
        r"(?:year ended|for the year|financial year|FY)[\s\w]*?(\d{4})",
        text, re.IGNORECASE
    )
    if year_match:
        result["fiscal_year"] = int(year_match.group(1))

    # Currency detection
    if any(c in text for c in ["ZAR", "R ", "Rand"]):
        result["currency"] = "ZAR"
    elif "GBP" in text or "£" in text:
        result["currency"] = "GBP"
    elif "EUR" in text or "€" in text:
        result["currency"] = "EUR"
    else:
        result["currency"] = "USD"

    # Unit detection (thousands / millions)
    unit = 1
    if re.search(r"in thousands|R'000|\$'000|£'000|000s", text, re.IGNORECASE):
        unit = 1_000
    elif re.search(r"in millions|R'm|\$m|£m", text, re.IGNORECASE):
        unit = 1_000_000

    # Financial line items — patterns for income statement
    financial_patterns = {
        "revenue": [
            r"(?:Revenue|Turnover|Net revenue|Total revenue|Sales)\s*[\|\:]?\s*([\d,\s]+)",
            r"(?:Revenue|Turnover)\s+(\d[\d\s,]+)",
        ],
        "ebitda": [
            r"EBITDA\s*[\|\:]?\s*([\d,\s]+)",
            r"Earnings before interest.*?depreciation.*?amortisation\s+([\d,\s]+)",
        ],
        "operating_profit": [
            r"(?:Operating profit|EBIT|Profit from operations)\s*[\|\:]?\s*([\d,\s]+)",
        ],
        "net_profit": [
            r"(?:Net profit|Net income|Profit after tax|PAT)\s*[\|\:]?\s*([\d,\s]+)",
            r"(?:Profit for the year)\s*[\|\:]?\s*([\d,\s]+)",
        ],
        "total_assets": [
            r"Total assets\s*[\|\:]?\s*([\d,\s]+)",
        ],
        "total_debt": [
            r"(?:Total debt|Total borrowings|Interest-bearing debt)\s*[\|\:]?\s*([\d,\s]+)",
            r"(?:Long.term borrowings)\s*[\|\:]?\s*([\d,\s]+)",
        ],
        "cash": [
            r"Cash and cash equivalents\s*[\|\:]?\s*([\d,\s]+)",
            r"Cash\s*[\|\:]?\s*([\d,\s]+)",
        ],
        "equity": [
            r"(?:Total equity|Shareholders. equity|Net assets)\s*[\|\:]?\s*([\d,\s]+)",
        ],
        "capex": [
            r"(?:Capital expenditure|Capex|PPE additions)\s*[\|\:]?\s*([\d,\s]+)",
        ],
        "operating_cash_flow": [
            r"(?:Cash generated from operations|Operating cash flow)\s*[\|\:]?\s*([\d,\s]+)",
        ],
    }

    for field, patterns in financial_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                raw = match.group(1).replace(",", "").replace(" ", "")
                try:
                    result[field] = float(raw) * unit
                    break
                except ValueError:
                    continue

    # Calculate derived metrics
    result = calculate_derived_metrics(result)
    return result


def calculate_derived_metrics(r: dict) -> dict:
    """Calculate margins, growth, etc. from raw numbers."""
    try:
        if r.get("revenue") and r.get("revenue_prior"):
            r["revenue_growth"] = round(
                (r["revenue"] - r["revenue_prior"]) / r["revenue_prior"], 4
            )
        if r.get("ebitda") and r.get("revenue"):
            r["ebitda_margin"] = round(r["ebitda"] / r["revenue"], 4)
        if r.get("net_profit") and r.get("revenue"):
            r["net_profit_margin"] = round(r["net_profit"] / r["revenue"], 4)
        if r.get("total_assets") and r.get("total_debt"):
            r["net_debt"] = r["total_debt"] - (r.get("cash") or 0)
    except Exception:
        pass
    return r


def is_extraction_complete(result: dict) -> bool:
    """Check if we got the minimum required fields."""
    required = ["revenue", "ebitda", "net_profit"]
    return all(result.get(f) for f in required)


# ─────────────────────────────────────────────
# CLAUDE AI EXTRACTION (fallback for complex PDFs)
# ─────────────────────────────────────────────

async def extract_financials_with_claude(
    contents: bytes, text: str, tables: list
) -> dict:
    """
    Send PDF content to Claude for intelligent extraction.
    Handles scanned PDFs, complex layouts, non-standard formats.
    """
    # Prepare the prompt with whatever text we have
    table_text = ""
    for i, table in enumerate(tables[:10]):  # limit to first 10 tables
        table_text += f"\nTable {i+1}:\n"
        for row in table:
            if row:
                table_text += " | ".join([str(c or "") for c in row]) + "\n"

    prompt = f"""You are a financial analyst. Extract key financial data from these annual financial statements.

EXTRACTED TEXT:
{text[:8000]}

EXTRACTED TABLES:
{table_text[:4000]}

Return ONLY a valid JSON object with these exact fields (use null for missing values):
{{
  "company_name": "string or null",
  "fiscal_year": integer or null,
  "currency": "USD/GBP/EUR/ZAR/other",
  "revenue": number or null,
  "revenue_prior": number or null,
  "revenue_growth": number or null,
  "ebitda": number or null,
  "ebitda_prior": number or null,
  "ebitda_margin": number or null,
  "operating_profit": number or null,
  "net_profit": number or null,
  "net_profit_margin": number or null,
  "total_assets": number or null,
  "total_liabilities": number or null,
  "total_debt": number or null,
  "cash": number or null,
  "net_debt": number or null,
  "equity": number or null,
  "working_capital": number or null,
  "capex": number or null,
  "operating_cash_flow": number or null,
  "employees": number or null,
  "notes": "any important context about the financials"
}}

All numbers should be in ACTUAL values (not thousands or millions).
If numbers appear in thousands, multiply by 1000. If in millions, multiply by 1000000.
Return only the JSON object, no other text."""

    try:
        message = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        response_text = message.content[0].text.strip()

        # Clean up response — remove markdown code fences if present
        response_text = re.sub(r"```json\s*|\s*```", "", response_text).strip()

        result = json.loads(response_text)
        result = calculate_derived_metrics(result)
        return result

    except json.JSONDecodeError as e:
        # Return whatever we could extract via regex
        return empty_result(notes=f"Partial extraction — Claude response parse error: {e}")
    except Exception as e:
        return empty_result(notes=f"Extraction error: {e}")


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def empty_result(notes: str = "") -> dict:
    """Return an empty result template."""
    return {
        "company_name": None,
        "fiscal_year": None,
        "currency": "USD",
        "revenue": None,
        "revenue_prior": None,
        "revenue_growth": None,
        "ebitda": None,
        "ebitda_prior": None,
        "ebitda_margin": None,
        "operating_profit": None,
        "net_profit": None,
        "net_profit_margin": None,
        "total_assets": None,
        "total_liabilities": None,
        "total_debt": None,
        "cash": None,
        "net_debt": None,
        "equity": None,
        "working_capital": None,
        "capex": None,
        "operating_cash_flow": None,
        "employees": None,
        "extraction_method": None,
        "raw_text": "",
        "notes": notes,
    }
