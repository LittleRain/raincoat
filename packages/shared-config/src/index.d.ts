import type { ToolDefinition } from "@raincoat/shared-types";
export declare const platformName = "Raincoat";
export declare const toolPathPrefix: {
    readonly reports: "/reports";
};
export declare const defaultToolDefinitions: ToolDefinition[];
export declare const platformPorts: {
    readonly web: 3100;
    readonly api: 3200;
};
export declare const getPublicRoutes: () => {
    home: string;
    reportsHome: "/reports";
    apiPrefix: string;
    artifactsPrefix: string;
};
export declare const buildRunPaths: (runsRoot: string, runId: string) => {
    root: string;
    inputDir: string;
    outputDir: string;
    logsDir: string;
    statusFile: string;
    metadataFile: string;
};
