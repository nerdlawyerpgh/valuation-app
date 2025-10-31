'use client';
import React, { useEffect, useState } from 'react';

export default function IntakePage() {
  const [userEmail, setUserEmail] = useState<string|null>(null);
  const [userPhone, setUserPhone] = useState<string|null>(null);  // ADD THIS

  useEffect(() => {
    fetch('/api/auth/me')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        setUserEmail(d?.email ?? null);
        setUserPhone(d?.phone ?? null);  // ADD THIS
      })
      .catch(() => {});
  }, []);

  const [ebitda, setEbitda] = useState('2500000');
  const [debtPct, setDebtPct] = useState<number>(60);
  const [industry, setIndustry] = useState('All-Industry');
  const [location, setLocation] = useState('');

  const [ev, setEv] = useState<number | null>(null);
  const [expected, setExpected] = useState<number | null>(null);
  const [expectedLow, setExpectedLow] = useState<number | null>(null);
  const [expectedHigh, setExpectedHigh] = useState<number | null>(null);
  const [unlocked, setUnlocked] = useState(false);

  // TEV statistical range (or envelope fallback)
  const [tevLow, setTevLow] = useState<number | null>(null);
  const [tevHigh, setTevHigh] = useState<number | null>(null);

  const STEP_EBITDA = 50_000;

  const toNumber = (s: string) => {
    const n = Number(String(s).replace(/[^0-9.-]/g, ''));
    return Number.isFinite(n) ? n : 0;
  };
  const inc = (val: string, step: number) => String(Math.max(0, toNumber(val) + step));
  const dec = (val: string, step: number) => String(Math.max(0, toNumber(val) - step));

  const INDUSTRIES = [
    'Business Services', 'Consumer Products', 'Distribution & Logistics',
    'Healthcare Services', 'Manufacturing', 'Media & Telecom', 'Retail', 'Technology / IT Services',
  ] as const;

  const US_STATES = [
  'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut',
  'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa',
  'Kansas', 'Kentucky', 'Louisiana', 'Maine', 'Maryland', 'Massachusetts', 'Michigan',
  'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire',
  'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio',
  'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
  'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington', 'West Virginia',
  'Wisconsin', 'Wyoming'
] as const;

  // Use backend-provided min/max if present; otherwise derive a ±20% band
  const expectedMin = expectedLow ?? (expected !== null ? Math.round(expected * 0.8) : null);
  const expectedMax = expectedHigh ?? (expected !== null ? Math.round(expected * 1.2) : null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const api = process.env.REACT_APP_API_BASE || 'http://localhost:8000';
    const res = await fetch(`${api}/compute-valuation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ebitda: parseFloat(ebitda),
        debt_pct: debtPct / 100,
        industry,
      }),
    });
    if (!res.ok) {
      alert('Failed to compute valuation');
      return;
    }
    const data = await res.json();

    setEv(data.enterprise_value ?? null);
    setExpected(data.expected_valuation ?? null);
    setExpectedLow(data.expected_low ?? null);
    setExpectedHigh(data.expected_high ?? null);
    setUnlocked(Boolean(data.unlocked));

    // Prefer explicit TEV CI if provided; else use expected_low/high
    const lo = (data.tev_low ?? data.expected_low) ?? null;
    const hi = (data.tev_high ?? data.expected_high) ?? null;
    setTevLow(typeof lo === 'number' ? lo : (lo != null ? Number(lo) : null));
    setTevHigh(typeof hi === 'number' ? hi : (hi != null ? Number(hi) : null));
  
       // helper to coerce numbers safely
    const num = (x: any) => {
      const n = Number(x);
      return Number.isFinite(n) ? n : null;
    };

    // Log the valuation run (inputs + outputs you just received)
    const payloadForLog = {
      // include email if you have it in context; otherwise leave null
      email: (typeof userEmail === 'string' && /\S+@\S+\.\S+/.test(userEmail)) ? userEmail : null,
      phone: userPhone, 
      location: location || null, 

      ebitda: num(ebitda),
      debt_pct: num(debtPct / 100),
      industry: industry || null,

      enterprise_value: num(data.enterprise_value),
      expected_valuation: num(data.expected_valuation),
      expected_low: num(data.tev_low ?? data.expected_low),
      expected_high: num(data.tev_high ?? data.expected_high),

      ev_tev_current: num(data.enterprise_value),
      ev_tev_avg: num(data.bars?.find((b:any)=>String(b.name).startsWith('TEV 5-yr Avg'))?.value),
      ev_ind_current: num(data.bars?.find((b:any)=>b.name==='Industry Current')?.value),
      ev_ind_avg: num(data.bars?.find((b:any)=>b.name==='Industry 5-yr Avg')?.value),
      ev_pe_stack: num(data.bars?.find((b:any)=>b.name==='PE Stack')?.value),

      band_label: (data.notes?.match(/band=([^;]+)/)?.[1]) ?? null,
      notes: data.notes ?? null,
    };

    fetch(`${api}/log/valuation`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payloadForLog),
    }).catch(() => {});
  }

  return (
    <div className="card">
      <h2 className="text-xl font-semibold mb-4 text-gray-900">Hi there!</h2>

      <div className="space-y-3 text-sm md:text-base text-gray-700">
        <p><strong>Total Enterprise Value (TEV)</strong> reflects the value of a company’s core operations—its equity plus net debt.</p>
        <p className="font-mono">TEV = Market Capitalization + Total Debt − Cash &amp; Cash Equivalents</p>
        <p className="text-xs text-gray-500">Note: Some definitions also include preferred equity and minority interest.</p>
        <p>Don’t have all of those figures handy? We can estimate TEV from your <strong>TTM EBITDA</strong> together with market leverage (percent debt financing) unsing industry specific debt to EBITDA ratios.</p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="grid gap-6 items-start grid-cols-1 md:grid-cols-[4rem_minmax(22rem,42rem)_4rem]"
      >
        {/* middle column */}
        <div className="mt-5 md:col-start-2 space-y-6">
          {/* EBITDA */}
          <div>
            <div className="flex items-center gap-2">
              <label htmlFor="ebitda" className="text-sm font-medium text-gray-700">TTM EBITDA</label>
              <details className="relative">
                <summary className="list-none cursor-pointer text-xs text-gray-600 w-5 h-5 rounded-full border flex items-center justify-center" aria-label="What is TTM EBITDA?">i</summary>
                <div className="absolute z-10 mt-2 w-80 p-3 text-xs bg-white border rounded-lg text-gray-500 shadow [&::-webkit-details-marker]:hidden">
                  TTM EBITDA = trailing twelve months earnings before interest, taxes, depreciation, and amortization.
                </div>
              </details>
            </div>

            <div className="mt-1 flex items-center gap-2 text-gray-500">
              <input
                id="ebitda"
                type="number"
                inputMode="numeric"
                step={STEP_EBITDA}
                min={0}
                className="w-full border rounded-lg p-2 font-mono"
                placeholder="e.g., 2500000"
                value={ebitda}
                onChange={(e) => setEbitda(e.target.value)}
              />
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Enter whole dollars. Example: <span className="font-mono">2500000</span> ($2.5M).
            </p>
          </div>

          {/* Percent Debt Financing (slider) */}
          <div>
            <label htmlFor="debtPct" className="block text-sm font-medium text-gray-700 mb-2">
              Percent Debt Financing
            </label>
            <div className="flex items-center text-gray-500 gap-3">
              <div className="flex-1">
                <input
                  id="debtPct"
                  type="range"
                  min={0}
                  max={100}
                  step={1}
                  value={debtPct}
                  onChange={(e) => setDebtPct(parseInt(e.target.value, 10))}
                  className="w-full accent-emerald-600"
                  aria-describedby="debtPctHelp"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>0%</span><span>100%</span>
                </div>
              </div>
              <div className="w-20">
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  value={debtPct}
                  onChange={(e) => {
                    const n = parseFloat(e.target.value);
                    setDebtPct(Number.isFinite(n) ? Math.min(100, Math.max(0, n)) : 0);
                  }}
                  className="w-full border rounded-lg p-2 text-right font-mono"
                />
              </div>
            </div>
            <p id="debtPctHelp" className="mt-1 text-xs text-gray-500">
              Share of the purchase price financed with debt.
            </p>
          </div>

          {/* Industry */}
          <div>
            <label htmlFor="industry" className="block text-sm font-medium text-gray-700 mb-1">Industry</label>
            <select
              id="industry"
              className="w-full text-gray-500 border rounded-lg p-2"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
            >
              <option value="All-Industry">All-Industry</option>
              {INDUSTRIES.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
            <p className="mt-2 text-xs text-gray-500">Pick the closest category.</p>
          </div>
          {/* Location */}
          <div>
            <label htmlFor="location" className="block text-sm font-medium text-gray-700 mb-1">
              Company Location
            </label>
            <select
              id="location"
              className="w-full text-gray-500 border rounded-lg p-2"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            >
              <option value="">Select state...</option>
              {US_STATES.map((state) => (
                <option key={state} value={state}>{state}</option>
              ))}
            </select>
            <p className="mt-2 text-xs text-gray-500">Where is your company based?</p>
          </div>

          {/* Compute */}
          <div className="flex justify-center">
            <button className="btn btn-primary px-8" type="submit">Compute</button>
          </div>
        </div>
      </form>

      {ev !== null && (
        <div
          className="grid gap-6 items-start grid-cols-1 md:grid-cols-[4rem_minmax(22rem,42rem)_4rem]"
          aria-live="polite"
        >
          {/* TEV range (unblurred) */}
          {tevLow !== null && tevHigh !== null && (
            <div className="md:col-start-2 text-gray-700">
              <div className="mt-5 space-y-0 text-gray-700 text-lg">Total Enterprise Value (TEV):</div>
              <div className="flex justify-center mt-1 text-xl font-mono">
                ${tevLow.toLocaleString()} <span className="mx-1">-</span> ${tevHigh.toLocaleString()}
              </div>
              <p className="mt-1 text-xs text-gray-500 text-left max-w-prose">
                TEV represents the total value of your company's operations. This range is based on 
                industry-specific multiples from recent private equity transactions. To determine your 
                expected sale price (equity value), we'll subtract net debt from TEV during our 
                detailed financial review.
              </p>
            </div>
          )}

          {/* Expected Sale Price (blurred range until unlocked) */}
          <div className="mt-2 md:col-start-2 text-gray-700">
            <div className="text-lg">Expected Sale Price:</div>

            {expectedMin !== null && expectedMax !== null ? (
              <>
                <div className="mt-1 text-xl font-mono text-center">
                  <span>$</span>
                  <span className={!unlocked ? 'blur-number inline-block' : ''}>
                    {expectedMin.toLocaleString()}
                  </span>
                  <span className="mx-1">-</span>
                  <span>$</span>
                  <span className={!unlocked ? 'blur-number inline-block' : ''}>
                    {expectedMax.toLocaleString()}
                  </span>
                </div>

                <p className="mt-2 text-xs text-gray-500 text-left max-w-prose">
                  The valuations presented in this app are derived from estimated TEV and public/benchmark multiples based on private equity transactions occuring in 2025 and over the last 5 years in your industry. To recieve these estimates and discuss your the value company with an investment banker, please click the button below.    
                </p>
              </>
            ) : (
              <div className="mt-1 text-2xl font-mono text-center">—</div>
            )}

            {!unlocked && (
              <div className="flex justify-center">
                <a
                  className="btn btn-primary mt-6 inline-block"
                  href={process.env.NEXT_PUBLIC_CAL_URL}
                  target="_blank"
                  rel="noreferrer"
                >
                  Book a call to unlock
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
