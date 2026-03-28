import { createServer } from "node:http";

import { platformPorts } from "@raincoat/shared-config";

import { createWebApp } from "./app";

const port = Number(process.env.PORT ?? platformPorts.web);

if (require.main === module) {
  createServer(createWebApp()).listen(port, () => {
    console.log(`raincoat-web listening on ${port}`);
  });
}
