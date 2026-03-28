import request from "supertest";
import { describe, expect, test } from "vitest";

import { createApiApp } from "../apps/api/src/app";

describe("api app", () => {
  test("returns health status for deployment checks", async () => {
    const response = await request(createApiApp()).get("/api/health");

    expect(response.status).toBe(200);
    expect(response.body).toEqual({ status: "ok", service: "raincoat-api" });
  });

  test("lists report scenarios from manifests", async () => {
    const response = await request(createApiApp()).get("/api/reports/scenarios");

    expect(response.status).toBe(200);
    expect(response.body.items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: "trading-weekly",
          owner: "engineering",
          pathPrefix: "/reports"
        }),
        expect.objectContaining({
          id: "circle-daily",
          owner: "engineering",
          pathPrefix: "/reports"
        })
      ])
    );
  });
});
