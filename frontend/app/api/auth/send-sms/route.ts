import { NextResponse } from 'next/server';
import { stytchClient } from '../../../lib.stytch';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const { phone } = await req.json() as { phone?: string };
  if (!phone) return NextResponse.json({ ok: false, error: 'Missing phone' }, { status: 400 });

  const stytch = stytchClient();
  const resp = await stytch.otps.sms.loginOrCreate({ phone_number: phone }); // returns phone_id

  const res = NextResponse.json({ ok: true });
  res.cookies.set('stytch_phone_id', resp.phone_id, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: 15 * 60, // 15 minutes
  });
  return res;
}