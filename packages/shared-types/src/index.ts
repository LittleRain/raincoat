export type ToolDefinition = {
  id: string;
  name: string;
  pathPrefix: string;
  enabled: boolean;
};

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export type JobRecord = {
  id: string;
  toolId: string;
  type: string;
  status: JobStatus;
  createdAt: string;
  startedAt?: string;
  finishedAt?: string;
  artifactPath?: string;
};

export type ReportScenario = {
  id: string;
  name: string;
  owner: string;
  pathPrefix: string;
  defaultReleaseId: string;
  description: string;
};

export type ScriptRelease = {
  id: string;
  scenarioId: string;
  version: string;
  scriptPath: string;
  manifestPath: string;
  gitRevision: string;
  status: "draft" | "active";
};

export type RunArtifact = {
  runId: string;
  kind: "html" | "json" | "zip" | "log";
  fileName: string;
  absolutePath: string;
  publicPath: string;
};
