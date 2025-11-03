/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: { serverActions: { allowedOrigins: ['https://valuation.nerdlawyer.ai'] } }
};
module.exports = nextConfig;
