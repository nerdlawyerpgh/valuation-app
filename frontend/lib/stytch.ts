// lib/stytch.ts
import { Client, envs } from 'stytch';

export const stytchClient = new Client({
  project_id: process.env.STYTCH_PROJECT_ID!,
  secret: process.env.STYTCH_SECRET!,
  env: (process.env.STYTCH_ENV || 'test').toLowerCase() === 'live' ? envs.live : envs.test,
});
