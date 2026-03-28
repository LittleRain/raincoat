import { createServer } from "node:http";

import { platformPorts } from "@raincoat/shared-config";

import { createApiApp } from "./app";

const port = Number(process.env.PORT ?? platformPorts.api);

if (require.main === module) {
  createServer(createApiApp()).listen(port, () => {
    console.log(`raincoat-api listening on ${port}`);
  });
}
