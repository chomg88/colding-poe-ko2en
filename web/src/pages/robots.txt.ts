import type { APIRoute } from "astro";

/* 도메인이 site.js 한 곳에서만 정해지도록 정적 파일 대신 생성한다. */
export const GET: APIRoute = ({ site }) =>
  new Response(
    `User-agent: *\nAllow: /\n\nSitemap: ${new URL("sitemap-index.xml", site)}\n`,
    { headers: { "Content-Type": "text/plain; charset=utf-8" } },
  );
