import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { stytchClient } from '../../../lib.stytch';
import { signMfaCookie } from '../../../lib.mfa';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const { code } = await req.json() as { code?: string };
  if (!code) return NextResponse.json({ ok:false, error:'Missing code' }, { status:400 });

  const method_id = cookies().get('stytch_phone_id')?.value;
  if (!method_id) return NextResponse.json({ ok:false, error:'Session expired, resend code.' }, { status:400 });

  const stytch = stytchClient();
  await stytch.otps.authenticate({ method_id, code, session_duration_minutes: 60 }); // <- correct call

  const token = await signMfaCookie('user', process.env.MFA_SIGNING_SECRET || 'change-me-please');
  const res = NextResponse.json({ ok: true });
  res.cookies.set('mfa_token', token, {
    httpOnly: true, sameSite: 'lax', secure: process.env.NODE_ENV==='production', path: '/', maxAge: 3600,
  });
  // clear the temporary phone_id cookie
  res.cookies.set('stytch_phone_id', '', { path: '/', maxAge: 0 });
  return res;
}
