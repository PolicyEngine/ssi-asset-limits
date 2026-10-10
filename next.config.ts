import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

const BASE_PATH = "/us/ssi-asset-limits";
const ZONE_PREFIX = "/_zones/ssi-asset-limits";

export default function nextConfig(phase: string): NextConfig {
  const isDev = phase === PHASE_DEVELOPMENT_SERVER;

  return {
    output: "export",
    basePath: BASE_PATH,
    assetPrefix: isDev ? undefined : ZONE_PREFIX,
    trailingSlash: true,
    env: {
      NEXT_PUBLIC_BASE_PATH: BASE_PATH,
    },
    images: {
      unoptimized: true,
    },
    turbopack: {
      root: process.cwd(),
    },
  };
}
