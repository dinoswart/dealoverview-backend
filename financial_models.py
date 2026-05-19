"""
Financial Models
================
All models auto-populated from parsed AFS data.
Runs synchronously (pure maths — no API calls needed).

Models:
  1. DCF — Discounted Cash Flow
  2. LBO — Leveraged Buyout
  3. Comparables — EV/EBITDA, EV/Revenue
  4. Sensitivity — WACC vs Growth, Margin vs Revenue
  5. Valuation Summary — blended range
  6. Excel data — structured for export
"""

import math
from typing import Optional


# ─────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────

def run_all_models(financials: dict, assumptions: dict) -> dict:
    """Run all models and return complete results."""
    # Fill in defaults for missing assumptions
    a = build_assumptions(financials, assumptions)

    # Run all models
    dcf_result     = run_dcf(financials, a)
    lbo_result     = run_lbo(financials, a)
    comps_result   = run_comparables(financials, a)
    dfs_result     = run_debt_financing_scenarios(financials, a)
    sensitivity    = run_sensitivity(financials, a)
    summary        = build_valuation_summary(dcf_result, lbo_result, comps_result, financials, a)
    excel_data     = build_excel_data(financials, a, dcf_result, lbo_result, comps_result, sensitivity)

    return {
        "dcf":              dcf_result,
        "lbo":              lbo_result,
        "comparables":      comps_result,
        "debt_financing":   dfs_result,
        "sensitivity":      sensitivity,
        "valuation_summary": summary,
        "excel_data":       excel_data,
        "assumptions_used": a,
    }


# ─────────────────────────────────────────────
# ASSUMPTIONS BUILDER
# ─────────────────────────────────────────────

def build_assumptions(financials: dict, overrides: dict) -> dict:
    """Build complete assumptions, using defaults where not provided."""
    revenue = financials.get("revenue") or 0
    ebitda  = financials.get("ebitda") or 0
    margin  = (ebitda / revenue) if revenue > 0 else 0.15

    # Default revenue growth rates — 5 years
    default_growth = [0.08, 0.09, 0.10, 0.09, 0.08]

    # Default WACC based on size (smaller company = higher risk)
    if revenue < 5_000_000:
        default_wacc = 0.15
    elif revenue < 20_000_000:
        default_wacc = 0.13
    elif revenue < 100_000_000:
        default_wacc = 0.12
    else:
        default_wacc = 0.10

    return {
        "wacc":                 overrides.get("wacc", default_wacc),
        "terminal_growth":      overrides.get("terminal_growth", 0.025),
        "revenue_growth_rates": overrides.get("revenue_growth_rates", default_growth),
        "ebitda_margin_target": overrides.get("ebitda_margin_target", min(margin + 0.02, 0.35)),
        "tax_rate":             overrides.get("tax_rate", 0.28),
        "capex_pct_revenue":    overrides.get("capex_pct_revenue",
                                    (financials.get("capex") or revenue * 0.03) / revenue if revenue else 0.03),
        "nwc_pct_revenue":      overrides.get("nwc_pct_revenue", 0.05),
        "da_pct_revenue":       overrides.get("da_pct_revenue", 0.03),
        # LBO
        "debt_multiple":        overrides.get("debt_multiple", 3.5),
        "entry_multiple":       overrides.get("entry_multiple", 7.0),
        "exit_multiple":        overrides.get("exit_multiple", 8.0),
        "hold_period":          overrides.get("hold_period", 5),
        "debt_interest_rate":   overrides.get("debt_interest_rate", 0.07),
        "debt_amortization":    overrides.get("debt_amortization", 0.10),
        # Comparables
        "comp_multiples":       overrides.get("comp_multiples", [6.5, 7.2, 8.1, 6.8, 7.5]),
        "comp_rev_multiples":   overrides.get("comp_rev_multiples", [1.2, 1.5, 1.8, 1.4]),
        # Debt financing
        "senior_debt_multiple": overrides.get("senior_debt_multiple", 2.5),
        "total_debt_multiple":  overrides.get("total_debt_multiple", 4.0),
    }


# ─────────────────────────────────────────────
# MODEL 1: DCF
# ─────────────────────────────────────────────

def run_dcf(financials: dict, a: dict) -> dict:
    """
    Standard 5-year DCF with terminal value.
    Uses FCFF (Free Cash Flow to Firm) approach.
    """
    revenue   = financials.get("revenue") or 0
    ebitda    = financials.get("ebitda") or 0
    net_debt  = financials.get("net_debt") or 0
    wacc      = a["wacc"]
    tg        = a["terminal_growth"]
    tax_rate  = a["tax_rate"]
    da_pct    = a["da_pct_revenue"]
    capex_pct = a["capex_pct_revenue"]
    nwc_pct   = a["nwc_pct_revenue"]
    growth    = a["revenue_growth_rates"]
    margin    = a["ebitda_margin_target"]

    # Project 5-year cash flows
    years     = list(range(1, 6))
    revenues  = []
    ebitdas   = []
    fcffs     = []
    pv_fcffs  = []

    rev = revenue
    prev_rev = revenue

    for i, yr in enumerate(years):
        g = growth[i] if i < len(growth) else growth[-1]
        rev = rev * (1 + g)
        revenues.append(rev)

        ebitda_proj = rev * margin
        ebitdas.append(ebitda_proj)

        da        = rev * da_pct
        ebit      = ebitda_proj - da
        nopat     = ebit * (1 - tax_rate)
        capex_val = rev * capex_pct
        d_nwc     = (rev - prev_rev) * nwc_pct
        fcff      = nopat + da - capex_val - d_nwc
        fcffs.append(fcff)

        pv = fcff / ((1 + wacc) ** yr)
        pv_fcffs.append(pv)
        prev_rev = rev

    # Terminal value — Gordon Growth Model
    terminal_fcff = fcffs[-1] * (1 + tg)
    terminal_value = terminal_fcff / (wacc - tg)
    pv_terminal = terminal_value / ((1 + wacc) ** 5)

    # Enterprise & Equity value
    sum_pv_fcff = sum(pv_fcffs)
    enterprise_value = sum_pv_fcff + pv_terminal
    equity_value = enterprise_value - net_debt

    # Implied EV/EBITDA
    implied_multiple = enterprise_value / ebitda if ebitda > 0 else None

    return {
        "enterprise_value":   round(enterprise_value),
        "equity_value":       round(equity_value),
        "pv_of_fcffs":        round(sum_pv_fcff),
        "pv_of_terminal":     round(pv_terminal),
        "terminal_value":     round(terminal_value),
        "implied_ev_ebitda":  round(implied_multiple, 1) if implied_multiple else None,
        "projected_revenues": [round(r) for r in revenues],
        "projected_ebitdas":  [round(e) for e in ebitdas],
        "projected_fcffs":    [round(f) for f in fcffs],
        "pv_fcffs":           [round(p) for p in pv_fcffs],
        "assumptions": {
            "wacc":            wacc,
            "terminal_growth": tg,
            "growth_rates":    growth,
            "ebitda_margin":   margin,
            "tax_rate":        tax_rate,
        }
    }


# ─────────────────────────────────────────────
# MODEL 2: LBO
# ─────────────────────────────────────────────

def run_lbo(financials: dict, a: dict) -> dict:
    """
    Standard LBO model.
    Entry → debt paydown over hold period → exit → returns.
    """
    ebitda        = financials.get("ebitda") or 0
    revenue       = financials.get("revenue") or 0
    net_debt      = financials.get("net_debt") or 0
    ocf           = financials.get("operating_cash_flow") or ebitda * 0.7
    entry_mult    = a["entry_multiple"]
    exit_mult     = a["exit_multiple"]
    hold          = a["hold_period"]
    debt_mult     = a["debt_multiple"]
    interest_rate = a["debt_interest_rate"]
    amort         = a["debt_amortization"]
    growth        = a["revenue_growth_rates"]
    margin        = a["ebitda_margin_target"]

    # Entry
    entry_ev      = ebitda * entry_mult
    entry_debt    = ebitda * debt_mult
    entry_equity  = entry_ev - entry_debt

    # Debt schedule
    debt = entry_debt
    debt_schedule = []
    ebitda_proj = ebitda

    for i in range(hold):
        g = growth[i] if i < len(growth) else growth[-1]
        rev_proj   = revenue * ((1 + g) ** (i + 1))
        ebitda_proj = rev_proj * margin
        interest    = debt * interest_rate
        amort_pay   = entry_debt * amort
        fcf_to_debt = max(ebitda_proj * 0.6 - interest, 0)  # ~60% cash conversion
        debt_paydown = min(fcf_to_debt, debt)
        debt        = max(debt - debt_paydown, 0)
        debt_schedule.append({
            "year":        i + 1,
            "ebitda":      round(ebitda_proj),
            "interest":    round(interest),
            "debt_paydown":round(debt_paydown),
            "ending_debt": round(debt),
        })

    # Exit
    exit_ev     = ebitda_proj * exit_mult
    exit_equity = exit_ev - debt

    # Returns
    moic = exit_equity / entry_equity if entry_equity > 0 else 0
    irr  = (moic ** (1/hold) - 1) if moic > 0 and hold > 0 else 0

    # Returns waterfall (simplified: management 10%, PE 90% up to 2x, then 80/20)
    mgmt_proceeds = 0
    pe_proceeds   = exit_equity
    if moic > 2:
        above_2x     = exit_equity - (entry_equity * 2)
        mgmt_proceeds = above_2x * 0.20
        pe_proceeds   = exit_equity - mgmt_proceeds

    return {
        "entry_ev":       round(entry_ev),
        "entry_equity":   round(entry_equity),
        "entry_debt":     round(entry_debt),
        "exit_ev":        round(exit_ev),
        "exit_equity":    round(exit_equity),
        "exit_debt":      round(debt),
        "irr":            round(irr * 100, 1),       # as percentage
        "moic":           round(moic, 2),
        "hold_period":    hold,
        "debt_schedule":  debt_schedule,
        "returns_waterfall": {
            "pe_proceeds":   round(pe_proceeds),
            "mgmt_proceeds": round(mgmt_proceeds),
            "total":         round(exit_equity),
        },
        "assumptions": {
            "entry_multiple":    entry_mult,
            "exit_multiple":     exit_mult,
            "debt_multiple":     debt_mult,
            "interest_rate":     interest_rate,
            "hold_period_years": hold,
        }
    }


# ─────────────────────────────────────────────
# MODEL 3: COMPARABLE COMPANIES
# ─────────────────────────────────────────────

def run_comparables(financials: dict, a: dict) -> dict:
    """
    Comparable company analysis using provided or default multiples.
    """
    ebitda  = financials.get("ebitda") or 0
    revenue = financials.get("revenue") or 0
    comps   = a["comp_multiples"]
    rev_comps = a["comp_rev_multiples"]

    if not ebitda:
        return {"error": "EBITDA required for comparables analysis"}

    # EV/EBITDA analysis
    ev_values = [ebitda * m for m in comps]
    ev_low    = min(ev_values)
    ev_high   = max(ev_values)
    ev_median = sorted(ev_values)[len(ev_values)//2]
    ev_mean   = sum(ev_values) / len(ev_values)

    # EV/Revenue analysis
    rev_ev_values = [revenue * m for m in rev_comps]
    rev_ev_low    = min(rev_ev_values)
    rev_ev_high   = max(rev_ev_values)
    rev_ev_median = sorted(rev_ev_values)[len(rev_ev_values)//2]

    return {
        "ev_ebitda": {
            "multiples_used": comps,
            "low_multiple":   min(comps),
            "high_multiple":  max(comps),
            "median_multiple": sorted(comps)[len(comps)//2],
            "implied_ev_low":    round(ev_low),
            "implied_ev_high":   round(ev_high),
            "implied_ev_median": round(ev_median),
            "implied_ev_mean":   round(ev_mean),
        },
        "ev_revenue": {
            "multiples_used": rev_comps,
            "low_multiple":   min(rev_comps),
            "high_multiple":  max(rev_comps),
            "implied_ev_low":    round(rev_ev_low),
            "implied_ev_high":   round(rev_ev_high),
            "implied_ev_median": round(rev_ev_median),
        },
        "blended_ev_range": {
            "low":    round((ev_low + rev_ev_low) / 2),
            "median": round((ev_median + rev_ev_median) / 2),
            "high":   round((ev_high + rev_ev_high) / 2),
        }
    }


# ─────────────────────────────────────────────
# MODEL 4: DEBT FINANCING SCENARIOS
# ─────────────────────────────────────────────

def run_debt_financing_scenarios(financials: dict, a: dict) -> dict:
    """
    Models different debt structures and tests serviceability.
    """
    ebitda   = financials.get("ebitda") or 0
    revenue  = financials.get("revenue") or 0
    ocf      = financials.get("operating_cash_flow") or ebitda * 0.7
    rate     = a["debt_interest_rate"]

    scenarios = []
    for mult in [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]:
        debt        = ebitda * mult
        interest    = debt * rate
        dscr        = ocf / interest if interest > 0 else None
        leverage    = debt / ebitda if ebitda > 0 else None
        serviceable = dscr >= 1.2 if dscr else False

        scenarios.append({
            "debt_multiple": mult,
            "debt_amount":   round(debt),
            "annual_interest": round(interest),
            "dscr":          round(dscr, 2) if dscr else None,
            "leverage_ratio": round(leverage, 1) if leverage else None,
            "serviceable":   serviceable,
            "rating":        "Conservative" if mult <= 2.5 else
                            "Moderate" if mult <= 3.5 else
                            "Aggressive" if mult <= 4.5 else "Stretched",
        })

    return {
        "scenarios": scenarios,
        "recommended_structure": next(
            (s for s in reversed(scenarios) if s["serviceable"]), scenarios[0]
        ),
        "max_serviceable_debt": max(
            (s["debt_amount"] for s in scenarios if s["serviceable"]), default=0
        ),
        "assumptions": {
            "interest_rate": rate,
            "ocf_used":      round(ocf),
            "ebitda_used":   round(ebitda),
        }
    }


# ─────────────────────────────────────────────
# MODEL 5: SENSITIVITY ANALYSIS
# ─────────────────────────────────────────────

def run_sensitivity(financials: dict, a: dict) -> dict:
    """
    Two sensitivity tables:
    1. WACC vs Terminal Growth Rate → Enterprise Value
    2. EBITDA Margin vs Revenue Growth → Enterprise Value
    """
    revenue  = financials.get("revenue") or 0
    ebitda   = financials.get("ebitda") or 0
    net_debt = financials.get("net_debt") or 0

    # Table 1: WACC vs Terminal Growth
    wacc_range = [a["wacc"] - 0.02, a["wacc"] - 0.01, a["wacc"],
                  a["wacc"] + 0.01, a["wacc"] + 0.02]
    tg_range   = [0.015, 0.020, 0.025, 0.030, 0.035]

    wacc_tg_table = []
    for wacc in wacc_range:
        row = {"wacc": round(wacc * 100, 1)}
        for tg in tg_range:
            # Quick DCF approximation
            result = run_dcf(financials, {**a, "wacc": wacc, "terminal_growth": tg})
            row[f"tg_{round(tg*100,1)}"] = round(result["enterprise_value"])
        wacc_tg_table.append(row)

    # Table 2: EBITDA Margin vs Revenue Growth
    margin_range = [a["ebitda_margin_target"] - 0.04,
                    a["ebitda_margin_target"] - 0.02,
                    a["ebitda_margin_target"],
                    a["ebitda_margin_target"] + 0.02,
                    a["ebitda_margin_target"] + 0.04]
    growth_range = [0.04, 0.06, 0.08, 0.10, 0.12]

    margin_growth_table = []
    for margin in margin_range:
        row = {"ebitda_margin": round(margin * 100, 1)}
        for g in growth_range:
            result = run_dcf(financials, {
                **a,
                "ebitda_margin_target": margin,
                "revenue_growth_rates": [g] * 5
            })
            row[f"growth_{round(g*100,0)}"] = round(result["enterprise_value"])
        margin_growth_table.append(row)

    return {
        "wacc_vs_terminal_growth": {
            "description": "Enterprise Value — WACC (rows) vs Terminal Growth Rate (columns)",
            "wacc_values": [round(w * 100, 1) for w in wacc_range],
            "tg_values":   [round(t * 100, 1) for t in tg_range],
            "table":       wacc_tg_table,
        },
        "margin_vs_growth": {
            "description": "Enterprise Value — EBITDA Margin (rows) vs Revenue Growth (columns)",
            "margin_values": [round(m * 100, 1) for m in margin_range],
            "growth_values": [round(g * 100, 0) for g in growth_range],
            "table":         margin_growth_table,
        }
    }


# ─────────────────────────────────────────────
# VALUATION SUMMARY
# ─────────────────────────────────────────────

def build_valuation_summary(dcf: dict, lbo: dict, comps: dict,
                              financials: dict, a: dict) -> dict:
    """
    Blended valuation range across all methodologies.
    Standard M&A practice: weight DCF 40%, Comps 40%, LBO 20%.
    """
    results = {}

    # DCF range (±15% around central case)
    dcf_ev = dcf.get("enterprise_value", 0)
    if dcf_ev:
        results["dcf"] = {
            "low":    round(dcf_ev * 0.85),
            "mid":    round(dcf_ev),
            "high":   round(dcf_ev * 1.15),
            "weight": 0.40,
        }

    # Comparables range
    if "blended_ev_range" in comps:
        results["comparables"] = {
            "low":    comps["blended_ev_range"]["low"],
            "mid":    comps["blended_ev_range"]["median"],
            "high":   comps["blended_ev_range"]["high"],
            "weight": 0.40,
        }

    # LBO floor (PE buyer sets the floor)
    lbo_ev = lbo.get("entry_ev", 0)
    if lbo_ev:
        results["lbo"] = {
            "low":    round(lbo_ev * 0.90),
            "mid":    round(lbo_ev),
            "high":   round(lbo_ev * 1.10),
            "weight": 0.20,
        }

    # Weighted blended range
    if results:
        blended_low  = sum(v["low"]  * v["weight"] for v in results.values())
        blended_mid  = sum(v["mid"]  * v["weight"] for v in results.values())
        blended_high = sum(v["high"] * v["weight"] for v in results.values())
    else:
        ebitda = financials.get("ebitda") or 0
        blended_low  = ebitda * 5.5
        blended_mid  = ebitda * 7.0
        blended_high = ebitda * 8.5

    return {
        "by_methodology": results,
        "blended": {
            "low":  round(blended_low),
            "mid":  round(blended_mid),
            "high": round(blended_high),
        },
        "methodology_weights": {
            "dcf":         "40%",
            "comparables": "40%",
            "lbo_floor":   "20%",
        }
    }


# ─────────────────────────────────────────────
# EXCEL EXPORT DATA
# ─────────────────────────────────────────────

def build_excel_data(financials, a, dcf, lbo, comps, sensitivity) -> dict:
    """
    Structured data for Excel export.
    Loveable frontend can use this to trigger an Excel download.
    """
    return {
        "income_statement": {
            "headers": ["Metric", "Prior Year", "Current Year", "Y1", "Y2", "Y3", "Y4", "Y5"],
            "rows": [
                ["Revenue",
                    financials.get("revenue_prior"),
                    financials.get("revenue"),
                    *dcf.get("projected_revenues", [None]*5)],
                ["EBITDA",
                    financials.get("ebitda_prior"),
                    financials.get("ebitda"),
                    *dcf.get("projected_ebitdas", [None]*5)],
                ["Net Profit",
                    None,
                    financials.get("net_profit"),
                    *[None]*5],
            ]
        },
        "dcf_summary": {
            "enterprise_value": dcf.get("enterprise_value"),
            "equity_value":     dcf.get("equity_value"),
            "pv_fcffs":         dcf.get("projected_fcffs"),
            "terminal_value":   dcf.get("terminal_value"),
        },
        "lbo_summary": {
            "irr":   lbo.get("irr"),
            "moic":  lbo.get("moic"),
            "entry": lbo.get("entry_ev"),
            "exit":  lbo.get("exit_ev"),
        },
        "sensitivity_wacc_tg": sensitivity.get("wacc_vs_terminal_growth", {}).get("table", []),
        "sensitivity_margin_growth": sensitivity.get("margin_vs_growth", {}).get("table", []),
    }
