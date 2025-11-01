'use client';
import React, { useState } from 'react';

function toE164(input: string): string | null {
  // strip everything except + and digits
  let s = input.replace(/[^\d+]/g, '');
  if (s.startsWith('+')) return s.length >= 8 ? s : null; // minimal sanity check
  const digits = s.replace(/\D/g, '');
  if (digits.length === 10) return `+1${digits}`;           // US default
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`;
  return null;
}

export default function MfaPage() {
  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [sent, setSent] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function sendSms(e: React.FormEvent) {
    e.preventDefault();
    setErr(null); setMsg('Sending...');
    try {
      const e164 = toE164(phone);
      if (!e164) { setErr('Please enter a valid phone like +14125551234'); setMsg(null); return; }

      const r = await fetch('/api/auth/send-sms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: e164 }),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || 'Failed to send code');
      setSent(true);
      setMsg('Code sent. Check your phone.');
    } catch (e: any) {
      setErr(e.message || 'Failed to send');
      setMsg(null);
    }
  }

  async function verifySms(e: React.FormEvent) {
    e.preventDefault();
    setErr(null); setMsg('Verifying...');
    try {
      const e164 = toE164(phone);
      if (!e164) { setErr('Invalid phone format'); setMsg(null); return; }

      const r = await fetch('/api/auth/verify-sms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: e164, code }),
      });
      const data = await r.json();
      if (!r.ok || !data.ok) throw new Error(data.error || 'Invalid code');

      // Successful MFA -> go to intake
      window.location.href = '/intake';
    } catch (e: any) {
      setErr(e.message || 'Verification failed');
      setMsg(null);
    }
    await fetch(process.env.NEXT_PUBLIC_API_BASE + '/log/access', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, phone }),
    });
    // app/mfa/page.tsx (after successful OTP verification)
    const api = process.env.NEXT_PUBLIC_API_BASE || 'https://valuation.nerdlawyer.ai/compute-valuation';
    fetch(`${api}/log/access`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, phone }),
    }).catch(() => {});
  }

  return (
    <div className="card">
      <h2 className="text-xl font-semibold mb-4">Verify your phone</h2>

      {!sent ? (
        <form onSubmit={sendSms} className="space-y-3">
          <input
            type="tel"
            className="w-full border rounded-lg p-2"
            placeholder="+1 555 555 5555"
            value={phone}
            onChange={(e)=>setPhone(e.target.value)}
            autoComplete="tel"
          />
          <button className="btn btn-primary" type="submit">Send code</button>
          {msg && <p className="text-gray-600">{msg}</p>}
          {err && <p className="text-red-600">{err}</p>}
        </form>
      ) : (
        <form onSubmit={verifySms} className="text-gray-700 space-y-3">
          <input
            type="tel"
            className="w-full border rounded-lg p-2"
            placeholder="+1 412 555 1234"
            value={phone}
            onChange={(e)=>setPhone(e.target.value)}
            autoComplete="tel"
          />
          <input
            type="text"
            className="w-full border rounded-lg p-2"
            placeholder="6-digit code"
            value={code}
            onChange={(e)=>setCode(e.target.value)}
            inputMode="numeric"
            autoComplete="one-time-code"
          />
          <button className="btn btn-primary" type="submit">Verify</button>
          {msg && <p className="text-gray-600">{msg}</p>}
          {err && <p className="text-red-600">{err}</p>}
        </form>
      )}
    </div>
  );
}
