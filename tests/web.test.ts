import request from "supertest";
import { describe, expect, test } from "vitest";

import { createWebApp } from "../apps/web/src/app";

describe("web app", () => {
  test("serves a workspace home page with tool entry links", async () => {
    const response = await request(createWebApp()).get("/");

    expect(response.status).toBe(200);
    expect(response.text).toContain("Raincoat");
    expect(response.text).toContain('href="/reports"');
    expect(response.text).toContain("周报系统");
  });

  test("serves the reports landing page on the reports prefix", async () => {
    const response = await request(createWebApp()).get("/reports");

    expect(response.status).toBe(200);
    expect(response.text).toContain("报告场景");
    expect(response.text).toContain("trading-weekly");
    expect(response.text).toContain("circle-daily");
  });
});
