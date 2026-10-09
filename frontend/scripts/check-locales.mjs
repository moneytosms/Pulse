import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../src/i18n/messages");
function leaves(object, prefix = "", out = {}) {
  for (const [key, value] of Object.entries(object)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out[path] = value;
    else if (value && typeof value === "object" && !Array.isArray(value)) leaves(value, path, out);
    else throw new Error(`Invalid catalog value: ${path}`);
  }
  return out;
}
const variables = value => [...new Set([...value.matchAll(/\{\s*(\w+)\s*[,}]/g)].map(m => m[1]))].sort().join(",");
const failures = [];
for (const file of readdirSync(`${root}/en`).filter(f => f.endsWith(".json"))) {
  const english = leaves(JSON.parse(readFileSync(`${root}/en/${file}`, "utf8")));
  for (const locale of ["en", "hi", "ta", "ml"]) {
    const catalog = leaves(JSON.parse(readFileSync(`${root}/${locale}/${file}`, "utf8")));
    for (const key of new Set([...Object.keys(english), ...Object.keys(catalog)])) {
      if (!(key in english) || !(key in catalog) || !catalog[key].trim()) failures.push(`${locale}/${file}: missing/empty/extra ${key}`);
      else if (variables(english[key]) !== variables(catalog[key])) failures.push(`${locale}/${file}: interpolation mismatch ${key}`);
    }
  }
}
const api = readFileSync(resolve(import.meta.dirname, "../src/lib/generated/api.ts"), "utf8");
for (const [name, file, prefix] of [
  ["ErrorCode", "errors.json", ""],
  ["AuditAction", "audit.json", "actions."],
  ["NotificationType", "notifications.json", "list.types."],
  ["NotificationType", "notifications.json", "content."],
]) {
  const match = api.match(new RegExp(`export const ${name}Values = (\\[[^;]+\\]) as const;`));
  if (!match) throw new Error(`Missing generated enum ${name}`);
  for (const locale of ["en", "hi", "ta", "ml"]) {
    const catalog = leaves(JSON.parse(readFileSync(`${root}/${locale}/${file}`, "utf8")));
    for (const value of JSON.parse(match[1])) {
      if (!catalog[prefix + value]) failures.push(`${locale}/${file}: missing ${name} ${value}`);
    }
  }
}
if (failures.length) { failures.forEach(f => console.error(f)); process.exitCode = 1; }
else console.log("Four locale catalogs have matching keys and interpolation variables; no empty messages.");
