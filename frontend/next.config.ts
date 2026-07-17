import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // "standalone" bundles a minimal server + only the node_modules actually
  // used, into .next/standalone — so the production Docker image ships that
  // instead of the whole repo + full node_modules. Much smaller image.
  output: "standalone",
};

export default nextConfig;
