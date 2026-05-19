"""
CIM Generator
=============
Takes parsed financials + deal context.
Uses Claude to write a full, professional CIM.
Outputs structured sections + complete markdown document.
"""

import json
import asyncio
from datetime import datetime
from typing import Optional
import anthropic

client = anthropic.AsyncAnthropic()
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"


def fmt(value, currency="$", unit="", decimals=1):
    """Format a number for display in the CIM."""
    if value is None:
        return "N/A"
    if abs(value) >= 1_000_000:
        return f"{currency}{value/1_000_000:,.{decimals}f}M{unit}"
    elif abs(value) >= 1_000:
        return f"{currency}{value/1_000:,.{decimals}f}K{unit}"
    else:
        return f"{currency}{value:,.{decimals}f}{unit}"

def fmt_pct(value):
    if value is None:
        return "N/A"
    return f"{value*100:.1f}%"

def fmt_multiple(ebitda, ev):
    if not ebitda or not ev:
        return "N/A"
    return f"{ev/ebitda:.1f}x"


async def generate_cim(financials: dict, deal_context: dict) -> dict:
    """
    Generate all CIM sections in parallel for speed.
    Returns structured sections + full markdown CIM.
    """
    company = financials.get("company_name") or deal_context.get("company_name") or "the Company"
    sector = deal_context.get("sector", "")
    currency_sym = get_currency_symbol(financials.get("currency", "USD"))
    asking_price = deal_context.get("asking_price")
    advisor = deal_context.get("advisor_name", "")
    rationale = deal_context.get("deal_rationale", "")
    strengths = deal_context.get("key_strengths", [])

    # Build a shared financial summary for all prompts
    fin_summary = build_financial_summary(financials, currency_sym)

    # Generate all sections in parallel
    sections = await asyncio.gather(
        gen_executive_summary(company, sector, financials, fin_summary, asking_price, currency_sym, rationale, strengths),
        gen_business_overview(company, sector, financials, fin_summary, deal_context),
        gen_financial_performance(company, financials, fin_summary, currency_sym),
        gen_ebitda_bridge(company, financials, fin_summary, currency_sym),
        gen_growth_opportunities(company, sector, financials, fin_summary),
        gen_management_summary(company, financials, deal_context),
        gen_transaction_details(company, financials, fin_summary, asking_price, currency_sym, advisor, deal_context),
    )

    (
        executive_summary,
        business_overview,
        financial_performance,
        ebitda_bridge,
        growth_opportunities,
        management_summary,
        transaction_details,
    ) = sections

    # Assemble full CIM markdown
    full_cim = assemble_full_cim(
        company=company,
        sector=sector,
        advisor=advisor,
        executive_summary=executive_summary,
        business_overview=business_overview,
        financial_performance=financial_performance,
        ebitda_bridge=ebitda_bridge,
        growth_opportunities=growth_opportunities,
        management_summary=management_summary,
        transaction_details=transaction_details,
        financials=financials,
        currency_sym=currency_sym,
        asking_price=asking_price,
    )

    return {
        "executive_summary": executive_summary,
        "business_overview": business_overview,
        "financial_performance": financial_performance,
        "ebitda_bridge": ebitda_bridge,
        "growth_opportunities": growth_opportunities,
        "management_summary": management_summary,
        "transaction_details": transaction_details,
        "full_cim_markdown": full_cim,
        "generated_at": datetime.utcnow().isoformat(),
        "company_name": company,
        "sector": sector,
    }


# ─────────────────────────────────────────────
# SECTION GENERATORS
# ─────────────────────────────────────────────

async def gen_executive_summary(company, sector, financials, fin_summary, asking_price, currency_sym, rationale, strengths):
    asking_str = fmt(asking_price, currency_sym) if asking_price else "available upon request"
    strengths_str = "\n".join(f"- {s}" for s in strengths) if strengths else "- Strong financial performance\n- Established market position\n- Experienced management team"

    prompt = f"""You are a senior M&A advisor writing a Confidential Information Memorandum.

Write the EXECUTIVE SUMMARY section for {company} ({sector}).

Financial highlights:
{fin_summary}

Asking price: {asking_str}
Deal rationale: {rationale or "The shareholders are seeking a strategic transaction."}
Key strengths:
{strengths_str}

Write 3-4 paragraphs covering:
1. Company overview and market position
2. Financial highlights and performance trajectory
3. Key investment highlights
4. Transaction overview and asking price

Tone: professional, factual, compelling. Written as a sell-side advisor presenting to sophisticated buyers.
Do not use placeholder text. Write real, specific content based on the financial data provided.
Use actual numbers from the financials."""

    return await call_claude(prompt, max_tokens=600)


async def gen_business_overview(company, sector, financials, fin_summary, deal_context):
    prompt = f"""You are a senior M&A advisor writing a Confidential Information Memorandum.

Write the BUSINESS OVERVIEW section for {company} ({sector}).

Financial context:
{fin_summary}

Write 3-4 paragraphs covering:
1. Business description — what the company does, how it makes money
2. Market position and competitive landscape
3. Customer base and key relationships
4. Operational overview

Base the description on the sector ({sector}) and financial profile.
Be specific and professional. Do not use generic filler text.
Infer reasonable business characteristics from the financial data."""

    return await call_claude(prompt, max_tokens=500)


async def gen_financial_performance(company, financials, fin_summary, currency_sym):
    prompt = f"""You are a senior M&A advisor writing a Confidential Information Memorandum.

Write the FINANCIAL PERFORMANCE section for {company}.

Actual financial data:
{fin_summary}

Write this section covering:
1. Revenue performance — current year, prior year, growth rate, commentary
2. EBITDA performance — margin, trajectory, drivers
3. Profitability — net profit, margins
4. Balance sheet highlights — assets, debt, cash position
5. Cash flow — operating cash generation

Use the actual numbers. Format key figures clearly.
Write as a factual financial narrative that gives buyers confidence in the numbers.
Include a summary table of key metrics."""

    return await call_claude(prompt, max_tokens=600)


async def gen_ebitda_bridge(company, financials, fin_summary, currency_sym):
    ebitda = financials.get("ebitda")
    ebitda_prior = financials.get("ebitda_prior")

    if not ebitda:
        return "EBITDA bridge not available — financial data insufficient."

    prompt = f"""You are a senior M&A advisor writing a Confidential Information Memorandum.

Write the EBITDA BRIDGE section for {company}.

Current EBITDA: {fmt(ebitda, currency_sym)}
Prior year EBITDA: {fmt(ebitda_prior, currency_sym) if ebitda_prior else 'N/A'}
EBITDA margin: {fmt_pct(financials.get("ebitda_margin"))}

Full financial context:
{fin_summary}

Write a concise EBITDA bridge section covering:
1. Movement from prior year to current year EBITDA (if prior year available)
2. Key drivers of EBITDA performance
3. Any normalisation adjustments that should be considered
4. Run-rate EBITDA commentary

Be analytical and specific. This section is read carefully by financial buyers."""

    return await call_claude(prompt, max_tokens=400)


async def gen_growth_opportunities(company, sector, financials, fin_summary):
    prompt = f"""You are a senior M&A advisor writing a Confidential Information Memorandum.

Write the GROWTH OPPORTUNITIES section for {company} ({sector}).

Financial context:
{fin_summary}

Write 4-5 specific, credible growth opportunities covering:
1. Organic growth — new markets, products, customers
2. Operational leverage — margin improvement opportunities
3. Geographic expansion
4. Digital/technology enhancement
5. Strategic acquisition potential (buy-and-build)

Each opportunity should be:
- Specific and realistic given the company's financial profile
- Quantified where possible
- Presented as a compelling investment thesis for a buyer

Do not write generic growth points. Make them specific to this company and sector."""

    return await call_claude(prompt, max_tokens=500)


async def gen_management_summary(company, financials, deal_context):
    prompt = f"""You are a senior M&A advisor writing a Confidential Information Memorandum.

Write the MANAGEMENT & TEAM section for {company}.

Deal context: {json.dumps(deal_context)}

Write a professional management section covering:
1. Overview of the leadership team structure
2. Key management capabilities and tenure
3. Management's role post-transaction
4. Succession planning and depth of team

Since specific management names are not provided, write this section describing the typical management structure for a company of this size and sector, noting that full CVs are available in the data room.

Keep it professional and reassuring for buyers."""

    return await call_claude(prompt, max_tokens=350)


async def gen_transaction_details(company, financials, fin_summary, asking_price, currency_sym, advisor, deal_context):
    asking_str = fmt(asking_price, currency_sym) if asking_price else "available upon request"
    ebitda = financials.get("ebitda")
    multiple_str = fmt_multiple(ebitda, asking_price) if ebitda and asking_price else "N/A"

    prompt = f"""You are a senior M&A advisor writing a Confidential Information Memorandum.

Write the TRANSACTION DETAILS section for {company}.

Asking price: {asking_str}
Implied EBITDA multiple: {multiple_str}
Advisor: {advisor or "the appointed advisor"}

Financial context:
{fin_summary}

Write this section covering:
1. Transaction overview — what is being sold (100% equity, assets, etc.)
2. Indicative asking price and valuation rationale
3. Process timeline — key milestones
4. Buyer requirements — NDA, proof of funds, management meetings
5. Contact and next steps

Standard M&A process language. Professional and clear."""

    return await call_claude(prompt, max_tokens=400)


# ─────────────────────────────────────────────
# ASSEMBLER
# ─────────────────────────────────────────────

def assemble_full_cim(company, sector, advisor, executive_summary, business_overview,
                       financial_performance, ebitda_bridge, growth_opportunities,
                       management_summary, transaction_details, financials,
                       currency_sym, asking_price) -> str:
    """Assemble all sections into a complete CIM markdown document."""
    rev = fmt(financials.get("revenue"), currency_sym)
    ebitda = fmt(financials.get("ebitda"), currency_sym)
    margin = fmt_pct(financials.get("ebitda_margin"))
    asking = fmt(asking_price, currency_sym) if asking_price else "Available upon request"
    year = financials.get("fiscal_year", "")

    cim = f"""# CONFIDENTIAL INFORMATION MEMORANDUM

## {company.upper()}

**{sector}**

---

*This Confidential Information Memorandum ("CIM") has been prepared by {advisor or "the appointed M&A advisor"} exclusively for the use of prospective purchasers in connection with the proposed sale of {company}. This document is strictly confidential and may not be reproduced or distributed without prior written consent.*

---

### KEY METRICS AT A GLANCE

| Metric | Value |
|--------|-------|
| Revenue ({year}) | {rev} |
| EBITDA ({year}) | {ebitda} |
| EBITDA Margin | {margin} |
| Asking Price | {asking} |
| Implied Multiple | {fmt_multiple(financials.get("ebitda"), asking_price)} |

---

## 1. EXECUTIVE SUMMARY

{executive_summary}

---

## 2. BUSINESS OVERVIEW

{business_overview}

---

## 3. FINANCIAL PERFORMANCE

{financial_performance}

---

## 4. EBITDA BRIDGE

{ebitda_bridge}

---

## 5. GROWTH OPPORTUNITIES

{growth_opportunities}

---

## 6. MANAGEMENT & TEAM

{management_summary}

---

## 7. TRANSACTION DETAILS

{transaction_details}

---

## 8. DISCLAIMER

*This CIM has been prepared from information provided by the Company and its management. Whilst reasonable care has been taken in its preparation, no representation or warranty, express or implied, is made as to the accuracy or completeness of the information contained herein. Prospective purchasers should conduct their own due diligence investigation.*

---

*Generated by DealOverview AI — dealoverview.com*
*{datetime.utcnow().strftime("%B %Y")}*
"""
    return cim


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

async def call_claude(prompt: str, max_tokens: int = 500) -> str:
    """Call Claude API and return text response."""
    try:
        message = await client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text.strip()
    except Exception as e:
        return f"[Section generation error: {e}]"


def build_financial_summary(financials: dict, currency_sym: str) -> str:
    """Build a human-readable financial summary for prompts."""
    lines = []
    fields = [
        ("Revenue (current year)", "revenue"),
        ("Revenue (prior year)", "revenue_prior"),
        ("Revenue growth", "revenue_growth"),
        ("EBITDA", "ebitda"),
        ("EBITDA margin", "ebitda_margin"),
        ("Net profit", "net_profit"),
        ("Net profit margin", "net_profit_margin"),
        ("Total assets", "total_assets"),
        ("Total debt", "total_debt"),
        ("Cash", "cash"),
        ("Net debt", "net_debt"),
        ("Equity", "equity"),
        ("Operating cash flow", "operating_cash_flow"),
        ("Capex", "capex"),
        ("Employees", "employees"),
    ]
    for label, key in fields:
        val = financials.get(key)
        if val is not None:
            if "margin" in key or "growth" in key:
                lines.append(f"{label}: {fmt_pct(val)}")
            elif key == "employees":
                lines.append(f"{label}: {int(val):,}")
            else:
                lines.append(f"{label}: {fmt(val, currency_sym)}")

    return "\n".join(lines) if lines else "Financial data not available."


def get_currency_symbol(currency: str) -> str:
    symbols = {"USD": "$", "GBP": "£", "EUR": "€", "ZAR": "R"}
    return symbols.get(currency, "$")
