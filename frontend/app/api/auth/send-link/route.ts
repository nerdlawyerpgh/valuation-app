// app/api/auth/send-link/route.ts
import { NextResponse } from 'next/server';
import { stytchClient } from '@/lib/stytch'; // export a ready instance from lib/stytch.ts

const isEmail = (s: unknown): s is string =>
  typeof s === 'string' && /\S+@\S+\.\S+/.test(s);

const BACKEND = process.env.NEXT_PUBLIC_API_BASE || 'https://valuation.nerdlawyer.ai/compute-valuation';
const BASE_URL =
  process.env.NEXT_PUBLIC_APP_URL ||
  process.env.APP_URL ||
  (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : 'https://valuation.nerdlawyer.ai');

const REDIRECT_PATH = '/api/auth/callback'; // where you handle the magic link token + MFA
const LOGIN_MAGIC_URL = `${BASE_URL}${REDIRECT_PATH}`;
const SIGNUP_MAGIC_URL = `${BASE_URL}${REDIRECT_PATH}`;

export async function POST(req: Request) {
  try {
    const { email, phone } = await req.json();

    if (!isEmail(email)) {
      return NextResponse.json({ ok: false, error: 'Invalid email' }, { status: 400 });
    }

    // Best-effort lead logging
    try {
      await fetch(`${BACKEND}/log/access`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          phone: typeof phone === 'string' && phone.trim() ? phone : null,
          referrer: null, // server route can't read document.referrer
        }),
      });
    } catch {
      /* ignore logging errors */
    }

    try {
      const ml = await stytchClient.magicLinks.email.loginOrCreate({
        email,
        login_magic_link_url: LOGIN_MAGIC_URL,
        signup_magic_link_url: SIGNUP_MAGIC_URL,
      });
      
      return NextResponse.json({
        ok: true,
        request_id: ml.request_id,
        login_magic_link_url: LOGIN_MAGIC_URL,
        signup_magic_link_url: SIGNUP_MAGIC_URL,
      });
    } catch (err: any) {
      console.error('Stytch error:', {
        message: err?.message,
        error_message: err?.error_message,
        status_code: err?.status_code,
        error_type: err?.error_type,
        full_error: err
      });
      
      const msg = err?.error_message || err?.message || 'Failed to send magic link';
      return NextResponse.json({ ok: false, error: msg }, { status: 500 });
    }

  } catch (err: any) {
    const msg =
      err?.error_message || err?.message || 'Failed to send magic link';
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
