import { promises as fs } from "node:fs";
import path from "node:path";

import type { ReportScenario } from "@raincoat/shared-types";

const capture = (content: string, field: string) => {
  const match = content.match(new RegExp(`^${field}:\\s*(.+)$`, "m"));
  return match?.[1]?.trim() ?? "";
};

const trimQuotes = (value: string) => value.replace(/^['"]|['"]$/g, "");

export const listScenarioDefinitions = async (
  manifestDirectory: string | URL
): Promise<ReportScenario[]> => {
  const directory = manifestDirectory instanceof URL
    ? manifestDirectory.pathname
    : manifestDirectory;

  const fileNames = (await fs.readdir(directory))
    .filter((item) => item.endsWith(".yaml"))
    .sort();

  const items = await Promise.all(
    fileNames.map(async (fileName) => {
      const fullPath = path.join(directory, fileName);
      const content = await fs.readFile(fullPath, "utf8");

      return {
        id: trimQuotes(capture(content, "id")),
        name: trimQuotes(capture(content, "name")),
        owner: trimQuotes(capture(content, "owner")),
        pathPrefix: trimQuotes(capture(content, "pathPrefix")),
        defaultReleaseId: trimQuotes(capture(content, "defaultReleaseId")),
        description: trimQuotes(capture(content, "description"))
      } satisfies ReportScenario;
    })
  );

  return items.sort((left, right) => left.id.localeCompare(right.id));
};
