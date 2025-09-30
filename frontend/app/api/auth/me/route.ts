import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { stytchClient } from '@/lib/stytch';

type EmailItem = { email?: string; primary?: boolean };
type PhoneItem = { phone_number?: string; primary?: boolean };

function pickPrimaryEmail(res: unknown): string | null {
  if (res && typeof res === 'object' && 'user' in res) {
    const user: any = (res as any).user;
    const emails: EmailItem[] | undefined = user?.emails;
    if (Array.isArray(emails) && emails.length) {
      return emails.find(e => e?.primary)?.email ?? emails[0]?.email ?? null;
    }
  }
  return null;
}

function pickPrimaryPhone(res: unknown): string | null {
  if (res && typeof res === 'object' && 'user' in res) {
    const user: any = (res as any).user;
    const phones: PhoneItem[] | undefined = user?.phone_numbers;
    if (Array.isArray(phones) && phones.length) {
      return phones.find(p => p?.primary)?.phone_number ?? phones[0]?.phone_number ?? null;
    }
  }
  return null;
}

export async function GET() {
  try {
    const sessionToken = cookies().get('stytch_session')?.value;
    if (!sessionToken) return NextResponse.json({ email: null, phone: null });

    const { session } = await stytchClient.sessions.authenticate({
      session_token: sessionToken,
    });

    const userRes = await stytchClient.users.get({ user_id: session.user_id });

    const primaryEmail = pickPrimaryEmail(userRes);
    const primaryPhone = pickPrimaryPhone(userRes);

    return NextResponse.json({ email: primaryEmail, phone: primaryPhone });
  } catch {
    return NextResponse.json({ email: null, phone: null });
  }
}