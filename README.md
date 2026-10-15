# ai-sales-crm-demo (code only)

Application code for the portable CRM demo. `Start.vbs` (in the team package)
downloads this repository on every launch and copies these folders over the
local install, so updates here reach every teammate automatically.

What is in here:
- `dashboard/` — Python dashboard server (token auth) + vanilla fallback page
- `frontend/dist/` — built React UI
- `generator/` — rule-based audit / cold email / landing page engine
- `lead-finder/dist/` — built scraper CLI (Puppeteer stealth)
- `integrate.py`, `run_pipeline.py` — pipeline glue (portable node/chrome aware)

What is NOT here (by design):
- Lead data (`unified_leads.json`, `generated_landing_pages/`) — stays local per PC
- Runtimes (`python/`, `node/`, `chrome/`, `cloudflared.exe`) — shipped in the initial zip
- `node_modules/` — shipped in the initial zip (only changes on dependency updates)

No API keys are required: audits are rule-based, scraping uses the bundled Chrome.
