"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.listScenarioDefinitions = void 0;
const node_fs_1 = require("node:fs");
const node_path_1 = __importDefault(require("node:path"));
const capture = (content, field) => {
    const match = content.match(new RegExp(`^${field}:\\s*(.+)$`, "m"));
    return match?.[1]?.trim() ?? "";
};
const trimQuotes = (value) => value.replace(/^['"]|['"]$/g, "");
const listScenarioDefinitions = async (manifestDirectory) => {
    const directory = manifestDirectory instanceof URL
        ? manifestDirectory.pathname
        : manifestDirectory;
    const fileNames = (await node_fs_1.promises.readdir(directory))
        .filter((item) => item.endsWith(".yaml"))
        .sort();
    const items = await Promise.all(fileNames.map(async (fileName) => {
        const fullPath = node_path_1.default.join(directory, fileName);
        const content = await node_fs_1.promises.readFile(fullPath, "utf8");
        return {
            id: trimQuotes(capture(content, "id")),
            name: trimQuotes(capture(content, "name")),
            owner: trimQuotes(capture(content, "owner")),
            pathPrefix: trimQuotes(capture(content, "pathPrefix")),
            defaultReleaseId: trimQuotes(capture(content, "defaultReleaseId")),
            description: trimQuotes(capture(content, "description"))
        };
    }));
    return items.sort((left, right) => left.id.localeCompare(right.id));
};
exports.listScenarioDefinitions = listScenarioDefinitions;
