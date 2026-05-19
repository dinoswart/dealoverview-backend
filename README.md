# DealOverview Backend API

Three endpoints that power the core AI features of DealOverview.

## Endpoints

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/parse-afs` | POST | Upload PDF or Excel AFS → returns structured financial JSON |
| `/generate-cim` | POST | Takes financials → returns full CIM with all sections |
| `/financial-models` | POST | Runs DCF, LBO, Comparables, Sensitivity → returns all models |
| `/` | GET | Health check |

---

## Deploy to Railway (free, 5 minutes)

1. Create a GitHub account if you don't have one
2. Create a new repo called `dealoverview-backend`
3. Upload all files in this folder to that repo
4. Go to railway.app → New Project → Deploy from GitHub → select your repo
5. Railway detects Python automatically and deploys
6. Go to Settings → Variables → add: `ANTHROPIC_API_KEY = your_key_here`
7. Go to Settings → Networking → Generate Domain
8. Your API is live at: `https://dealoverview-backend.railway.app`

---

## Run Locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=your_key_here
uvicorn main:app --reload --port 8000
```

Test it:
```bash
curl http://localhost:8000/
```

---

## Connect to Loveable

Once deployed, paste this into the Loveable chat:

> "The backend API is live at https://YOUR-RAILWAY-URL.railway.app
>
> Wire up the following:
> 1. On the CIM tab, when a file is uploaded, POST it as multipart/form-data to /parse-afs. Store the returned JSON in the deal's financial_data field in Supabase.
> 2. Add a 'Generate CIM' button that POSTs to /generate-cim with body: { financials: [stored financial_data], deal_context: { sector, asking_price, advisor_name } }. Display the returned sections in the CIM tab editor.
> 3. On the Financial Models tab, add a 'Run Models' button that POSTs to /financial-models with body: { financials: [stored financial_data], assumptions: {} }. Display DCF enterprise value, LBO IRR/MOIC, comparables range, and sensitivity tables in the respective panels."

---

## API Examples

### Parse AFS
```bash
curl -X POST https://your-api.railway.app/parse-afs \
  -F "file=@financials.pdf"
```

### Generate CIM
```bash
curl -X POST https://your-api.railway.app/generate-cim \
  -H "Content-Type: application/json" \
  -d '{
    "financials": {
      "company_name": "Hartwell Engineering",
      "revenue": 48200000,
      "ebitda": 9640000,
      "ebitda_margin": 0.20,
      "net_profit": 6200000,
      "total_assets": 32000000,
      "total_debt": 8000000,
      "cash": 3200000
    },
    "deal_context": {
      "sector": "Industrial Manufacturing",
      "asking_price": 72000000,
      "advisor_name": "Smith & Partners",
      "deal_rationale": "Founder retirement"
    }
  }'
```

### Run Financial Models
```bash
curl -X POST https://your-api.railway.app/financial-models \
  -H "Content-Type: application/json" \
  -d '{
    "financials": {
      "revenue": 48200000,
      "ebitda": 9640000,
      "net_profit": 6200000,
      "net_debt": 4800000,
      "operating_cash_flow": 8100000
    },
    "assumptions": {
      "wacc": 0.12,
      "terminal_growth": 0.025,
      "entry_multiple": 7.0,
      "exit_multiple": 8.5
    }
  }'
```
