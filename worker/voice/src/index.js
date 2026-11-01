// src/index.js — Cloudflare Worker fetch handler for the voice proxy.
import {
  ALLOWED_LOCAL_ORIGIN,
  LANGS,
  MAX_BODY_BYTES,
  SITE_ORIGIN_DEFAULT,
  TRANSCRIBE_BIAS,
  buildContext,
  buildPrompt,
  corsHeaders,
  dayKey,
  disclaimer,
  DISCLAIMER_EN,
  parseWav,
  validateRequest,
} from "./lib.js";

async function sha256Hex(text) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function jsonResponse(obj, status, origin, allowed) {
  const headers = new Headers({
    "content-type": "application/json",
    "cache-control": "no-store",
    ...corsHeaders(origin, allowed),
  });
  return new Response(JSON.stringify(obj), { status, headers });
}

function upstreamFailure(origin, allowed, type) {
  console.error(type);
  return jsonResponse({ error: "upstream" }, 502, origin, allowed);
}

function makeWavAudioPart(audioBytes) {
  return new Blob([audioBytes], { type: "audio/wav" });
}

async function transcribe(audioBytes, lang, apiKey) {
  const form = new FormData();
  form.append(
    "request",
    new Blob(
      [
        JSON.stringify({
          model: "muse-voice-transcribe-1.0",
          audioEncoding: "WAV",
          mode: "PUSH_TO_TALK",
          languageBias: [TRANSCRIBE_BIAS[lang]],
          keywords: [
            "vog",
            "Kīlauea",
            "Mauna Loa",
            "Kona",
            "Hilo",
            "Pāhala",
            "Maui",
            "Oʻahu",
          ],
        }),
      ],
      { type: "application/json" },
    ),
    "request.json",
  );
  form.append("audio", makeWavAudioPart(audioBytes), "audio.wav");
  const res = await fetch("https://api.meta.ai/v1/asr/transcribe", {
    method: "POST",
    headers: {
      authorization: `Bearer ${apiKey}`,
      accept: "application/json",
    },
    body: form,
  });
  if (!res.ok) {
    console.error(`transcribe_status:${res.status}`);
    return null;
  }
  let data = null;
  try {
    data = await res.json();
  } catch {
    return null;
  }
  return data && typeof data.transcript === "string" ? data.transcript : null;
}

function readAnswerText(data) {
  if (data && typeof data.output_text === "string" && data.output_text.trim()) {
    return data.output_text;
  }
  if (data && Array.isArray(data.output)) {
    const parts = [];
    for (const item of data.output) {
      for (const block of item?.content ?? []) {
        if (block && block.type === "output_text" && typeof block.text === "string") {
          parts.push(block.text);
        }
      }
    }
    if (parts.length > 0) return parts.join("");
  }
  return null;
}

// Per-IP rate limit and daily cap. Runs BEFORE any paid upstream call and fails
// closed: a missing binding refuses the request instead of skipping the limit.
async function enforceLimits(request, env, origin, allowed) {
  if (!env.RATE_LIMITER || !env.VOICE_KV) {
    return upstreamFailure(origin, allowed, "limits_unconfigured");
  }
  const day = dayKey(new Date());
  const ip = request.headers.get("cf-connecting-ip") || "";
  const rateKey = await sha256Hex(`${ip}:${day}`);
  {
    let limited = null;
    try {
      limited = await env.RATE_LIMITER.limit({ key: rateKey });
    } catch {
      return upstreamFailure(origin, allowed, "rate_limit_failed");
    }
    if (!limited || limited.success !== true) {
      return jsonResponse({ error: "rate_limited" }, 429, origin, allowed);
    }
  }

  const cap = parseInt(env.DAILY_CAP ?? "300", 10);
  if (!(cap > 0)) {
    return jsonResponse({ error: "daily_cap" }, 429, origin, allowed);
  }
  const countKey = `count:${day}`;
  {
    let current = 0;
    try {
      const stored = await env.VOICE_KV.get(countKey);
      const parsed = parseInt(stored ?? "0", 10);
      current = Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
    } catch {
      return upstreamFailure(origin, allowed, "daily_cap_failed");
    }
    if (current >= cap) {
      return jsonResponse({ error: "daily_cap" }, 429, origin, allowed);
    }
    try {
      await env.VOICE_KV.put(countKey, String(current + 1), {
        expirationTtl: 172800,
      });
    } catch {
      return upstreamFailure(origin, allowed, "daily_cap_failed");
    }
  }

  return null;
}

async function handleAsk(request, env, origin, allowed) {
  const contentType = request.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const isMultipart = contentType.includes("multipart/form-data");
  if (!isJson && !isMultipart) {
    return jsonResponse({ error: "bad_request" }, 400, origin, allowed);
  }

  const lengthRaw = request.headers.get("content-length");
  const lengthNum = lengthRaw === null ? NaN : Number(lengthRaw);
  if (lengthRaw === null || !Number.isFinite(lengthNum) || lengthNum > MAX_BODY_BYTES) {
    return jsonResponse({ error: "body_too_large" }, 413, origin, allowed);
  }
  const raw = new Uint8Array(await request.arrayBuffer());
  if (raw.byteLength > MAX_BODY_BYTES) {
    return jsonResponse({ error: "body_too_large" }, 413, origin, allowed);
  }

  let lang = null;
  let question = null;
  let transcript = null;

  if (isJson) {
    let body = null;
    try {
      body = JSON.parse(new TextDecoder().decode(raw));
    } catch {
      return jsonResponse({ error: "bad_request" }, 400, origin, allowed);
    }
    lang = body?.lang;
    question = body?.text;
    const failed = validateRequest({ lang, text: question, hasAudio: false });
    if (failed) {
      return jsonResponse(
        { error: failed.error, message: failed.message },
        failed.status,
        origin,
        allowed,
      );
    }
    question = question.trim();
    const limited = await enforceLimits(request, env, origin, allowed);
    if (limited) return limited;
  } else {
    let form = null;
    try {
      const replay = new Request(request.url, {
        method: "POST",
        headers: { "content-type": contentType },
        body: raw,
      });
      form = await replay.formData();
    } catch {
      return jsonResponse({ error: "audio_invalid" }, 400, origin, allowed);
    }
    lang = String(form.get("lang") ?? "");
    if (!LANGS.includes(lang)) {
      return jsonResponse({ error: "lang_unsupported" }, 400, origin, allowed);
    }
    if (lang === "ilo" || lang === "haw") {
      return jsonResponse(
        {
          error: "voice_unsupported",
          message: "Voice not yet supported for this language",
        },
        400,
        origin,
        allowed,
      );
    }
    const audio = form.get("audio");
    if (!audio || typeof audio.arrayBuffer !== "function") {
      return jsonResponse({ error: "audio_invalid" }, 400, origin, allowed);
    }
    const audioBytes = new Uint8Array(await audio.arrayBuffer());
    try {
      parseWav(audioBytes);
    } catch (err) {
      if (err && err.code === "audio_too_long") {
        return jsonResponse({ error: "audio_too_long" }, 400, origin, allowed);
      }
      return jsonResponse({ error: "audio_invalid" }, 400, origin, allowed);
    }

    if (!env.META_API_KEY) {
      return upstreamFailure(origin, allowed, "missing_api_key");
    }
    const limited = await enforceLimits(request, env, origin, allowed);
    if (limited) return limited;
    let rawTranscript = null;
    try {
      rawTranscript = await transcribe(audioBytes, lang, env.META_API_KEY);
    } catch {
      return upstreamFailure(origin, allowed, "transcribe_failed");
    }
    if (rawTranscript === null) {
      return upstreamFailure(origin, allowed, "transcribe_failed");
    }
    if (rawTranscript.trim().length === 0) {
      return jsonResponse({ error: "no_speech" }, 422, origin, allowed);
    }
    const failed = validateRequest({
      lang,
      text: rawTranscript,
      hasAudio: true,
    });
    if (failed) {
      return jsonResponse(
        { error: failed.error, message: failed.message },
        failed.status,
        origin,
        allowed,
      );
    }
    transcript = rawTranscript.trim();
    question = transcript;
  }

  const siteOrigin = env.SITE_ORIGIN || SITE_ORIGIN_DEFAULT;
  let index = null;
  let run = null;
  try {
    const [indexRes, runRes] = await Promise.all([
      fetch(`${siteOrigin}/data/index.json`, {
        headers: { accept: "application/json" },
        cf: { cacheTtl: 120 },
      }),
      fetch(`${siteOrigin}/data/live/run.json`, {
        headers: { accept: "application/json" },
        cf: { cacheTtl: 120 },
      }),
    ]);
    if (!indexRes.ok || !runRes.ok) {
      return upstreamFailure(origin, allowed, `data_failed:${indexRes.status}`);
    }
    index = await indexRes.json();
    run = await runRes.json();
  } catch {
    return upstreamFailure(origin, allowed, "data_failed");
  }

  const context = buildContext(index, run, lang);
  const prompt = buildPrompt(context, question, lang);

  let answer = null;
  try {
    const answerRes = await fetch("https://api.meta.ai/v1/responses", {
      method: "POST",
      headers: {
        authorization: `Bearer ${env.META_API_KEY}`,
        "content-type": "application/json",
        accept: "application/json",
      },
      body: JSON.stringify({
        model: "muse-spark-1.3",
        reasoning: { effort: "minimal" },
        max_output_tokens: 1500,
        input: prompt,
      }),
    });
    if (!answerRes.ok) {
      return upstreamFailure(origin, allowed, `answer_failed:${answerRes.status}`);
    }
    const answerJson = await answerRes.json();
    answer = readAnswerText(answerJson);
    if (!answer) console.error(`answer_empty:${answerJson?.status}:${answerJson?.incomplete_details?.reason ?? ""}`);
  } catch {
    return upstreamFailure(origin, allowed, "answer_failed");
  }
  if (!answer || !answer.trim()) {
    return upstreamFailure(origin, allowed, "answer_failed");
  }

  const payload = {
    lang,
    answer,
    disclaimer: disclaimer(lang),
    disclaimer_en: DISCLAIMER_EN,
    machine_translated: lang !== "en",
    scan: {
      image_time: run?.image_time ?? null,
      verdict: run?.verdict?.class ?? null,
    },
  };
  if (transcript !== null) payload.transcript = transcript;
  return jsonResponse(payload, 200, origin, allowed);
}

export default {
  async fetch(request, env, ctx) {
    const siteOrigin = env?.SITE_ORIGIN || SITE_ORIGIN_DEFAULT;
    const allowed = [siteOrigin, ALLOWED_LOCAL_ORIGIN];
    const origin = request.headers.get("origin");
    try {
      if (!origin || !allowed.includes(origin)) {
        return jsonResponse({ error: "forbidden" }, 403, origin, allowed);
      }
      const url = new URL(request.url);
      const method = request.method.toUpperCase();
      if (method === "OPTIONS" && url.pathname === "/ask") {
        const headers = new Headers({
          "cache-control": "no-store",
          ...corsHeaders(origin, allowed),
        });
        return new Response(null, { status: 204, headers });
      }
      if (method === "GET" && url.pathname === "/health") {
        return jsonResponse({ ok: true }, 200, origin, allowed);
      }
      if (method === "POST" && url.pathname === "/ask") {
        return await handleAsk(request, env, origin, allowed);
      }
      return jsonResponse({ error: "not_found" }, 404, origin, allowed);
    } catch {
      console.error("request_failed");
      return jsonResponse({ error: "upstream" }, 502, origin, allowed);
    }
  },
};
