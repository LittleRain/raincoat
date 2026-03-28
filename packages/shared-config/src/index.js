"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.buildRunPaths = exports.getPublicRoutes = exports.platformPorts = exports.defaultToolDefinitions = exports.toolPathPrefix = exports.platformName = void 0;
const node_path_1 = __importDefault(require("node:path"));
exports.platformName = "Raincoat";
exports.toolPathPrefix = {
    reports: "/reports"
};
exports.defaultToolDefinitions = [
    {
        id: "reports",
        name: "周报系统",
        pathPrefix: exports.toolPathPrefix.reports,
        enabled: true
    }
];
exports.platformPorts = {
    web: 3100,
    api: 3200
};
const getPublicRoutes = () => ({
    home: "/",
    reportsHome: exports.toolPathPrefix.reports,
    apiPrefix: "/api",
    artifactsPrefix: "/artifacts"
});
exports.getPublicRoutes = getPublicRoutes;
const buildRunPaths = (runsRoot, runId) => {
    const root = node_path_1.default.join(runsRoot, runId);
    return {
        root,
        inputDir: node_path_1.default.join(root, "input"),
        outputDir: node_path_1.default.join(root, "output"),
        logsDir: node_path_1.default.join(root, "logs"),
        statusFile: node_path_1.default.join(root, "status.json"),
        metadataFile: node_path_1.default.join(root, "metadata.json")
    };
};
exports.buildRunPaths = buildRunPaths;
