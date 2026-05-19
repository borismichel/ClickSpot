import { defineConfig } from "vite";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";

const zustandRoot = fileURLToPath(new URL("./node_modules/zustand", import.meta.url));

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8193,
    proxy: {
      "/api": {
        target: "http://localhost:8192",
        changeOrigin: true,
      },
      "/health": {
        target: "http://localhost:8192",
        changeOrigin: true,
      },
    },
  },
  // zustand 4.5.x ships a broken `exports` map: the `import` condition for the
  // `./traditional` and `./shallow` subpaths points at `./esm/*.mjs` files that
  // don't exist in the published tarball (only `./esm/*.js` does). Vite/esbuild
  // honors the `import` condition, follows the broken path, and dev startup
  // fails with "Failed to resolve import zustand/traditional".
  //
  // @xyflow/react is what triggers this — it imports those subpaths from its
  // pre-bundled output. We work around it by aliasing directly to the working
  // files at the package root, bypassing the broken exports map.
  resolve: {
    alias: [
      { find: /^zustand\/traditional$/, replacement: `${zustandRoot}/traditional.js` },
      { find: /^zustand\/shallow$/, replacement: `${zustandRoot}/shallow.js` },
    ],
  },
});
