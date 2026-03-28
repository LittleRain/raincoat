import path from "node:path";

import type { ToolDefinition } from "@raincoat/shared-types";

export const platformName = "Raincoat";

export const toolPathPrefix = {
  reports: "/reports"
} as const;

export const defaultToolDefinitions: ToolDefinition[] = [
  {
    id: "reports",
    name: "周报系统",
    pathPrefix: toolPathPrefix.reports,
    enabled: true
  }
];

export const platformPorts = {
  web: 3100,
  api: 3200
} as const;

export const getPublicRoutes = () => ({
  home: "/",
  reportsHome: toolPathPrefix.reports,
  apiPrefix: "/api",
  artifactsPrefix: "/artifacts"
});

export const buildRunPaths = (runsRoot: string, runId: string) => {
  const root = path.join(runsRoot, runId);

  return {
    root,
    inputDir: path.join(root, "input"),
    outputDir: path.join(root, "output"),
    logsDir: path.join(root, "logs"),
    statusFile: path.join(root, "status.json"),
    metadataFile: path.join(root, "metadata.json")
  };
};
