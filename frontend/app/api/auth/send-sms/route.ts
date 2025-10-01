import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { stytchClient } from '@/lib/stytch';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const { phone } = await req.json() as { phone?: string };
  if (!phone) return NextResponse.json({ ok: false, error: 'Missing phone' }, { status: 400 });

  // Get the existing session from the magic link auth
  const sessionToken = cookies().get('stytch_session')?.value;

  const resp = await stytchClient.otps.sms.send({ 
    phone_number: phone,
    // Link to existing session if available
    ...(sessionToken && { session_token: sessionToken })
  });

  const res = NextResponse.json({ ok: true });
  res.cookies.set('stytch_phone_id', resp.phone_id, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: 15 * 60,
  });
  return res;
}