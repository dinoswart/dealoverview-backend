"""
DealOverview Backend API
========================
Three endpoints:
  POST /parse-afs        — Upload PDF or Excel AFS, extract financials
  POST /generate-cim     — Generate full CIM from parsed financials
  POST /financial-models — Run DCF, LBO, Comparables, Sensitivity models

Deploy to Railway.app (free tier):
  1. Push this folder to a GitHub repo
  2. Connect Railway to that repo
  3. Railway auto-detects Python and deploys

Install:
  pip install -r requirements.txt
Run locally:
  uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn

from parser import parse_afs_file
from cim_generator import generate_cim
from financial_models import run_all_models

app = FastAPI(
    title="DealOverview API",
    description="AFS Parser, CIM Generator, Financial Models",
    version="1.0.0"
)

# Allow requests from dealoverview.com and localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dealoverview.com",
        "https://www.dealoverview.com",
        "https://deal-oracle-suite.lovable.app",
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# ENDPOINT 1: AFS PARSER
# ─────────────────────────────────────────────

@app.post("/parse-afs")
async def parse_afs(file: UploadFile = File(...)):
    """
    Upload an AFS (PDF or Excel).
    Returns structured financial data as JSON.

    Accepts: .pdf, .xlsx, .xls, .csv
    Returns: {
        company_name, fiscal_year, currency,
        revenue, revenue_prior, revenue_growth,
        ebitda, ebitda_prior, ebitda_margin,
        net_profit, net_profit_margin,
        total_assets, total_debt, cash,
        equity, working_capital,
        capex, operating_cash_flow,
        employees (if found),
        raw_text (truncated, for debugging)
    }
    """
    allowed = [".pdf", ".xlsx", ".xls", ".csv"]
    filename = file.filename.lower()
    if not any(filename.endswith(ext) for ext in allowed):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Please upload: {', '.join(allowed)}"
        )

    contents = await file.read()
    result = await parse_afs_file(contents, file.filename)
    return result


# ─────────────────────────────────────────────
# ENDPOINT 2: CIM GENERATOR
# ─────────────────────────────────────────────

class CIMRequest(BaseModel):
    financials: dict           # Output from /parse-afs
    deal_context: Optional[dict] = {}
    # Optional overrides:
    # deal_context = {
    #   asking_price: 5000000,
    #   sector: "Industrial Manufacturing",
    #   advisor_name: "Smith & Partners",
    #   deal_rationale: "Founder retirement",
    #   key_strengths: ["Strong recurring revenue", "Market leader"],
    # }

@app.post("/generate-cim")
async def generate_cim_endpoint(request: CIMRequest):
    """
    Takes parsed financials + optional deal context.
    Returns a full CIM with all sections as structured text.

    Returns: {
        executive_summary,
        business_overview,
        financial_performance,
        ebitda_bridge,
        growth_opportunities,
        management_summary,
        transaction_details,
        full_cim_markdown,   ← complete CIM as markdown
        generated_at
    }
    """
    result = await generate_cim(request.financials, request.deal_context)
    return result


# ─────────────────────────────────────────────
# ENDPOINT 3: FINANCIAL MODELS
# ─────────────────────────────────────────────

class ModelsRequest(BaseModel):
    financials: dict           # Output from /parse-afs
    assumptions: Optional[dict] = {}
    # assumptions = {
    #   wacc: 0.12,
    #   terminal_growth: 0.025,
    #   revenue_growth_rates: [0.08, 0.10, 0.09, 0.08, 0.07],
    #   ebitda_margin_target: 0.22,
    #   debt_multiple: 3.5,
    #   entry_multiple: 7.0,
    #   exit_multiple: 8.0,
    #   hold_period: 5,
    #   comp_multiples: [6.5, 7.2, 8.1, 6.8],  # EV/EBITDA comps
    # }

@app.post("/financial-models")
async def financial_models_endpoint(request: ModelsRequest):
    """
    Runs all financial models auto-populated from AFS data.

    Returns: {
        dcf: { enterprise_value, equity_value, per_share, assumptions, cash_flows },
        lbo: { irr, moic, entry_ev, exit_ev, returns_waterfall },
        comparables: { ev_ebitda_range, ev_revenue_range, implied_value_range },
        sensitivity: { wacc_vs_growth_table, margin_vs_revenue_table },
        valuation_summary: { low, mid, high, methodology_weights },
        excel_data: { ... }  ← structured data for Excel export
    }
    """
    result = run_all_models(request.financials, request.assumptions)
    return result


# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────

@app.get("/")
def health():
    return {
        "status": "live",
        "product": "DealOverview API",
        "version": "1.0.0",
        "endpoints": ["/parse-afs", "/generate-cim", "/financial-models"]
    }


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
