import express from "express";
import path from "node:path";

import { defaultToolDefinitions, platformName, toolPathPrefix } from "@raincoat/shared-config";
import { listScenarioDefinitions } from "@raincoat/task-sdk";

const reportsManifestDir = path.resolve(
  __dirname,
  "../../../tools/reports/manifests"
);

const renderHomePage = () => {
  const toolCards = defaultToolDefinitions
    .map(
      (tool) => `
        <li>
          <a href="${tool.pathPrefix}">${tool.name}</a>
          <p>路径前缀：${tool.pathPrefix}</p>
        </li>
      `
    )
    .join("");

  return `<!doctype html>
  <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>${platformName}</title>
    </head>
    <body>
      <main>
        <h1>${platformName}</h1>
        <p>内部工具工作台</p>
        <ul>${toolCards}</ul>
      </main>
    </body>
  </html>`;
};

const renderReportsPage = async () => {
  const scenarios = await listScenarioDefinitions(reportsManifestDir);
  const items = scenarios
    .map(
      (item) => `
        <li>
          <strong>${item.id}</strong>
          <div>${item.name}</div>
          <div>${item.description}</div>
        </li>
      `
    )
    .join("");

  return `<!doctype html>
  <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>周报系统</title>
    </head>
    <body>
      <main>
        <a href="/">返回工作台</a>
        <h1>报告场景</h1>
        <p>当前挂载路径：${toolPathPrefix.reports}</p>
        <ul>${items}</ul>
      </main>
    </body>
  </html>`;
};

export const createWebApp = () => {
  const app = express();

  app.get("/", (_req, res) => {
    res.status(200).type("html").send(renderHomePage());
  });

  app.get("/reports", async (_req, res, next) => {
    try {
      res.status(200).type("html").send(await renderReportsPage());
    } catch (error) {
      next(error);
    }
  });

  app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
    const message = error instanceof Error ? error.message : String(error);
    res.status(500).type("html").send(`<h1>web error</h1><pre>${message}</pre>`);
  });

  return app;
};
