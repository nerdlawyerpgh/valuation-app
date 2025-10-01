import { NextResponse } from 'next/server';
import { stytchClient } from '@/lib/stytch';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(req: Request) {
  const url = new URL(req.url);
  const token = url.searchParams.get('token');

  if (!token) {
    return NextResponse.redirect(new URL('/request-access?err=missing-token', url.origin));
  }

  try {
    const authResponse = await stytchClient.magicLinks.authenticate({
      token,
      session_duration_minutes: 60,
    });

    console.log('Magic link auth response:', authResponse);
    console.log('Session token:', authResponse.session_token);
    console.log('Session JWT:', authResponse.session_jwt);

    const sessionToken = authResponse.session_token || authResponse.session_jwt;
    
    if (!sessionToken) {
      console.error('No session token found in response!');
      return NextResponse.redirect(new URL('/request-access?err=no-session', url.origin));
    }

    const res = NextResponse.redirect(new URL('/mfa', url.origin));
    res.cookies.set('stytch_session', sessionToken, {
      httpOnly: true,
      sameSite: 'lax',
      secure: process.env.NODE_ENV === 'production',
      path: '/',
      maxAge: 3600,
    });
    
    console.log('Set stytch_session cookie');
    
    return res;
  } catch (e) {
    console.error('Magic link auth error:', e);
    return NextResponse.redirect(new URL('/request-access?err=auth-failed', url.origin));
  }
}