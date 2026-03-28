import { describe, expect, test } from "vitest";

import {
  buildRunPaths,
  defaultToolDefinitions,
  getPublicRoutes
} from "../packages/shared-config/src";

describe("shared config", () => {
  test("defines same-domain route prefixes for current tools", () => {
    expect(defaultToolDefinitions).toEqual([
      {
        id: "reports",
        name: "周报系统",
        pathPrefix: "/reports",
        enabled: true
      }
    ]);
  });

  test("builds isolated run directories under a single run id", () => {
    expect(buildRunPaths("/srv/raincoat/data/runs", "run-123")).toEqual({
      root: "/srv/raincoat/data/runs/run-123",
      inputDir: "/srv/raincoat/data/runs/run-123/input",
      outputDir: "/srv/raincoat/data/runs/run-123/output",
      logsDir: "/srv/raincoat/data/runs/run-123/logs",
      statusFile: "/srv/raincoat/data/runs/run-123/status.json",
      metadataFile: "/srv/raincoat/data/runs/run-123/metadata.json"
    });
  });

  test("exposes platform routes for home, reports, api, and artifacts", () => {
    expect(getPublicRoutes()).toEqual({
      home: "/",
      reportsHome: "/reports",
      apiPrefix: "/api",
      artifactsPrefix: "/artifacts"
    });
  });
});
