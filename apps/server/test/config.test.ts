import { describe, expect, it } from "vitest";
import { loadConfig } from "../src/config.ts";

describe("loadConfig", () => {
  it("listens on localhost only by default", () => {
    expect(loadConfig({})).toEqual({ NODE_ENV: "development", HOST: "127.0.0.1", PORT: 8080 });
  });

  it("reads the port from the environment", () => {
    expect(loadConfig({ PORT: "9000" }).PORT).toBe(9000);
  });

  it("rejects an invalid port", () => {
    expect(() => loadConfig({ PORT: "99999" })).toThrow(/Invalid configuration/);
    expect(() => loadConfig({ PORT: "abc" })).toThrow(/Invalid configuration/);
  });
});
