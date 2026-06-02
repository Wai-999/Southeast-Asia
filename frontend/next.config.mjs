/** @type {import('next').NextConfig} */
const rawApiUpstream =
  process.env.API_UPSTREAM_URL ??
  process.env.API_UPSTREAM_HOSTPORT ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

const apiUpstream = /^https?:\/\//.test(rawApiUpstream)
  ? rawApiUpstream
  : `http://${rawApiUpstream}`;

const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiUpstream}/:path*`,
      },
    ];
  },
};

export default nextConfig;
