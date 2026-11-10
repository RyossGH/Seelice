import { describe, expect, it } from "vitest";
import { healthzResponseSchema } from "../src/index.ts";

describe("healthzResponseSchema", () => {
  it("accepts the ok payload", () => {
    expect(healthzResponseSchema.parse({ status: "ok" })).toEqual({ status: "ok" });
  });

  it("rejects anything else", () => {
    expect(healthzResponseSchema.safeParse({ status: "down" }).success).toBe(false);
    expect(healthzResponseSchema.safeParse({}).success).toBe(false);
  });
});
