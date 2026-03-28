import { describe, expect, test } from "vitest";

import { listScenarioDefinitions } from "../packages/task-sdk/src";

describe("task sdk", () => {
  test("discovers report scenarios from tool manifests", async () => {
    const scenarios = await listScenarioDefinitions(
      new URL("../tools/reports/manifests", import.meta.url)
    );

    expect(scenarios.map((item) => item.id)).toEqual([
      "circle-daily",
      "trading-weekly"
    ]);
  });
});
