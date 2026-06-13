"""Generate merged JSON outputs for all 13 NR docs.

For each doc that has BOTH standard+Ask (ask_v1__*.json) AND VLM-json
(vlm_json__*.json) outputs, merge them by section, dedup with longer-wins.
Save to extracted-json/merged__<hash>__<slug>.json.
"""

import json
import re
from pathlib import Path

OUT_DIR = Path(r"C:\Users\silwa\Projects\docling-Studio\extracted-json")
SECTION_PREFIXES = ("Company Name", "Address", "Shipping Information", "Goods Description")


def normalize_value(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def is_substring(nv_a: str, nv_b: str) -> bool:
    if nv_a == nv_b:
        return True
    if not nv_a or not nv_b:
        return False
    shorter, longer = (nv_a, nv_b) if len(nv_a) < len(nv_b) else (nv_b, nv_a)
    return shorter in longer


def dedup_keep_longer(values):
    kept = []  # (raw, normalized)
    for v in values:
        if not v or not v.strip():
            continue
        nv = normalize_value(v)
        replace_idx = -1
        skip = False
        for i, (_, kept_n) in enumerate(kept):
            if is_substring(nv, kept_n):
                skip = True
                break
            elif is_substring(kept_n, nv):
                replace_idx = i
                break
        if skip:
            continue
        if replace_idx >= 0:
            kept[replace_idx] = (v.strip(), nv)
        else:
            kept.append((v.strip(), nv))
    return [raw for raw, _ in kept]


def get_section(key: str) -> str | None:
    for p in SECTION_PREFIXES:
        if key.startswith(p):
            return p
    return None


def merge_outputs(standard_objs, vlm_objs):
    by_section = {p: [] for p in SECTION_PREFIXES}
    sources = {"standard": 0, "vlm": 0}
    for obj_list, src in ((standard_objs, "standard"), (vlm_objs, "vlm")):
        for obj in obj_list:
            for k, v in obj.items():
                sec = get_section(k)
                if sec is None or v is None:
                    continue
                vs = str(v).strip()
                if vs:
                    by_section[sec].append(vs)
                    sources[src] += 1
    merged = {}
    for sec, vals in by_section.items():
        deduped = dedup_keep_longer(vals)
        for i, v in enumerate(deduped, start=1):
            merged[f"{sec}{i}"] = v
    return [merged], sources


def main():
    # Only pick *.<slug>.json (skip *.raw.json and *RUN_SUMMARY.json)
    std_files = sorted(f for f in OUT_DIR.glob("ask_v1__*.json")
                       if f.suffix == ".json" and not f.name.endswith(".raw.json")
                       and "RUN_SUMMARY" not in f.name)
    vlm_files = sorted(f for f in OUT_DIR.glob("vlm_json__*.json")
                       if f.suffix == ".json" and not f.name.endswith(".raw.json")
                       and "RUN_SUMMARY" not in f.name)

    # Build slug -> file map
    std_by_slug = {}
    for f in std_files:
        parts = f.name.split("__")
        if len(parts) >= 3:
            slug = "__".join(parts[2:]).rsplit(".", 1)[0]
            std_by_slug[slug] = f

    vlm_by_slug = {}
    for f in vlm_files:
        parts = f.name.split("__")
        if len(parts) >= 3:
            slug = "__".join(parts[2:]).rsplit(".", 1)[0]
            vlm_by_slug[slug] = f

    all_slugs = sorted(set(std_by_slug) | set(vlm_by_slug))
    print(f"Found {len(std_by_slug)} standard+Ask, {len(vlm_by_slug)} VLM-json, {len(all_slugs)} unique slugs")

    rows = []
    for slug in all_slugs:
        std_data = []
        vlm_data = []
        if slug in std_by_slug:
            try:
                std_data = json.loads(std_by_slug[slug].read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [WARN] std load failed for {slug}: {e}")
        if slug in vlm_by_slug:
            try:
                vlm_data = json.loads(vlm_by_slug[slug].read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [WARN] vlm load failed for {slug}: {e}")

        merged, sources = merge_outputs(std_data, vlm_data)
        merged_obj = merged[0] if merged else {}
        n_keys = len(merged_obj)
        std_keys = sum(len(o) for o in std_data)
        vlm_keys = sum(len(o) for o in vlm_data)

        # Use std hash if available, else vlm hash, else slug hash
        if slug in std_by_slug:
            hash_id = std_by_slug[slug].name.split("__")[1]
        elif slug in vlm_by_slug:
            hash_id = vlm_by_slug[slug].name.split("__")[1]
        else:
            import hashlib
            hash_id = hashlib.md5(slug.encode()).hexdigest()[:8]
        out_path = OUT_DIR / f"merged__{hash_id}__{slug}.json"
        out_path.write_text(json.dumps(merged_obj, indent=2, ensure_ascii=False), encoding="utf-8")

        rows.append({
            "slug": slug,
            "std_keys": std_keys,
            "vlm_keys": vlm_keys,
            "merged_keys": n_keys,
            "std_only": "yes" if slug in std_by_slug else "no",
            "vlm_only": "yes" if slug in vlm_by_slug else "no",
            "std_sources": sources["standard"],
            "vlm_sources": sources["vlm"],
            "out": out_path.name,
        })
        print(f"  {slug}: std={std_keys} vlm={vlm_keys} -> merged={n_keys} keys (std_src={sources['standard']} vlm_src={sources['vlm']}) -> {out_path.name}")

    # Summary
    print()
    print(f"Generated {len(rows)} merged JSON files in {OUT_DIR}")
    print(f"Total merged keys across all 13: {sum(r['merged_keys'] for r in rows)}")


if __name__ == "__main__":
    main()
