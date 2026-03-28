import express from "express";
import path from "node:path";

import { toolPathPrefix } from "@raincoat/shared-config";
import { listScenarioDefinitions } from "@raincoat/task-sdk";

const reportsManifestDir = path.resolve(
  __dirname,
  "../../../tools/reports/manifests"
);

export const createApiApp = () => {
  const app = express();

  app.use(express.json());

  app.get("/api/health", (_req, res) => {
    res.status(200).json({ status: "ok", service: "raincoat-api" });
  });

  app.get("/api/tools", (_req, res) => {
    res.status(200).json({
      items: [
        {
          id: "reports",
          name: "周报系统",
          pathPrefix: toolPathPrefix.reports,
          enabled: true
        }
      ]
    });
  });

  app.get("/api/reports/scenarios", async (_req, res, next) => {
    try {
      const items = await listScenarioDefinitions(reportsManifestDir);
      res.status(200).json({ items });
    } catch (error) {
      next(error);
    }
  });

  app.get("/api/reports/scenarios/:scenarioId", async (req, res, next) => {
    try {
      const items = await listScenarioDefinitions(reportsManifestDir);
      const item = items.find((entry) => entry.id === req.params.scenarioId);

      if (!item) {
        return res.status(404).json({ error: "scenario not found" });
      }

      return res.status(200).json(item);
    } catch (error) {
      return next(error);
    }
  });

  app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    const message = error instanceof Error ? error.message : String(error);
    res.status(500).json({ error: "internal_error", message });
  });

  return app;
};
