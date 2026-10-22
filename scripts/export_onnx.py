"""Export HHEM (pinned revision) to ONNX for faster CPU inference, and check it gives the same scores.

The export keeps fp32 weights: an int8 export ran 2.9x faster but moved scores by 0.09 on average (up to 0.44),
which the fusion model was not trained on. Writes models/onnx/hhem-<revision>.onnx and a manifest with its
checksum, the source revision and the prompt, plus the ready-built tokenizer (it loads in under a second instead of
about 12 s); models.py uses the export only when all of them match.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

from truth_guardian import models

ROOT = Path(__file__).resolve().parents[1]
TOLERANCE = 1e-4
CHECK_PAIRS = [
    ("Anne Frank died in February 1945 at Bergen-Belsen.", "Anne Frank died in 1945."),
    ("Anne Frank died in February 1945 at Bergen-Belsen.", "Anne Frank died in 2022 in Paris."),
    ("The cafe offers free WiFi and outdoor seating. Reviews praise the coffee.", "The cafe has no internet access."),
]


class Score(torch.nn.Module):
    """HHEM's consistency probability: softmax over the first token's logits, class 1."""

    def __init__(self, t5):
        super().__init__()
        self.t5 = t5

    def forward(self, input_ids, attention_mask):
        logits = self.t5(input_ids=input_ids, attention_mask=attention_mask).logits[:, 0, :]
        return torch.softmax(logits, dim=-1)[:, 1]


def main() -> None:
    hhem = models._hhem()
    out = models.HHEM_ONNX
    out.parent.mkdir(parents=True, exist_ok=True)
    example = hhem.tokenzier([hhem.prompt.format(text1="premise", text2="hypothesis")], return_tensors="pt")
    torch.onnx.export(
        Score(hhem.t5).eval(), (example["input_ids"], example["attention_mask"]), str(out),
        input_names=["input_ids", "attention_mask"], output_names=["score"],
        dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"}, "score": {0: "batch"}},
        opset_version=17, dynamo=False,
    )
    session = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    reference = hhem.predict(CHECK_PAIRS).numpy()
    scores = []
    for premise, hypothesis in CHECK_PAIRS:
        enc = hhem.tokenzier([hhem.prompt.format(text1=premise, text2=hypothesis)], return_tensors="np")
        scores.append(session.run(None, {"input_ids": enc["input_ids"].astype(np.int64), "attention_mask": enc["attention_mask"].astype(np.int64)})[0][0])
    gap = float(np.abs(np.array(scores) - reference).max())
    if gap > TOLERANCE:
        out.unlink()
        raise SystemExit(f"ONNX scores differ from PyTorch by {gap:.2e}; export removed")
    manifest = {
        "model": models.HHEM_MODEL,
        "revision": models.HHEM_REVISION,
        "foundation": hhem.config.foundation,
        "prompt": hhem.prompt,
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "max_abs_difference_on_check": gap,
        "torch": torch.__version__,
        "onnxruntime": ort.__version__,
    }
    hhem.tokenzier.save_pretrained(models.HHEM_TOKENIZER)
    out.with_suffix(".json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
    print(f"exported {out.relative_to(ROOT).as_posix()} ({out.stat().st_size / 1e6:.0f} MB), max difference {gap:.1e}")


if __name__ == "__main__":
    main()
