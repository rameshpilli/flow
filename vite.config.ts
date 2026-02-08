import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteSingleFile } from "vite-plugin-singlefile";

const INPUT = process.env.INPUT;

export default defineConfig(({ command }) => {
  if (command === "build" && !INPUT) {
    throw new Error("INPUT environment variable is not set");
  }

  return {
    plugins: [react(), viteSingleFile()],
    build: {
      rollupOptions: {
        input: INPUT,
      },
      outDir: "dist",
      emptyOutDir: false,
    },
  };
});
