import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["*.replit.dev"],
  async rewrites() {
    return [
      {
        source: "/api/management/:path*",
        destination: "http://localhost:3001/api/:path*",
      },
      {
        source: "/api/ai/:path*",
        destination: "http://localhost:8001/api/:path*",
      },
    ];
  },
};

export default nextConfig;
