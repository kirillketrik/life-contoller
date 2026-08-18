import { defineRouting } from "next-intl/routing";

/**
 * Russian ships first and is the default locale. Adding another locale (e.g.
 * English) later is just appending it here plus a matching messages/<locale>.json
 * file — no routing/middleware changes needed.
 */
export const routing = defineRouting({
  locales: ["ru"],
  defaultLocale: "ru",
  localePrefix: "as-needed",
});
