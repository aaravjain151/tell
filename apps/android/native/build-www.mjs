// Copies the PWA shell (apps/android) into native/www, which Capacitor bundles into the APK. No audio, no data, no secrets.
import { cpSync, rmSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const here = dirname(fileURLToPath(import.meta.url)), src = join(here, ".."), out = join(here, "www");
rmSync(out, { recursive: true, force: true }); mkdirSync(out, { recursive: true });
for (const f of ["index.html", "app.css", "app.js", "worklet.js", "outfit.woff2", "manifest.webmanifest", "lib", "icons"]) cpSync(join(src, f), join(out, f), { recursive: true });
console.log("www ready:", out);
