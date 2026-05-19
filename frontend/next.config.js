/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Backend URL is consumed by the /api/proxy edge route, not exposed to the client.
  // See docs/deploy.md after U11 for production wiring.
  env: {
    BACKEND_URL: process.env.BACKEND_URL || 'http://localhost:8000',
  },
  experimental: {
    typedRoutes: true,
  },
};

module.exports = nextConfig;
