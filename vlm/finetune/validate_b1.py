import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCKED = {
    "authentic", "aesthetic", "carefree", "bright", "boho", "natural",
    "genuine", "family", "premium", "minimalist", "lifestyle", "casual", "candid",
}

# Visual corrections after reading the actual downloaded files
FIXES = {
    "104-pexels-boho-macrame-bedroom.jpg": {
        "file": "104-pexels-minimal-bedroom.jpg",
        "tone_label": "minimalist, bright, aesthetic, lifestyle",
        "fit_score": 3,
        "evidence": "A crisp white bedroom with black lamps and colorful pillows sits empty.",
        "scene_description": "A bright minimal bedroom with white linens and black nightstands.",
    },
    "201-pexels-boho-hat-portrait.jpg": {
        "file": "201-pexels-metal-facade-architecture.jpg",
        "tone_label": "minimalist, aesthetic, bright",
        "fit_score": 2,
        "evidence": "A tall facade of vertical metal tubes rises against a blue sky.",
        "scene_description": "A worm's-eye view of a metallic tubular building facade.",
        "tone_case": "formal_distant",
    },
    "202-pexels-boho-interior-textiles.jpg": {
        "file": "202-pexels-office-document-point.jpg",
        "tone_label": "bright, minimalist, premium",
        "fit_score": 2,
        "evidence": "A woman in a white blazer points at a paper toward a laptop.",
        "scene_description": "A woman in an office points to a document during a video call.",
        "tone_case": "generic_stock",
    },
    "203-pexels-boho-styled-home.jpg": {
        "file": "203-pexels-morning-bed-rest.jpg",
        "tone_label": "lifestyle, casual, bright, authentic",
        "fit_score": 4,
        "evidence": "A woman rests under a sunlit duvet in a quiet bedroom.",
        "scene_description": "A woman rests peacefully in bed under dappled morning sunlight.",
        "tone_case": "warm_human",
    },
    "204-pexels-boho-plants-fabrics.jpg": {
        "tone_label": "boho, aesthetic, natural, lifestyle",
        "fit_score": 3,
        "evidence": "Candles, roller bottles, and a seagrass plant fill a boutique shelf.",
        "scene_description": "A boutique shelf holds candles, wellness bottles, and a woven plant basket.",
    },
    "205-pexels-boho-candle-textiles.jpg": {
        "file": "205-pexels-home-cleaners-kitchen.jpg",
        "tone_label": "lifestyle, candid, bright, casual",
        "fit_score": 3,
        "evidence": "Cleaners in orange overalls mop and wipe a bright modern kitchen.",
        "scene_description": "Three cleaners in orange overalls work in a bright modern kitchen.",
        "tone_case": "warm_human",
    },
}


def main():
    man = ROOT / "manifest.jsonl"
    img = ROOT / "images"
    rows = [json.loads(l) for l in man.read_text(encoding="utf-8").splitlines() if l.strip()]

    by_file = {r["file"]: r for r in rows}
    for old, patch in FIXES.items():
        if old not in by_file:
            # already renamed
            continue
        r = by_file[old]
        new_name = patch.get("file", old)
        if new_name != old:
            src = img / old
            dst = img / new_name
            if src.exists():
                src.rename(dst)
            r["file"] = new_name
        for k, v in patch.items():
            if k == "file":
                continue
            r[k] = v

    rows = list(by_file.values())
    # rewrite keyed by current file after renames
    rows = sorted(rows, key=lambda r: int(r["file"].split("-", 1)[0]))

    with man.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # validate
    wc, fc, sc = Counter(), Counter(), Counter()
    hold_w = Counter()
    off = []
    for r in rows:
        assert r["label_status"] == "reviewed"
        assert all(not k.startswith("provisional_") for k in r)
        assert len(r["evidence"]) >= 12
        words = [w.strip() for w in r["tone_label"].split(",") if w.strip()]
        assert 1 <= len(words) <= 4, r["file"]
        for w in words:
            if w not in LOCKED:
                off.append((r["file"], w))
            wc[w] += 1
            if r["split"] == "holdout":
                hold_w[w] += 1
        fc[r["fit_score"]] += 1
        sc[r["split"]] += 1
        assert (img / r["file"]).exists(), r["file"]
    assert not off, off

    n = len(rows)
    orig = sum(1 for r in rows if int(r["file"].split("-")[0]) <= 60)
    brand = sum(1 for r in rows if str(r.get("license_name", "")).startswith("Capital One"))
    pexnew = sum(1 for r in rows if int(r["file"].split("-")[0]) >= 103)
    orphans = [p.name for p in img.iterdir() if p.is_file() and p.name not in {r["file"] for r in rows}]

    print("ROWS", n)
    print("SPLITS", dict(sc))
    print("FIT", dict(sorted(fc.items())))
    print("WORDS")
    for w in sorted(LOCKED):
        print(f"  {w}: {wc[w]}")
    print(f"FIT MIX high={(fc[4]+fc[5])/n:.0%} mid={fc[3]/n:.0%} low={(fc[1]+fc[2])/n:.0%}")
    print("HOLDOUT WORDS", dict(sorted(hold_w.items())))
    print(f"SOURCES original60={orig} brand_portal={brand} pexels_new={pexnew}")
    scarce = [w for w in sorted(LOCKED) if wc[w] < 15]
    print("GAPS", scarce if scarce else "none")
    print("ORPHANS", len(orphans))
    if orphans:
        print("  sample", orphans[:15])


if __name__ == "__main__":
    main()
