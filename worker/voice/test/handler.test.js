// Handler tests (added during review): limits run before any paid upstream call,
// fail closed, and the happy paths shape the response. fetch is mocked; no network.
import { test, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import worker from "../src/index.js";

const ORIGIN = "https://smoke-or-vog.pages.dev";
const fixture = (n) => JSON.parse(readFileSync(new URL(`./fixtures/${n}`, import.meta.url)));
let calls;
const realFetch = globalThis.fetch;

function wav(seconds, rate = 16000) {
  const data = Math.round(seconds * rate) * 2;
  const b = new Uint8Array(44 + data);
  const v = new DataView(b.buffer);
  const w = (o, s) => [...s].forEach((c, i) => (b[o + i] = c.charCodeAt(0)));
  w(0, "RIFF"); v.setUint32(4, 36 + data, true); w(8, "WAVE"); w(12, "fmt ");
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true);
  v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, data, true);
  return b;
}
function env(over = {}) {
  const kv = new Map();
  return { META_API_KEY: "test-key", SITE_ORIGIN: ORIGIN, DAILY_CAP: "2",
    RATE_LIMITER: { limit: async () => ({ success: true }) },
    VOICE_KV: { get: async (k) => kv.get(k) ?? null, put: async (k, v) => kv.set(k, v) }, ...over };
}
async function ask(body, e = env(), headers = {}) {
  let init;
  if (body instanceof FormData) {
    const r = new Request("https://x/ask", { method: "POST", body });
    const raw = new Uint8Array(await r.arrayBuffer());
    init = { body: raw, headers: { "content-type": r.headers.get("content-type"), "content-length": String(raw.byteLength) } };
  } else {
    const raw = JSON.stringify(body);
    init = { body: raw, headers: { "content-type": "application/json", "content-length": String(Buffer.byteLength(raw)) } };
  }
  const req = new Request("https://voice.example/ask", { method: "POST", ...init,
    headers: { origin: ORIGIN, "cf-connecting-ip": "203.0.113.9", ...init.headers, ...headers } });
  const res = await worker.fetch(req, e, {});
  return { status: res.status, body: await res.json(), res };
}
function voiceForm(lang = "en", seconds = 2) {
  const f = new FormData();
  f.append("lang", lang);
  f.append("audio", new Blob([wav(seconds)], { type: "audio/wav" }), "a.wav");
  return f;
}

beforeEach(() => {
  calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push(String(url));
    if (String(url).endsWith("/asr/transcribe")) return Response.json({ transcript: "Is there vog in Kona?" });
    if (String(url).endsWith("/data/index.json")) return Response.json(fixture("index.json"));
    if (String(url).endsWith("/data/live/run.json")) return Response.json(fixture("run_live_noplume.json"));
    if (String(url).endsWith("/v1/responses")) return Response.json({ output_text: "No haze plume was detected from space." });
    return new Response("nope", { status: 404 });
  };
});
afterEach(() => { globalThis.fetch = realFetch; });

test("rate-limited voice request makes no upstream call", async () => {
  const r = await ask(voiceForm(), env({ RATE_LIMITER: { limit: async () => ({ success: false }) } }));
  assert.equal(r.status, 429);
  assert.equal(r.body.error, "rate_limited");
  assert.deepEqual(calls, []);
});

test("daily cap reached: 429 and no upstream call", async () => {
  const e = env({ DAILY_CAP: "1" });
  assert.equal((await ask({ lang: "en", text: "vog?" }, e)).status, 200);
  calls = [];
  const r = await ask(voiceForm(), e);
  assert.equal(r.status, 429);
  assert.equal(r.body.error, "daily_cap");
  assert.deepEqual(calls, []);
});

test("missing bindings or bad cap fail closed", async () => {
  assert.equal((await ask(voiceForm(), env({ VOICE_KV: undefined }))).status, 502);
  assert.equal((await ask(voiceForm(), env({ RATE_LIMITER: undefined }))).status, 502);
  assert.equal((await ask(voiceForm(), env({ DAILY_CAP: "abc" }))).status, 429);
  assert.deepEqual(calls, []);
});

test("audio over 20 s rejected before any call", async () => {
  const r = await ask(voiceForm("en", 20.5));
  assert.equal(r.status, 400);
  assert.equal(r.body.error, "audio_too_long");
  assert.deepEqual(calls, []);
});

test("voice happy path: transcribe, read latest run, answer, disclaimer", async () => {
  const r = await ask(voiceForm("vi"));
  assert.equal(r.status, 200);
  assert.equal(r.body.transcript, "Is there vog in Kona?");
  assert.equal(r.body.machine_translated, true);
  assert.match(r.body.disclaimer, /Ước tính/);
  assert.match(r.body.disclaimer_en, /not an official warning/);
  assert.equal(r.res.headers.get("cache-control"), "no-store");
  assert.ok(calls[0].endsWith("/asr/transcribe"));
});

test("typed Hawaiian works; Hawaiian audio is refused without a call", async () => {
  assert.equal((await ask({ lang: "haw", text: "He vog anei?" })).status, 200);
  calls = [];
  const r = await ask(voiceForm("haw"));
  assert.equal(r.status, 400);
  assert.equal(r.body.message, "Voice not yet supported for this language");
  assert.deepEqual(calls, []);
});

test("foreign origin is refused", async () => {
  const r = await ask({ lang: "en", text: "hi" }, env(), { origin: "https://evil.example" });
  assert.equal(r.status, 403);
  assert.equal(r.res.headers.get("access-control-allow-origin"), null);
  assert.deepEqual(calls, []);
});

test("upstream error body is not echoed", async () => {
  globalThis.fetch = async () => new Response("secret upstream detail", { status: 500 });
  const r = await ask({ lang: "en", text: "vog?" });
  assert.equal(r.status, 502);
  assert.deepEqual(r.body, { error: "upstream" });
});
