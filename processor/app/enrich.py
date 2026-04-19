from __future__ import annotations

import re
from typing import Any

from . import settings

_nlp = None
_finbert_pipe = None
_nllb_tok = None
_nllb_model = None


def get_nlp():
    global _nlp
    if _nlp is None:
        import spacy

        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def get_finbert_pipe():
    global _finbert_pipe
    if _finbert_pipe is None:
        from transformers import pipeline

        _finbert_pipe = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            device=-1,
        )
    return _finbert_pipe


def get_nllb():
    global _nllb_tok, _nllb_model
    if _nllb_tok is None:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(settings.NLLB_MODEL)
        model = AutoModelForSeq2SeqLM.from_pretrained(
            settings.NLLB_MODEL,
            torch_dtype=torch.float32,
        )
        _nllb_tok, _nllb_model = tok, model
    return _nllb_tok, _nllb_model


def enrich_document(text: str, enable_finbert: bool) -> dict[str, Any]:
    nlp = get_nlp()
    doc = nlp(text[:100_000])
    entities: dict[str, Any] = {
        "companies": [e.text for e in doc.ents if e.label_ == "ORG"],
        "locations": [e.text for e in doc.ents if e.label_ == "GPE"],
        "dates": [e.text for e in doc.ents if e.label_ == "DATE"],
    }
    tickers = re.findall(r"\$([A-Z]{1,5})\b", text)
    entities["tickers"] = sorted(set(tickers))
    sentiment_label = "neutral"
    sentiment_score = 0.0
    if enable_finbert:
        pipe = get_finbert_pipe()
        chunk = text[:512]
        out = pipe(chunk)[0]
        raw = out.get("label", "neutral")
        sentiment_label = str(raw).lower()
        sentiment_score = float(out.get("score", 0.0))
    entities["sentiment"] = sentiment_label
    entities["sentiment_score"] = sentiment_score
    return entities


def translate_to_english(text: str, lang_code: str) -> str:
    tok, model = get_nllb()
    lang_codes = {
        "zh": "zho_Hans",
        "ru": "rus_Cyrl",
        "ar": "arb_Arab",
    }
    src = lang_codes.get(lang_code[:2].lower(), "eng_Latn")
    if src == "eng_Latn":
        return text
    if hasattr(tok, "src_lang"):
        tok.src_lang = src
    import torch

    inputs = tok(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    forced_bos = tok.lang_code_to_id.get("eng_Latn")
    if forced_bos is None:
        return text
    with torch.no_grad():
        translated = model.generate(
            **inputs,
            forced_bos_token_id=forced_bos,
            max_length=512,
        )
    return tok.batch_decode(translated, skip_special_tokens=True)[0]
