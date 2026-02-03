/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // API calls go to Railway backend
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
