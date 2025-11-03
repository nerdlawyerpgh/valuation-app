// app/lib.stytch.ts
import { Client, envs } from 'stytch';

export function stytchClient() {
  const env = (process.env.STYTCH_ENV || 'test').toLowerCase() === 'live' ? envs.live : envs.test;
  const project_id = process.env.STYTCH_PROJECT_ID!;
  const secret = process.env.STYTCH_SECRET!;
  return new Client({ project_id, secret, env });
}
