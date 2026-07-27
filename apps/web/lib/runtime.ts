export type RuntimeConfig = {
  apiBaseUrl: string;
};

const DEFAULT_API_BASE_URL = "http://localhost:8000";

export function getRuntimeConfig(): RuntimeConfig {
  return {
    apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL
  };
}
