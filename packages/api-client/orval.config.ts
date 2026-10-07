import { defineConfig } from "orval";

// Generated from the FastAPI OpenAPI document. Do not edit files in src/gen by hand;
// run `pnpm gen:client` from the repo root instead.
export default defineConfig({
  api: {
    input: "./openapi.json",
    output: {
      mode: "tags-split",
      target: "./src/gen/endpoints",
      schemas: "./src/gen/model",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      override: {
        mutator: { path: "./src/fetcher.ts", name: "apiFetch" },
        // GET → useQuery + useSuspenseQuery hooks; POST/PUT/PATCH/DELETE → useMutation hooks.
        query: { useSuspenseQuery: true },
        // apiFetch throws ApiError on any non-2xx, so results are always the success shape.
        fetch: { forceSuccessResponse: true },
      },
    },
  },
  apiZod: {
    input: "./openapi.json",
    output: {
      mode: "tags-split",
      target: "./src/gen/zod",
      client: "zod",
      fileExtension: ".zod.ts",
      clean: true,
    },
  },
});
