'use client';
import React, { useState } from 'react';

export default function RequestAccessPage() {
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setStatus('Sending link…');

    try {
      const res = await fetch('/api/auth/send-link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, phone }), // <— only runs on click
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data?.error || 'Failed to send magic link');

      setSent(true);
      setStatus('Check your email for the secure link.');
    } catch (err: any) {
      setError(err.message || 'Something went wrong');
      setStatus(null);
    }
      const api = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

      // 1) log the access attempt
      await fetch('${api}/log/access', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          referrer: document.referrer || '',
          // lat/lon only if you asked for user consent
        }),
      });

      // 2) send magic link...
      await fetch('/api/auth/send-link', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });
    }
    
    return (
    <div className="card">
      {!sent ? (
        <form onSubmit={handleSubmit} className="space-y-3"><h2 className="text-xl font-semibold mb-4 text-gray-900">WELCOME!</h2>
        <div className="mt-1 text-base text-gray-600 space-y-3">
          <p>
            At Jordon Voytek Capital Partners, we help business owners achieve their goals: sell on your terms, free up time to spend with family and friends, or expand your empire through acquisition. 
          </p>
          <p>
            It all starts with a clear valuation.
          </p>
          <p>
            This tool estimates your company’s current value—its <strong>Enterprise Value</strong>—using
            industry data, proprietary private-equity multiples, and other market factors. Treat it as a
            starting point for a sale strategy tailored specifically to you.
          </p>
          <p className="text-gray-700 font-medium">
            Ready to learn what your company may be worth?
          </p>
        </div>
          <input
            className="mt-5 text-gray-600 w-full border rounded-lg p-2"
            placeholder="Email"
            value={email}
            onChange={(e)=>setEmail(e.target.value)}
          />
          <div className="col-span-2 flex justify-center">
            <button className="btn btn-primary" type="submit">Send Secure Link</button>
          </div>
          <div className="mt-1 text-sm text-gray-600 space-y-3">
            <p>
              We care about security as much as you do! We'll send a secure link to your business email with instructions for multi-factor authentication, before asking for sensitive information.   
            </p>
          </div>
          {status && <p className="text-gray-600">{status}</p>}
          {error && <p className="text-red-600">{error}</p>}
        </form>
       ) : (
        // ✅ styled, visible success state
        <div className="p-4">
          <h3 className="text-gray-700 text-lg font-semibold mb-2">Check your email</h3>
          <div className="mt-1 text-base text-gray-600 space-y-3">
            <p>
              We sent a secure sign-in link to <strong>{email || 'your email'}</strong>.
              Click the link to continue to MFA.
            </p>
            <p className="mt-2 text-sm text-gray-600">
              Didn’t get it? Check spam or <button className="underline" onClick={()=>setSent(false)}>try again</button>.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
