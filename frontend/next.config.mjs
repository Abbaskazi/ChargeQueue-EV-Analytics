/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  async rewrites() {
    const backendUrl = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')

    return [{
      source: '/api/:path*',
      destination: `${backendUrl}/api/:path*`,
    }]
  },
  agentRules: false,
}

export default nextConfig
