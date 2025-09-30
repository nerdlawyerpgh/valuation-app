# Valuation App Starter (Next.js + FastAPI + Stytch-ready)

This starter migrates your Streamlit prototype into a production-style architecture with:
- Next.js (App Router) frontend
- FastAPI backend for all valuation logic
- Space for Stytch passwordless + MFA (email magic link as primary, SMS/TOTP as second factor)
- Gated "Expected Valuation" until a meeting is booked (Cal.com webhook stub)

## What you need to do

1. **Move your valuation logic** from Streamlit into `backend/app/valuations.py::compute_valuation`.
   - Convert Streamlit-specific code into **pure functions**.
   - If your app uses CSVs (e.g., `multiples_tev.csv`, `multiples_industry.csv`), load them in that module and select multiples based on inputs like `industry` and `tev_band`.
   - Keep any charts client-side (Next.js) using a chart lib.

2. **Wire up Stytch** for auth & MFA:
   - Add server routes in Next.js using `@stytch/nextjs` or vanilla server SDK to send a **magic link** to the email captured on `/request-access`.
   - On callback, set your session cookie and **redirect to `/app/intake`**.
   - Implement **MFA step-up**: after magic link, send SMS/TOTP and set an `mfa_token` cookie (this starter uses a signed cookie via `MFA_SIGNING_SECRET`).

3. **Configure the Cal.com webhook** to call `POST /webhooks/cal` with the booking email.
   - Replace the signature verification with Cal.com’s official method and map the payload to `email`.
   - On prod, persist unlock state in your DB (set a `unlocked_at` timestamp on the valuation record).

## Local development

### Backend (FastAPI)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./run.sh
```
Runs on `http://localhost:8000`.

### Frontend (Next.js)
```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```
Runs on `http://localhost:3000`. Set `NEXT_PUBLIC_API_BASE` to your FastAPI URL.

## Route overview

- **POST /leads** — create a lead (email + phone). (You will likely call Stytch from a Next.js server action or API route here.)
- **POST /compute-valuation** — compute EV + expected valuation server-side.
  - If the user is **unlocked** (via `/webhooks/cal`), the frontend removes the blur.
- **POST /webhooks/cal** — Cal.com webhook stub (unlock by email).

## Security checklist

- Sessions: use Stytch sessions + **HttpOnly, Secure cookies**.
- MFA: require a second factor (SMS or TOTP). Do **not** use email as both factors.
- Backend-only compute: Never send raw formulas or CSVs to the client.
- Secrets: use a cloud secret manager and production env vars.
- Webhooks: verify signatures, store audit logs, rate-limit endpoints.
- Data: encrypt PII at rest, purge stale leads, and include disclaimers.

## Production deployment

- **Frontend**: Vercel (or your preferred Node host).
- **Backend**: Cloud Run / Fly.io / Railway (containerized FastAPI).
- **DB**: Postgres (Neon, Cloud SQL, Supabase). Add SQLAlchemy models when ready.
