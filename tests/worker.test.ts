import { describe, expect, test } from "vitest";

import { createWorkerSummary } from "../apps/worker/src";

describe("worker", () => {
  test("describes worker responsibilities for task-based tools", () => {
    expect(createWorkerSummary()).toEqual({
      service: "raincoat-worker",
      responsibilities: [
        "discover-manifests",
        "prepare-run-directories",
        "execute-tool-jobs",
        "collect-artifacts"
      ]
    });
  });
});
