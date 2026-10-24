import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// The dev server is reached through the builder's preview proxy
// (<id>.preview.ninoo.app over TLS), so HMR must dial the proxy's port, not
// 5173. The image sets HMR_CLIENT_PORT=443; locally it falls back to 5173.
const hmrClientPort = Number(process.env.HMR_CLIENT_PORT ?? 5173);

export default defineConfig({
  plugins: [react(), tailwindcss(), ninooPreviewErrors()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    hmr: { clientPort: hmrClientPort },
    // An optional Python backend (api/, FastAPI on 8000) shares the preview's
    // origin through this proxy, so the browser just calls fetch("/api/...").
    // A branch's own preview runs its backend on another port (API_PORT).
    proxy: { "/api": `http://127.0.0.1:${process.env.API_PORT ?? 8000}` },
  },
  preview: { host: true, port: 5173 },
});

/**
 * Dev server only, never in a build: when the app shown in the Ninoo Builder's
 * preview throws (or fails to compile), tell the Builder so it can offer to
 * fix it. Does nothing when the app is not framed by the Builder.
 */
function ninooPreviewErrors(): Plugin {
  const reporter = `
// Only the page framing this one hears about its errors: its origin comes
// from ancestorOrigins (Chrome, Safari) or the referrer (Firefox). With
// neither, nothing is sent, so no other site that frames the preview sees them.
const ninooParent = (() => {
  try {
    const a = window.location.ancestorOrigins;
    if (a && a.length) return a[0];
    return document.referrer ? new URL(document.referrer).origin : null;
  } catch {
    return null;
  }
})();
if (window.parent !== window && ninooParent && ninooParent !== "null") {
  const post = (data) => { try { window.parent.postMessage(data, ninooParent); } catch {} };
  // A fresh page starts clean: whatever the last one reported is gone with it.
  post({ type: "ninoo:error-cleared" });
  const send = (kind, message, stack) => {
    message = String(message || "Unknown error").replace(/^Uncaught /, "");
    if (message === "Script error." || message.startsWith("ResizeObserver loop")) return;
    post({ type: "ninoo:error", kind, message: message.slice(0, 2000), stack: String(stack || "").slice(0, 4000) });
  };
  window.addEventListener("error", (e) => send("runtime", e.message || (e.error && e.error.message), e.error && e.error.stack));
  window.addEventListener("unhandledrejection", (e) => send("runtime", (e.reason && e.reason.message) || e.reason, e.reason && e.reason.stack));
  import("/@vite/client").then(({ createHotContext }) => {
    const hot = createHotContext("/@ninoo/preview-errors");
    hot.on("vite:error", (p) => {
      const err = (p && p.err) || {};
      const where = err.id ? err.id + (err.loc ? ":" + err.loc.line + ":" + err.loc.column : "") : "";
      send("build", err.message, [where, err.frame].filter(Boolean).join("\\n"));
    });
    hot.on("vite:afterUpdate", () => post({ type: "ninoo:error-cleared" }));
  }).catch(() => {});
}`;
  return {
    name: "ninoo-preview-errors",
    apply: "serve",
    transformIndexHtml: () => [{ tag: "script", attrs: { type: "module" }, children: reporter, injectTo: "head-prepend" }],
  };
}
