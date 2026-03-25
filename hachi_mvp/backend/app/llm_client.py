from __future__ import annotations

import json
import math
import random
import re
import asyncio
from typing import Any

import httpx

from .config import Settings


class ModelGateway:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self.settings.hachi_mock_mode:
            return [self._mock_embedding(text, self.settings.embedding_dim) for text in texts]

        provider = self._resolve_embedding_provider(self.settings.embedding_provider)
        if provider == "dashscope_multimodal":
            return await self._embed_dashscope_multimodal(texts)
        if provider == "openai_compatible":
            return await self._embed_openai_compatible(texts)
        raise ValueError(f"Unsupported embedding provider: {provider}")

    async def _embed_openai_compatible(self, texts: list[str]) -> list[list[float]]:
        if not self.settings.embedding_base_url or not self.settings.embedding_api_key:
            raise ValueError("Embedding configuration is missing")

        batch_size = max(1, int(self.settings.embedding_batch_size))
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            payload: dict[str, Any] = {
                "model": self.settings.embedding_model,
                "input": batch,
                "encoding_format": "float",
            }
            if self.settings.embedding_dim > 0:
                payload["dimensions"] = self.settings.embedding_dim

            data = await self._post_openai_compatible(
                base_url=self.settings.embedding_base_url,
                api_key=self.settings.embedding_api_key,
                path="/embeddings",
                payload=payload,
            )
            sorted_rows = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
            batch_embeddings = [row["embedding"] for row in sorted_rows]
            if len(batch_embeddings) != len(batch):
                raise ValueError(
                    f"Embedding response count mismatch: expected {len(batch)}, got {len(batch_embeddings)}"
                )
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def _embed_dashscope_multimodal(self, texts: list[str]) -> list[list[float]]:
        if not self.settings.embedding_api_key:
            raise ValueError("Embedding configuration is missing")

        try:
            import dashscope
        except ImportError as exc:
            raise ValueError("dashscope package is required for dashscope_multimodal embedding") from exc

        dashscope.api_key = self.settings.embedding_api_key
        batch_size = max(1, int(self.settings.embedding_batch_size))
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            mm_input = [{"text": text} for text in batch]
            response = dashscope.MultiModalEmbedding.call(
                model=self.settings.embedding_model,
                input=mm_input,
            )
            data = self._normalize_dashscope_response(response)
            embeddings_payload = data.get("output", {}).get("embeddings", [])
            if not isinstance(embeddings_payload, list) or not embeddings_payload:
                raise ValueError(f"Invalid DashScope embedding response: {data}")

            batch_embeddings: list[list[float]] = []
            for item in embeddings_payload:
                if not isinstance(item, dict):
                    continue
                vec = item.get("embedding")
                if isinstance(vec, list):
                    batch_embeddings.append(vec)

            if len(batch_embeddings) != len(batch):
                # Fallback: single-item requests, some models may return non-standard payload ordering.
                batch_embeddings = []
                for text in batch:
                    single_resp = dashscope.MultiModalEmbedding.call(
                        model=self.settings.embedding_model,
                        input=[{"text": text}],
                    )
                    single_data = self._normalize_dashscope_response(single_resp)
                    single_items = single_data.get("output", {}).get("embeddings", [])
                    if not single_items or not isinstance(single_items[0], dict):
                        raise ValueError(f"Invalid DashScope single embedding response: {single_data}")
                    vec = single_items[0].get("embedding")
                    if not isinstance(vec, list):
                        raise ValueError(f"Missing embedding vector in DashScope response: {single_data}")
                    batch_embeddings.append(vec)

            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def _resolve_embedding_provider(self, configured_provider: str) -> str:
        provider = (configured_provider or "auto").strip().lower()
        if provider and provider != "auto":
            return provider

        model = self.settings.embedding_model.strip().lower()
        if "vl-embedding" in model or "embedding-vision" in model:
            return "dashscope_multimodal"
        return "openai_compatible"

    def _normalize_dashscope_response(self, response: Any) -> dict[str, Any]:
        # DashScope SDK response can be dict-like or object-like.
        if isinstance(response, dict):
            data = response
        elif hasattr(response, "output"):
            data = {
                "status_code": getattr(response, "status_code", None),
                "code": getattr(response, "code", None),
                "message": getattr(response, "message", None),
                "output": getattr(response, "output", None),
                "request_id": getattr(response, "request_id", None),
            }
        else:
            data = {"raw": str(response)}

        status_code = data.get("status_code")
        if status_code is not None and int(status_code) >= 400:
            raise ValueError(
                f"DashScope API error {status_code}: code={data.get('code')} message={data.get('message')} request_id={data.get('request_id')}"
            )

        if data.get("code") and data.get("code") != "Success":
            raise ValueError(
                f"DashScope API error: code={data.get('code')} message={data.get('message')} request_id={data.get('request_id')}"
            )
        return data

    async def router_plan(
        self,
        *,
        question: str,
        allow_web: bool,
        allow_memory_compress: bool,
        message_count: int,
        token_count: int,
        memory_exists: bool,
    ) -> dict[str, Any]:
        if self.settings.hachi_mock_mode:
            return self._mock_router_plan(
                question=question,
                allow_web=allow_web,
                allow_memory_compress=allow_memory_compress,
                message_count=message_count,
                token_count=token_count,
            )

        if not self.settings.glm5_router_base_url or not self.settings.glm5_router_api_key:
            raise ValueError("GLM5 router configuration is missing")

        system = (
            "You are a routing and tool-selection agent. Decide whether to use web search, "
            "whether to compress memory, and propose 1-3 retrieval queries."
        )
        user = {
            "question": question,
            "constraints": {
                "allow_web": allow_web,
                "allow_memory_compress": allow_memory_compress,
            },
            "session_state": {
                "message_count": message_count,
                "token_count": token_count,
                "memory_exists": memory_exists,
            },
            "output_schema": {
                "need_web_search": "bool",
                "need_memory_compress": "bool",
                "search_queries": ["string"],
                "reason": "string",
            },
        }

        raw = await self._chat_completion(
            base_url=self.settings.glm5_router_base_url,
            api_key=self.settings.glm5_router_api_key,
            model=self.settings.glm5_router_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            max_tokens=700,
            response_json=True,
        )
        parsed = self._parse_json(raw)
        return {
            "need_web_search": bool(parsed.get("need_web_search", False) and allow_web),
            "need_memory_compress": bool(
                parsed.get("need_memory_compress", False) and allow_memory_compress
            ),
            "search_queries": self._normalize_search_queries(parsed.get("search_queries"), question),
            "reason": str(parsed.get("reason", "")),
        }

    async def compress_memory(self, *, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if self.settings.hachi_mock_mode:
            return self._mock_memory_summary(messages)

        if not self.settings.glm5_router_base_url or not self.settings.glm5_router_api_key:
            raise ValueError("GLM5 router configuration is missing")

        system = (
            "Summarize chat memory into structured JSON. Keep only durable facts and decisions. "
            "Do not invent information."
        )
        payload = {
            "messages": [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in messages[-30:]
            ],
            "output_schema": {
                "facts": ["string"],
                "open_questions": ["string"],
                "decisions": ["string"],
                "raw_summary": "string",
            },
        }

        raw = await self._chat_completion(
            base_url=self.settings.glm5_router_base_url,
            api_key=self.settings.glm5_router_api_key,
            model=self.settings.glm5_router_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            max_tokens=900,
            response_json=True,
        )
        parsed = self._parse_json(raw)
        return {
            "facts": self._as_str_list(parsed.get("facts")),
            "open_questions": self._as_str_list(parsed.get("open_questions")),
            "decisions": self._as_str_list(parsed.get("decisions")),
            "raw_summary": str(parsed.get("raw_summary", "")),
        }

    async def analyze_user_signal(
        self,
        *,
        question: str,
        recent_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        heuristic = self._heuristic_user_signal(question=question, recent_messages=recent_messages)
        if self.settings.hachi_mock_mode:
            return heuristic

        if not self.settings.glm5_router_base_url or not self.settings.glm5_router_api_key:
            return heuristic

        system = (
            "You analyze the user's tone and learning needs from the latest message plus recent chat context. "
            "Return JSON only. Focus on whether the previous answer seems insufficient, what explanation style "
            "the user now needs, and whether a weak knowledge topic should be remembered."
        )
        payload = {
            "latest_user_message": question,
            "recent_messages": [
                {
                    "role": str(item.get("role", "")),
                    "content": str(item.get("content", ""))[:600],
                }
                for item in recent_messages[-8:]
            ],
            "output_schema": {
                "tone": "neutral|curious|confused|frustrated|confident",
                "answer_quality_signal": "good|adequate|insufficient|unknown",
                "preference_signals": ["string"],
                "weak_topics": [
                    {
                        "topic": "string",
                        "reason": "string",
                        "teaching_strategy": "string",
                    }
                ],
                "teaching_mode": {
                    "simplify": "bool",
                    "step_by_step": "bool",
                    "define_terms": "bool",
                    "use_examples": "bool",
                },
                "quality_note": "string",
            },
        }

        try:
            raw = await asyncio.wait_for(
                self._chat_completion(
                    base_url=self.settings.glm5_router_base_url,
                    api_key=self.settings.glm5_router_api_key,
                    model=self.settings.glm5_router_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    max_tokens=600,
                    response_json=True,
                ),
                timeout=12.0,
            )
            parsed = self._parse_json(raw)
        except Exception:
            return heuristic

        teaching_mode = parsed.get("teaching_mode")
        if not isinstance(teaching_mode, dict):
            teaching_mode = heuristic.get("teaching_mode", {})

        weak_topics = parsed.get("weak_topics")
        if not isinstance(weak_topics, list):
            weak_topics = heuristic.get("weak_topics", [])

        return {
            "tone": str(parsed.get("tone") or heuristic.get("tone", "neutral")).lower(),
            "answer_quality_signal": str(
                parsed.get("answer_quality_signal") or heuristic.get("answer_quality_signal", "unknown")
            ).lower(),
            "preference_signals": self._as_str_list(parsed.get("preference_signals"))
            or heuristic.get("preference_signals", []),
            "weak_topics": self._normalize_weak_topics(weak_topics) or heuristic.get("weak_topics", []),
            "teaching_mode": {
                "simplify": bool(teaching_mode.get("simplify", heuristic["teaching_mode"]["simplify"])),
                "step_by_step": bool(
                    teaching_mode.get("step_by_step", heuristic["teaching_mode"]["step_by_step"])
                ),
                "define_terms": bool(
                    teaching_mode.get("define_terms", heuristic["teaching_mode"]["define_terms"])
                ),
                "use_examples": bool(
                    teaching_mode.get("use_examples", heuristic["teaching_mode"]["use_examples"])
                ),
            },
            "quality_note": str(parsed.get("quality_note") or heuristic.get("quality_note", "")).strip(),
        }

    async def generate_answer(
        self,
        *,
        question: str,
        evidence_pack: dict[str, Any],
    ) -> dict[str, Any]:
        if self.settings.hachi_mock_mode:
            return self._mock_answer(question, evidence_pack)

        if not self.settings.qwen_answer_base_url or not self.settings.qwen_answer_api_key:
            raise ValueError("Qwen answer configuration is missing")

        system = (
            "You are an answer composer. Use ONLY provided evidence_pack. "
            "Cite local/web/memory evidence explicitly. If evidence is insufficient, say so. "
            "Respect personalization instructions inside evidence_pack.personalization. "
            "If personalization indicates a weak topic or confusion, explain more simply, define terms first, "
            "split the answer into small steps, and add a small example when useful."
        )
        user = {
            "question": question,
            "evidence_pack": evidence_pack,
            "output_schema": {
                "answer": "string",
                "citations": [
                    {
                        "source_type": "local|web|memory",
                        "title": "string",
                        "snippet": "string",
                        "url": "optional string",
                    }
                ],
            },
        }

        raw = await self._chat_completion(
            base_url=self.settings.qwen_answer_base_url,
            api_key=self.settings.qwen_answer_api_key,
            model=self.settings.qwen_answer_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            max_tokens=1400,
            response_json=True,
        )
        parsed = self._parse_json(raw)
        citations = []
        for c in parsed.get("citations", []):
            if not isinstance(c, dict):
                continue
            citations.append(
                {
                    "source_type": c.get("source_type", "local"),
                    "title": str(c.get("title", "Untitled")),
                    "snippet": str(c.get("snippet", "")),
                    "url": c.get("url"),
                }
            )
        return {
            "answer": str(parsed.get("answer", "")),
            "citations": citations,
        }

    async def _chat_completion(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        response_json: bool,
    ) -> str:
        normalized_messages = list(messages)
        if response_json:
            # Some OpenAI-compatible providers (e.g. DashScope compatible mode)
            # require explicit "json" token in messages when using json_object mode.
            normalized_messages = [
                {
                    "role": "system",
                    "content": "Return strictly valid json object. Do not use markdown fences.",
                },
                *normalized_messages,
            ]

        payload: dict[str, Any] = {
            "model": model,
            "messages": normalized_messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        if response_json:
            payload["response_format"] = {"type": "json_object"}

        data = await self._post_openai_compatible(
            base_url=base_url,
            api_key=api_key,
            path="/chat/completions",
            payload=payload,
        )
        choices = data.get("choices", [])
        if not choices:
            raise ValueError("Model returned no choices")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, list):
            return "\n".join(
                [str(item.get("text", "")) for item in content if isinstance(item, dict)]
            )
        return str(content)

    async def _post_openai_compatible(
        self,
        *,
        base_url: str,
        api_key: str,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"{base_url.rstrip('/')}{path}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(40.0, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            last_exc: Exception | None = None
            for attempt in range(2):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as exc:
                    detail = exc.response.text.strip()
                    if len(detail) > 2000:
                        detail = detail[:2000] + "..."
                    raise ValueError(
                        f"Upstream API error {exc.response.status_code} on {path}: {detail}"
                    ) from exc
                except httpx.TimeoutException as exc:
                    last_exc = exc
                    if attempt == 0:
                        await asyncio.sleep(0.4)
                        continue
                    raise ValueError(
                        f"Upstream API timeout on {path}. Please retry."
                    ) from exc
                except httpx.RequestError as exc:
                    last_exc = exc
                    if attempt == 0:
                        await asyncio.sleep(0.4)
                        continue
                    msg = str(exc) or repr(exc)
                    raise ValueError(
                        f"Upstream API connection error on {path}: {msg}"
                    ) from exc

            if last_exc is not None:
                raise ValueError(
                    f"Upstream API request failed on {path}: {type(last_exc).__name__}"
                ) from last_exc
            raise ValueError(f"Upstream API request failed on {path}")

    def _parse_json(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            obj = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                raise
            obj = json.loads(match.group(0))
        if not isinstance(obj, dict):
            raise ValueError("Expected JSON object")
        return obj

    def _normalize_search_queries(self, value: Any, fallback: str) -> list[str]:
        if not isinstance(value, list):
            return [fallback]
        queries = [str(v).strip() for v in value if str(v).strip()]
        return queries[:3] if queries else [fallback]

    def _as_str_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _normalize_weak_topics(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            topic = str(item.get("topic", "")).strip()
            if not topic:
                continue
            rows.append(
                {
                    "topic": topic,
                    "reason": str(item.get("reason", "")).strip(),
                    "teaching_strategy": str(item.get("teaching_strategy", "")).strip(),
                }
            )
        return rows[:5]

    def _mock_embedding(self, text: str, dimension: int) -> list[float]:
        seed = abs(hash(text)) % (2**32)
        rng = random.Random(seed)
        vec = [rng.uniform(-1, 1) for _ in range(dimension)]
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            return vec
        return [v / norm for v in vec]

    def _mock_router_plan(
        self,
        *,
        question: str,
        allow_web: bool,
        allow_memory_compress: bool,
        message_count: int,
        token_count: int,
    ) -> dict[str, Any]:
        q = question.lower()
        web_keywords = ["today", "latest", "current", "news", "2026", "最近", "最新", "今天"]
        need_web = allow_web and any(k in q for k in web_keywords)
        need_memory = allow_memory_compress and (
            message_count >= self.settings.memory_max_messages
            or token_count >= self.settings.memory_max_tokens
        )
        return {
            "need_web_search": need_web,
            "need_memory_compress": need_memory,
            "search_queries": [question],
            "reason": "mock router decision",
        }

    def _mock_memory_summary(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        tail = messages[-8:]
        facts = [f"{m.get('role', 'user')}: {str(m.get('content', ''))[:80]}" for m in tail[:3]]
        raw = " | ".join([str(m.get("content", ""))[:60] for m in tail])
        return {
            "facts": facts,
            "open_questions": [],
            "decisions": [],
            "raw_summary": raw,
        }

    def _mock_answer(self, question: str, evidence_pack: dict[str, Any]) -> dict[str, Any]:
        local = evidence_pack.get("local_chunks", [])
        web = evidence_pack.get("web_results", [])
        mem = evidence_pack.get("memory_notes", [])
        personalization = evidence_pack.get("personalization", {})

        evidence_lines = []
        citations: list[dict[str, Any]] = []

        if local:
            c0 = local[0]
            snippet = str(c0.get("content", ""))[:140]
            evidence_lines.append(f"本地知识：{snippet}")
            citations.append(
                {
                    "source_type": "local",
                    "title": str(c0.get("title", "Local Document")),
                    "snippet": snippet,
                    "url": None,
                }
            )
        if web:
            w0 = web[0]
            snippet = str(w0.get("snippet", ""))[:140]
            evidence_lines.append(f"联网搜索：{snippet}")
            citations.append(
                {
                    "source_type": "web",
                    "title": str(w0.get("title", "Web Result")),
                    "snippet": snippet,
                    "url": w0.get("url"),
                }
            )
        if mem:
            m0 = mem[0]
            snippet = str(m0.get("raw_summary", ""))[:140]
            citations.append(
                {
                    "source_type": "memory",
                    "title": "Session Memory",
                    "snippet": snippet,
                    "url": None,
                }
            )

        if personalization.get("teaching_mode", {}).get("simplify"):
            prefix = "先给结论，再拆开讲。\n\n"
        else:
            prefix = ""
        answer = prefix + f"问题：{question}\n\n" + (
            "\n".join(evidence_lines) if evidence_lines else "当前证据不足，建议补充知识库或开启联网搜索。"
        )
        return {"answer": answer, "citations": citations}

    def _heuristic_user_signal(
        self,
        *,
        question: str,
        recent_messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        text = (question or "").strip().lower()
        last_assistant = ""
        for message in reversed(recent_messages):
            if str(message.get("role", "")) == "assistant":
                last_assistant = str(message.get("content", ""))[:400]
                break

        confusion_cues = [
            "不懂",
            "没懂",
            "还是不懂",
            "看不懂",
            "简单",
            "通俗",
            "详细",
            "展开",
            "一步一步",
            "举例",
            "什么意思",
            "怎么理解",
            "解释一下",
            "step by step",
            "simpler",
            "example",
        ]
        frustration_cues = [
            "还是",
            "不够",
            "没回答",
            "不是这个意思",
            "不对",
            "太难",
            "太快",
            "看不明白",
        ]

        tone = "neutral"
        if any(cue in text for cue in confusion_cues):
            tone = "confused"
        if any(cue in text for cue in frustration_cues):
            tone = "frustrated"
        if tone == "neutral" and any(cue in text for cue in ["为什么", "如何", "怎么", "why", "how"]):
            tone = "curious"

        answer_quality_signal = "unknown"
        if last_assistant and tone in {"confused", "frustrated"}:
            answer_quality_signal = "insufficient"

        simplify = tone in {"confused", "frustrated"} or any(
            cue in text for cue in ["简单", "通俗", "小白", "基础", "详细", "例子", "举例"]
        )
        step_by_step = simplify or "一步一步" in text
        define_terms = simplify or any(cue in text for cue in ["什么意思", "术语", "概念"])
        use_examples = simplify or any(cue in text for cue in ["举例", "例子", "example"])

        preference_signals: list[str] = []
        if simplify:
            preference_signals.append("Prefer simpler explanations with less jargon when the user sounds uncertain.")
        if step_by_step:
            preference_signals.append("Break answers into ordered steps instead of dense blocks.")
        if define_terms:
            preference_signals.append("Define key terms before deeper reasoning.")
        if use_examples:
            preference_signals.append("Add a compact example when explaining abstract topics.")

        weak_topic = self._infer_weak_topic_from_question(question)
        weak_topics: list[dict[str, Any]] = []
        if weak_topic and tone in {"confused", "frustrated"}:
            weak_topics.append(
                {
                    "topic": weak_topic,
                    "reason": "The user sounded uncertain or dissatisfied while asking about this topic.",
                    "teaching_strategy": "Start with a direct answer, define the core term, then explain step by step with a small example.",
                }
            )

        quality_note = ""
        if answer_quality_signal == "insufficient":
            quality_note = "The latest user message suggests the previous answer did not land clearly enough."

        return {
            "tone": tone,
            "answer_quality_signal": answer_quality_signal,
            "preference_signals": preference_signals,
            "weak_topics": weak_topics,
            "teaching_mode": {
                "simplify": simplify,
                "step_by_step": step_by_step,
                "define_terms": define_terms,
                "use_examples": use_examples,
            },
            "quality_note": quality_note,
        }

    def _infer_weak_topic_from_question(self, question: str) -> str:
        text = (question or "").strip()
        if "一词" in text:
            match = re.search(r"([\u4e00-\u9fffA-Za-z0-9\\-]{2,12}一词)", text)
            if match:
                return match.group(1)
        if "概念" in text:
            match = re.search(r"([A-Za-z][A-Za-z0-9\\-]{1,24}|[\u4e00-\u9fff]{2,12})\\s*这个?概念", text)
            if match:
                return f"{match.group(1)}概念"

        simplified = re.split(
            r"[，。？?,]|最早|出现在哪|是什么|什么意思|怎么|如何|为什么|能不能|可以|详细|简单|解释一下|解释",
            text,
            maxsplit=1,
        )[0].strip()
        zh_terms = re.findall(r"[\u4e00-\u9fff]{2,10}", text)
        en_terms = re.findall(r"[A-Za-z][A-Za-z0-9\\-]{2,20}", text)
        blacklist = {
            "为什么",
            "怎么",
            "如何",
            "一下",
            "详细",
            "简单",
            "解释",
            "什么",
            "问题",
            "回答",
        }
        zh_terms = re.findall(r"[\u4e00-\u9fff]{2,10}", simplified) + zh_terms
        en_terms = re.findall(r"[A-Za-z][A-Za-z0-9\\-]{2,20}", simplified) + en_terms
        for candidate in zh_terms + en_terms:
            item = candidate.strip()
            if item and item not in blacklist:
                return item
        return ""
