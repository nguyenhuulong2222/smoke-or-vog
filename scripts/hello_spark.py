"""Smoke test (a): Muse Spark answers one question via the Responses API."""

import openai

from _common import client, log_cost, spark_cost

MODELS = ["muse-spark-1.3", "muse-spark-1.2"]
QUESTION = "In one sentence: what is vog, and where does Hawaiʻi's vog come from?"


def main() -> None:
    c = client()
    for model in MODELS:
        try:
            r = c.responses.create(model=model, input=QUESTION)
        except openai.APIStatusError as e:
            print(f"{model}: HTTP {e.status_code}, trying fallback")
            log_cost("hello_spark", model, 0.0, status=f"http_{e.status_code}")
            continue
        cost, toks = spark_cost(r.usage)
        log_cost("hello_spark", r.model, cost, **toks)
        print(f"model: {r.model}")
        print(f"answer: {r.output_text}")
        print(f"usage: {toks}  cost: ${cost:.6f}")
        return
    raise SystemExit("all models failed")


if __name__ == "__main__":
    main()
