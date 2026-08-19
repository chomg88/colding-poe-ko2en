import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";
import { SITE } from "./src/site.js";

export default defineConfig({
  site: SITE.origin,
  integrations: [sitemap()],
  build: { format: "directory" },
});
