import { describe, expect, it } from "vitest";
import { getRuntimeConfig } from "@/lib/runtime";

describe("getRuntimeConfig", () => {
  it("uses the local FastAPI URL by default", () => {
    const original = process.env.NEXT_PUBLIC_API_BASE_URL;
    delete process.env.NEXT_PUBLIC_API_BASE_URL;

    expect(getRuntimeConfig()).toEqual({
      apiBaseUrl: "http://localhost:8000"
    });

    process.env.NEXT_PUBLIC_API_BASE_URL = original;
  });

  it("allows overriding the API URL through env", () => {
    const original = process.env.NEXT_PUBLIC_API_BASE_URL;
    process.env.NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:9000";

    expect(getRuntimeConfig().apiBaseUrl).toBe("http://127.0.0.1:9000");

    process.env.NEXT_PUBLIC_API_BASE_URL = original;
  });
});
