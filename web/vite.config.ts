import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = "http://127.0.0.1:8001";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/agents": apiTarget,
      "/runs": apiTarget,
      "/sessions": apiTarget,
      "/approvals": apiTarget,
      "/dashboard": apiTarget,
      "/config": apiTarget,
      "/tasks": apiTarget,
      "/tools": apiTarget,
      "/events": apiTarget
    }
  }
});
