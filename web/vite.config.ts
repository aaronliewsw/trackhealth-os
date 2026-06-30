import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import type { IncomingMessage } from "node:http";
import { fileURLToPath } from "node:url";
import { defineConfig, type Connect, type Plugin } from "vite";

const stateFixturePath = fileURLToPath(
  new URL("../tests/fixtures/contract/state.json", import.meta.url),
);
const seriesFixturePath = fileURLToPath(
  new URL("../tests/fixtures/contract/series.json", import.meta.url),
);
const readingsFixturePath = fileURLToPath(
  new URL("../tests/fixtures/contract/readings.json", import.meta.url),
);

function readJsonFixture(pathname: string): Record<string, unknown> {
  return JSON.parse(readFileSync(pathname, "utf8")) as Record<string, unknown>;
}

function sendJson(
  response: Connect.ServerResponse,
  body: string | Record<string, unknown>,
  statusCode = 200,
) {
  response.statusCode = statusCode;
  response.setHeader("Content-Type", "application/json; charset=utf-8");
  response.setHeader("Cache-Control", "no-store");
  response.end(typeof body === "string" ? body : JSON.stringify(body));
}

function readRequestJson(request: IncomingMessage): Promise<Record<string, unknown>> {
  return new Promise((resolve, reject) => {
    let body = "";
    request.setEncoding("utf8");
    request.on("data", (chunk: string) => {
      body += chunk;
    });
    request.on("end", () => {
      if (!body.trim()) {
        resolve({});
        return;
      }

      try {
        resolve(JSON.parse(body) as Record<string, unknown>);
      } catch (error) {
        reject(error);
      }
    });
    request.on("error", reject);
  });
}

function stateMockPlugin(): Plugin {
  type MockConnectionState = "connected" | "disconnected" | "needs_mfa";

  let connectionState: MockConnectionState = "disconnected";
  let lastSuccessAt: string | null = null;

  function mockedState(): Record<string, unknown> {
    const state = readJsonFixture(stateFixturePath);
    state.connection = { state: connectionState };

    const freshness =
      typeof state.freshness === "object" && state.freshness !== null
        ? (state.freshness as Record<string, unknown>)
        : {};
    state.freshness = {
      ...freshness,
      last_success_at: lastSuccessAt,
    };

    if (connectionState !== "connected") {
      state.metrics = {};
    }

    return state;
  }

  const serveContractFixture: Connect.NextHandleFunction = (request, response, next) => {
    const requestUrl = new URL(request.url ?? "/", "http://trackhealth.local");
    const pathname = requestUrl.pathname;

    if (pathname === "/api/connection" && request.method === "GET") {
      sendJson(response, { state: connectionState });
      return;
    }

    if (pathname === "/api/connection" && request.method === "POST") {
      void readRequestJson(request)
        .then((body) => {
          connectionState =
            typeof body.mfa_code === "string" && body.mfa_code.trim()
              ? "connected"
              : "needs_mfa";
          sendJson(response, { state: connectionState });
        })
        .catch(() => {
          sendJson(response, { detail: "Invalid JSON body." }, 400);
        });
      return;
    }

    if (pathname === "/api/connection" && request.method === "DELETE") {
      connectionState = "disconnected";
      lastSuccessAt = null;
      sendJson(response, { state: connectionState });
      return;
    }

    if (pathname === "/api/sync" && request.method === "POST") {
      lastSuccessAt = new Date().toISOString();
      sendJson(response, {
        error: null,
        last_success_at: lastSuccessAt,
        state: "idle",
      });
      return;
    }

    if (pathname === "/api/backfill" && request.method === "POST") {
      lastSuccessAt = new Date().toISOString();
      sendJson(response, {
        days_written: 28,
        error: null,
        last_success_at: lastSuccessAt,
        state: "idle",
      });
      return;
    }

    if (request.method !== "GET") {
      next();
      return;
    }

    if (pathname === "/api/state") {
      sendJson(response, mockedState());
      return;
    }

    const seriesMatch = pathname.match(/^\/api\/metrics\/([^/]+)\/series$/);

    if (seriesMatch) {
      const series = readJsonFixture(seriesFixturePath);
      series.metric = decodeURIComponent(seriesMatch[1]);
      series.range = requestUrl.searchParams.get("range") ?? series.range;
      sendJson(response, series);
      return;
    }

    const readingsMatch = pathname.match(/^\/api\/metrics\/([^/]+)\/readings$/);

    if (readingsMatch) {
      const readings = readJsonFixture(readingsFixturePath);
      readings.metric = decodeURIComponent(readingsMatch[1]);
      readings.on = requestUrl.searchParams.get("on") ?? readings.on;
      sendJson(response, readings);
      return;
    }

    next();
  };

  return {
    name: "trackhealth-contract-mock",
    configureServer(server) {
      server.middlewares.use(serveContractFixture);
    },
    configurePreviewServer(server) {
      server.middlewares.use(serveContractFixture);
    },
  };
}

export default defineConfig({
  plugins: [react(), stateMockPlugin()],
  server: {
    port: 5173,
  },
  preview: {
    port: 4173,
  },
});
