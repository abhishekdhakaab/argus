const fastApiUrl = process.env.FASTAPI_URL ?? 'http://127.0.0.1:8080';

/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${fastApiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
