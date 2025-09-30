import { NextResponse } from 'next/server';
import { stytchClient } from '../../../lib.stytch';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const url = new URL(req.url);
  const token = url.searchParams.get('token');           // Stytch adds this
  const tokenType = url.searchParams.get('stytch_token_type'); // usually "magic_links"

  if (!token) {
    return NextResponse.redirect(new URL('/request-access?err=missing-token', url.origin));
  }

  try {
    const stytch = stytchClient();
    const { session_jwt } = await stytch.magicLinks.authenticate({
      token,
      session_duration_minutes: 60,
    });

    const res = NextResponse.redirect(new URL('/mfa', url.origin));
    res.cookies.set('stytch_session', session_jwt, {
      httpOnly: true, sameSite: 'lax', secure: false, path: '/', maxAge: 3600,
    });
    return res;
  } catch (e) {
    return NextResponse.redirect(new URL('/request-access?err=auth-failed', url.origin));
  }
}
