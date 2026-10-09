import { expect, test } from "@playwright/test";
import { mergeCatalogs, pruneEmpty } from "../src/i18n/catalog";

test("nested translation fallback keeps translated siblings and fills missing leaves", () => {
  const base = { entry: { title: "Entry", error: { retry: "Retry", text: "Failed" } } };
  const translated = { entry: { title: "प्रविष्टि", error: { retry: "फिर प्रयास करें", text: "" } } };
  expect(mergeCatalogs(base, pruneEmpty(translated))).toEqual({
    entry: { title: "प्रविष्टि", error: { retry: "फिर प्रयास करें", text: "Failed" } },
  });
  expect(base.entry.error.text).toBe("Failed");
});
