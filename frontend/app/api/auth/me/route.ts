// app/api/auth/me/route.ts
import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { stytchClient } from '@/lib/stytch'; // instance export (your Option B)

type EmailItem = { email?: string; primary?: boolean };

// Narrow the shape we need from whatever the SDK returns
function pickPrimaryEmail(res: unknown): string | null {
  // Some SDK versions return { user: { emails: [...] } }
  if (res && typeof res === 'object' && 'user' in res) {
    const user: any = (res as any).user;
    const emails: EmailItem[] | undefined = user?.emails;
    if (Array.isArray(emails) && emails.length) {
      return emails.find(e => e?.primary)?.email ?? emails[0]?.email ?? null;
    }
  }
  return null;
}

export async function GET() {
  try {
    const sessionToken = cookies().get('stytch_session')?.value;
    if (!sessionToken) return NextResponse.json({ email: null });

    // 1) Authenticate the session and get the user_id
    const { session } = await stytchClient.sessions.authenticate({
      session_token: sessionToken,
    });

    // 2) Fetch the user; avoid strict typing issues with a tiny helper
    const userRes = await stytchClient.users.get({ user_id: session.user_id });

    const primaryEmail = pickPrimaryEmail(userRes);

    return NextResponse.json({ email: primaryEmail });
  } catch {
    return NextResponse.json({ email: null });
  }
}
