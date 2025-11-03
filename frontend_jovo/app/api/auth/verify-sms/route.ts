import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { stytchClient } from '@/lib/stytch';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(req: Request) {
  const { code } = await req.json() as { code?: string };
  if (!code) return NextResponse.json({ ok:false, error:'Missing code' }, { status:400 });

  const method_id = cookies().get('stytch_phone_id')?.value;
  const sessionToken = cookies().get('stytch_session')?.value;
  
  if (!method_id) return NextResponse.json({ ok:false, error:'Session expired, resend code.' }, { status:400 });
  if (!sessionToken) return NextResponse.json({ ok:false, error:'No active session.' }, { status:400 });

  try {
    const authResponse = await stytchClient.otps.authenticate({ 
      method_id, 
      code,
      session_token: sessionToken,  // ADD THIS - pass the existing session
      session_duration_minutes: 60 
    });

    const newSessionToken = authResponse.session_token || authResponse.session_jwt;
    
    if (!newSessionToken) {
      console.error('No session token in OTP response!');
      return NextResponse.json({ ok: false, error: 'Session error' }, { status: 500 });
    }

    const res = NextResponse.json({ ok: true });
    
    // Update the session cookie with the new token
    res.cookies.set('stytch_session', newSessionToken, {
      httpOnly: true,
      sameSite: 'lax',
      secure: process.env.NODE_ENV === 'production',
      path: '/',
      maxAge: 3600
    });

    res.cookies.set('stytch_phone_id', '', { path: '/', maxAge: 0 });
   
    return res;
  } catch (error: any) {
    console.error('SMS verification error:', error);
    return NextResponse.json({ 
      ok: false, 
      error: error.error_message || 'Invalid code' 
    }, { status: 400 });
  }
}