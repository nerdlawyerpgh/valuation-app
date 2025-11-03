import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { stytchClient } from '@/lib/stytch'; // adjust your import as needed

export async function GET(req: Request) {
  try {
    const url = new URL(req.url);
    const token = url.searchParams.get('token'); // or 'token_type', if your flow uses it

    if (!token) {
      return NextResponse.redirect('/login?error=missing_token');
    }

    // ✅ 1. Authenticate and create a 30-minute session
    const { session_token, session_jwt } =
      await stytchClient.magicLinks.authenticate({
        token,
        session_duration_minutes: 30, // absolute 30-minute lifetime
      });

    // ✅ 2. Set cookie to expire in 30 minutes (1800 seconds)
    const maxAge = 30 * 60; // seconds
    cookies().set('stytch_session_jwt', session_jwt, {
      httpOnly: true,
      secure: true,
      sameSite: 'none',
      path: '/',
      domain: '.nerdlawyer.ai',
      maxAge, // expires in 30 min
    });

    // ✅ 3. Redirect user into the app
    return NextResponse.redirect(new URL('/intake', url.origin));
  } catch (err) {
    console.error('Stytch callback error:', err);
    return NextResponse.redirect('/login?error=auth_failed');
  }
}
