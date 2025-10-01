import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { stytchClient } from '@/lib/stytch';

type EmailItem = { email?: string; primary?: boolean };
type PhoneItem = { phone_number?: string; primary?: boolean };

function pickPrimaryEmail(res: unknown): string | null {
  if (res && typeof res === 'object') {
    // Check if emails array is at the root level
    const emails: EmailItem[] | undefined = (res as any).emails;
    if (Array.isArray(emails) && emails.length) {
      return emails.find(e => e?.email)?.email ?? emails[0]?.email ?? null;
    }
  }
  return null;
}

function pickPrimaryPhone(res: unknown): string | null {
  if (res && typeof res === 'object') {
    // Check if phone_numbers array is at the root level
    const phones: PhoneItem[] | undefined = (res as any).phone_numbers;
    if (Array.isArray(phones) && phones.length) {
      return phones.find(p => p?.phone_number)?.phone_number ?? phones[0]?.phone_number ?? null;
    }
  }
  return null;
}

export async function GET() {
  try {
    const sessionToken = cookies().get('stytch_session')?.value;
    console.log('Session token exists:', !!sessionToken);
    
    if (!sessionToken) return NextResponse.json({ email: null, phone: null });

    const { session } = await stytchClient.sessions.authenticate({
      session_token: sessionToken,
    });

    console.log('Session user_id:', session.user_id);

    const userRes = await stytchClient.users.get({ user_id: session.user_id });
    
    console.log('Full user object:', JSON.stringify(userRes, null, 2));

    const primaryEmail = pickPrimaryEmail(userRes);
    const primaryPhone = pickPrimaryPhone(userRes);

    console.log('Extracted email:', primaryEmail);
    console.log('Extracted phone:', primaryPhone);

    return NextResponse.json({ email: primaryEmail, phone: primaryPhone });
  } catch (error) {
    console.error('Error in /api/auth/me:', error);
    return NextResponse.json({ email: null, phone: null });
  }
}