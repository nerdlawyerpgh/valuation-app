import { SignJWT, jwtVerify } from 'jose';

const alg = 'HS256';

export async function signMfaCookie(email: string, secret: string) {
  return await new SignJWT({ email, mfa: true })
    .setProtectedHeader({ alg })
    .setIssuedAt()
    .setExpirationTime('1h')
    .sign(new TextEncoder().encode(secret));
}

export async function verifyMfaCookie(token: string, secret: string) {
  const { payload } = await jwtVerify(token, new TextEncoder().encode(secret));
  return payload?.mfa === true ? payload : null;
}

import { Client, envs } from 'stytch';

export function stytchClient() {
  const env = (process.env.STYTCH_ENV || 'test').toLowerCase() === 'live' ? envs.live : envs.test;
  const project_id = process.env.STYTCH_PROJECT_ID!;
  const secret = process.env.STYTCH_SECRET!;
  return new Client({ project_id, secret, env });
}