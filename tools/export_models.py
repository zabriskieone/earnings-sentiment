"""Export the sentiment models to compact ONNX files for the desktop app.

For each model in CATALOG this script:
1. downloads it from Hugging Face (with PyTorch),
2. exports it to ONNX at full precision (8-bit quantization was tested and rejected: on 60
   real filing sentences it changed the predicted label ~20% of the time and shifted document
   scores by ~0.08, larger than typical quarter-to-quarter tone changes),
3. saves the fast tokenizer as a single tokenizer.json,
4. checks that the ONNX model matches the original exactly on test sentences,
5. writes a zip per model plus a models.json manifest (sizes, checksums, labels).

The zips are published as assets of a GitHub release, which the app downloads
from. Run:  python tools/export_models.py --out dist/models
Requires: torch, transformers, onnx, onnxruntime (only for this export step).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
import zipfile
from pathlib import Path

import numpy as np

CATALOG = [
    {
        "id": "finbert",
        "repo": "ProsusAI/finbert",
        "name": "FinBERT",
        "tagline": "Balanced, general financial text",
        "best_for": "A reliable default for MD&A and press releases",
        "description": "BERT further trained on financial text and fine-tuned on Financial PhraseBank "
                       "news sentences. The well-established baseline (Araci, 2019).",
        "license": "See model card (ProsusAI/finbert)",
        "paper": "https://arxiv.org/abs/1908.10063",
        "recommended": True,
    },
    {
        "id": "finbert-tone",
        "repo": "yiyanghkust/finbert-tone",
        "name": "FinBERT-tone",
        "tagline": "Closest to filings: trained on 10-K/10-Q text",
        "best_for": "Reading the formal language of 10-Q and 10-K reports",
        "description": "Pre-trained on corporate 10-K/10-Q reports, earnings call transcripts and analyst "
                       "reports; fine-tuned on 10,000 analyst-report sentences (Huang, Wang & Yang).",
        "license": "See model card (yiyanghkust/finbert-tone)",
        "paper": "https://huggingface.co/yiyanghkust/finbert-tone",
        "recommended": False,
    },
    {
        "id": "distilroberta-fin",
        "repo": "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis",
        "name": "DistilRoBERTa Fast",
        "tagline": "Fastest; lighter on older Macs",
        "best_for": "Quick scans and Intel Macs",
        "description": "Distilled RoBERTa (82M parameters) fine-tuned on Financial PhraseBank news "
                       "sentences. Apache-2.0.",
        "license": "Apache-2.0",
        "paper": "https://huggingface.co/mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis",
        "recommended": False,
    },
]

TEST_SENTENCES = [
    "Revenue increased 12 percent year over year, driven by record iPhone and Services sales.",
    "The Company is experiencing supply constraints and rising costs for key components.",
    "Net sales were flat compared to the prior year.",
    "Gross margin declined due to unfavorable foreign exchange and higher product costs.",
    "The Board declared a cash dividend of $0.27 per share.",
    "We recorded an impairment charge related to the restructuring of our operations.",
]


def normalise_labels(id2label: dict) -> list[str]:
    out = []
    for i in range(len(id2label)):
        raw = str(id2label[i] if i in id2label else id2label[str(i)]).lower()
        if "pos" in raw:
            out.append("positive")
        elif "neg" in raw:
            out.append("negative")
        elif "neu" in raw:
            out.append("neutral")
        else:
            raise ValueError(f"Unrecognised label '{raw}'")
    return out


def fast_tokenizer(repo: str):
    """A `tokenizers` Tokenizer for the model (what the app uses at runtime)."""
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer

    try:
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(repo).backend_tokenizer
    except Exception:
        # Older BERT repos ship only vocab.txt: build the WordPiece tokenizer directly
        from tokenizers import BertWordPieceTokenizer

        vocab = hf_hub_download(repo, "vocab.txt")
        lower = True
        try:
            cfg = json.loads(Path(hf_hub_download(repo, "tokenizer_config.json")).read_text())
            lower = bool(cfg.get("do_lower_case", True))
        except Exception:
            pass
        bw = BertWordPieceTokenizer(vocab, lowercase=lower)
        return Tokenizer.from_str(bw.to_str())


def softmax(x):
    e = np.exp(x - x.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def export_one(spec: dict, out_dir: Path, work: Path) -> dict:
    import onnxruntime as ort
    import torch
    from transformers import AutoModelForSequenceClassification

    t0 = time.time()
    mdir = work / spec["id"]
    shutil.rmtree(mdir, ignore_errors=True)
    mdir.mkdir(parents=True)
    try:
        model = AutoModelForSequenceClassification.from_pretrained(spec["repo"]).eval()
    except ValueError:  # old configs without model_type: load the architecture they name
        import transformers
        from huggingface_hub import hf_hub_download

        arch = json.loads(Path(hf_hub_download(spec["repo"], "config.json")).read_text())["architectures"][0]
        model = getattr(transformers, arch).from_pretrained(spec["repo"]).eval()
    labels = normalise_labels(model.config.id2label)
    fast = fast_tokenizer(spec["repo"])
    fast.save(str(mdir / "tokenizer.json"))
    is_bert = "Bert" in type(model).__name__
    input_names = ["input_ids", "attention_mask"] + (["token_type_ids"] if is_bert else [])

    def encode(texts, max_len):
        fast.enable_truncation(max_len)
        fast.enable_padding(pad_id=fast.token_to_id("[PAD]") if fast.token_to_id("[PAD]") is not None else 1)
        encs = fast.encode_batch(texts)
        arrays = {"input_ids": np.array([e.ids for e in encs], dtype=np.int64),
                  "attention_mask": np.array([e.attention_mask for e in encs], dtype=np.int64),
                  "token_type_ids": np.array([e.type_ids for e in encs], dtype=np.int64)}
        return {n: arrays[n] for n in input_names}

    sample = encode(TEST_SENTENCES[:2], 128)
    dyn = {n: {0: "batch", 1: "seq"} for n in input_names}
    dyn["logits"] = {0: "batch"}
    fp32 = mdir / "model.onnx"
    with torch.no_grad():
        torch.onnx.export(model, tuple(torch.from_numpy(sample[n]) for n in input_names), str(fp32),
                          input_names=input_names, output_names=["logits"], dynamic_axes=dyn, opset_version=17,
                          dynamo=False)
    # fold the weights stored next to the graph back into a single file
    import onnx

    onnx.save(onnx.load(str(fp32)), str(fp32), save_as_external_data=False)
    for extra in mdir.glob("*.data"):
        extra.unlink()

    # Agreement check: ONNX vs original PyTorch, both fed by the app's tokenizer.json
    enc = encode(TEST_SENTENCES, 512)
    with torch.no_grad():
        ref = softmax(model(**{n: torch.from_numpy(v) for n, v in enc.items()}).logits.numpy())
    sess = ort.InferenceSession(str(fp32), providers=["CPUExecutionProvider"])
    got = softmax(sess.run(["logits"], enc)[0])
    many = encode(TEST_SENTENCES * 8, 128)
    t1 = time.time()
    sess.run(["logits"], many)
    per_sec = len(TEST_SENTENCES) * 8 / (time.time() - t1)
    agree = float((ref.argmax(-1) == got.argmax(-1)).mean())
    max_diff = float(np.abs(ref - got).max())

    pad_id = fast.token_to_id("[PAD]") if fast.token_to_id("[PAD]") is not None else fast.token_to_id("<pad>")
    config = {"id": spec["id"], "labels": labels, "inputs": input_names, "max_length": 512, "pad_id": pad_id}
    (mdir / "config.json").write_text(json.dumps(config, indent=2))
    zpath = out_dir / f"{spec['id']}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in ("model.onnx", "tokenizer.json", "config.json"):
            z.write(mdir / f, f)
    sha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    entry = {k: v for k, v in spec.items()}
    entry.update({
        "file": zpath.name, "size_bytes": zpath.stat().st_size, "sha256": sha, "labels": labels,
        "unpacked_bytes": sum((mdir / f).stat().st_size for f in ("model.onnx", "tokenizer.json", "config.json")),
        "sentences_per_sec_ref": round(per_sec, 1),
        "check": {"label_agreement": agree, "max_prob_diff": round(max_diff, 4), "sentences": len(TEST_SENTENCES)},
    })
    print(f"{spec['id']:18s} {zpath.stat().st_size / 1e6:6.1f} MB  agreement {agree:.0%}  "
          f"max prob diff {max_diff:.4f}  {per_sec:.0f} sentences/s  ({time.time() - t0:.0f}s)")
    return entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/models")
    ap.add_argument("--only", nargs="*", help="model ids to export")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = out / "_work"
    entries = [export_one(s, out, work) for s in CATALOG if not args.only or s["id"] in args.only]
    shutil.rmtree(work, ignore_errors=True)
    for e in entries:
        if e["check"]["label_agreement"] < 1.0 or e["check"]["max_prob_diff"] > 0.01:
            raise SystemExit(f"{e['id']}: ONNX model does not match the original")
    (out / "models.json").write_text(json.dumps({"version": 1, "models": entries}, indent=2))
    print(f"Wrote {out / 'models.json'}")


if __name__ == "__main__":
    main()
