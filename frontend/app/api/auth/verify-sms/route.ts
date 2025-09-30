import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { stytchClient } from '../../../../lib/stytch';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const { code } = await req.json() as { code?: string };
  if (!code) return NextResponse.json({ ok:false, error:'Missing code' }, { status:400 });

  const method_id = cookies().get('stytch_phone_id')?.value;
  if (!method_id) return NextResponse.json({ ok:false, error:'Session expired, resend code.' }, { status:400 });

  try {
    // Authenticate the OTP - this returns a session
    const authResponse = await stytchClient.otps.authenticate({ 
      method_id, 
      code, 
      session_duration_minutes: 60 
    });

    const res = NextResponse.json({ ok: true });
    
    // Save the Stytch session token as a cookie
    res.cookies.set('stytch_session', authResponse.session_token, {
      httpOnly: true,
      sameSite: 'lax',
      secure: process.env.NODE_ENV === 'production',
      path: '/',
      maxAge: 3600
    });

    // Clear the temporary phone_id cookie
    res.cookies.set('stytch_phone_id', '', { path: '/', maxAge: 0 });
    
    return res;
  } catch (error) {
    console.error('SMS verification error:', error);
    return NextResponse.json({ ok: false, error: 'Invalid code' }, { status: 400 });
  }
}