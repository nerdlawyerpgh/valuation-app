import { NextRequest, NextResponse } from 'next/server';
import { verifyMfaCookie } from './app/lib.mfa';

const PROTECTED_PREFIXES = ['/app', '/result'];

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (!PROTECTED_PREFIXES.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }
  const token = req.cookies.get('mfa_token')?.value;
  const secret = process.env.MFA_SIGNING_SECRET || 'change-me-please';
  if (!token) {
    return NextResponse.redirect(new URL('/request-access', req.url));
  }
  try {
    const payload = await verifyMfaCookie(token, secret);
    if (!payload) throw new Error('Invalid token');
    return NextResponse.next();
  } catch {
    return NextResponse.redirect(new URL('/request-access', req.url));
  }
}

export const config = { matcher: ['/app/:path*', '/result/:path*'] };
