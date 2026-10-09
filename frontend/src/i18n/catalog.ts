export type Catalog = Record<string, unknown>;

export function pruneEmpty(catalog: Catalog): Catalog {
  const out: Catalog = {};
  for (const [key, value] of Object.entries(catalog)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const nested = pruneEmpty(value as Catalog);
      if (Object.keys(nested).length > 0) out[key] = nested;
    } else if (value !== "") {
      out[key] = value;
    }
  }
  return out;
}

export function mergeCatalogs(base: Catalog, override: Catalog): Catalog {
  const out: Catalog = { ...base };
  for (const [key, value] of Object.entries(override)) {
    out[key] =
      value && typeof value === "object" && !Array.isArray(value)
        ? mergeCatalogs((base[key] && typeof base[key] === "object" ? base[key] : {}) as Catalog, value as Catalog)
        : value;
  }
  return out;
}
