import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.AGENTGOV_API_TARGET || "http://127.0.0.1:8007";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/agents": apiTarget,
      "/runs": apiTarget,
      "/sessions": apiTarget,
      "/approvals": apiTarget,
      "/delegations": apiTarget,
      "/dashboard": apiTarget,
      "/config": apiTarget,
      "/tasks": apiTarget,
      "/tools": apiTarget,
      "/skills": apiTarget,
      "/memory": apiTarget,
      "/knowledge": apiTarget,
      "/worker": apiTarget,
      "/events": apiTarget
    }
  }
});
