import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

/* 가이드 글. src/content/guides/*.md 에 파일을 넣으면 목록과 사이트맵에
   자동으로 잡힌다. draft: true 면 빌드에서 빠진다. */
const guides = defineCollection({
  loader: glob({ pattern: "**/*.md", base: "./src/content/guides" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    published: z.coerce.date(),
    updated: z.coerce.date().optional(),
    tags: z.array(z.string()).default([]),
    draft: z.boolean().default(false),
  }),
});

export const collections = { guides };
