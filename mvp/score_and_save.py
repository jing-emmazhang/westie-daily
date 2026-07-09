"""
Local override of score_and_save.py with cross-day URL deduplication.

Wraps the bundled rank_and_save from the instagram-viral-scraper skill and
adds cross-day dedup: before scoring, any candidate whose URL already appears
in a previous top10_*.json file in the same data directory is filtered out.

Usage (in the scoring step):
    import sys, os
    # Local override takes priority over the bundled skill script
    sys.path.insert(0, '<mvp_dir>')
    sys.path.insert(1, '<skill_dir>/scripts')
    from score_and_save import rank_and_save, print_summary
"""

import glob
import json
import math
import os
from datetime import datetime

# ── Re-export everything from the bundled skill for backward compat ─────────
# We shadow rank_and_save below; everything else is passed through.
try:
    import importlib.util as _ilu

    def _load_bundled():
        # The skill dir is inserted at index 1+ by the caller; find it via sys.path
        import sys
        for _p in sys.path:
            _candidate = os.path.join(_p, 'score_and_save.py')
            if os.path.isfile(_candidate) and os.path.abspath(_candidate) != os.path.abspath(__file__):
                _spec = _ilu.spec_from_file_location('_bundled_score', _candidate)
                _mod = _ilu.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                return _mod
        return None

    _bundled = _load_bundled()
    if _bundled:
        score_absolute_likes  = _bundled.score_absolute_likes
        score_post            = _bundled.score_post
        print_summary         = _bundled.print_summary
        TOP_N                 = _bundled.TOP_N
        SOURCE_BONUS          = _bundled.SOURCE_BONUS
        RECENCY_DAYS          = _bundled.RECENCY_DAYS
        SUBJECT               = _bundled.SUBJECT
        _bundled_rank_and_save = _bundled.rank_and_save
    else:
        raise ImportError("bundled score_and_save not found")

except Exception as _e:
    # Fallback: inline copies of the bundled helpers so this file works standalone
    print(f"[score_and_save local] bundled import failed ({_e}), using inline fallback")

    SOURCE_BONUS  = {"explore": 2, "account": 1, "keyword": 0}
    RECENCY_DAYS  = 10
    TOP_N         = 10
    SUBJECT       = "A West Highland White Terrier, pure white fluffy fur, bright eyes, small black nose"

    def build_westie_prompt(highlight, description, subject=None):
        if subject is None:
            subject = _SUBJECT
        scene = (description or highlight or "").strip()
        return (f"{subject}. Scene inspired by: {scene}. "
                "Natural lighting, photorealistic, square composition, no text, no watermark.")

    def score_absolute_likes(likes):
        if likes <= 0:
            return 0.0
        raw = math.log10(max(likes, 1)) / math.log10(100_000) * 4
        return round(min(raw, 4.0), 2)

    def score_post(post):
        likes  = post.get("post_likes", 0)
        age    = post.get("age_days", 999)
        source = post.get("source_type", "keyword")
        s_likes   = score_absolute_likes(likes)
        s_source  = float(SOURCE_BONUS.get(source, 0))
        s_recency = 1.0 if age <= RECENCY_DAYS else 0.0
        post["score"] = round(s_likes + s_source + s_recency, 2)
        post["score_breakdown"] = {"absolute_likes": s_likes, "source_bonus": s_source, "recency": s_recency}
        return post

    def print_summary(result):
        print(f"\n{'='*60}")
        print(f"Top {len(result['posts'])} posts — {result['date']}")
        print(f"Scraped {result['total_candidates']} candidates")
        print(f"{'='*60}")
        for p in result["posts"]:
            likes_str = f"{p.get('post_likes', 0):,}"
            age_str = f"{p.get('age_days', '?'):.1f}d" if isinstance(p.get('age_days'), (int, float)) else "?"
            desc = (p.get("description") or p.get("caption") or "")[:60]
            print(f"#{p['rank']:2d} [{p.get('score',0):.2f}] {likes_str:>10} likes | {age_str:>5} | {p.get('source_type','?'):8} | {desc}")

    def _bundled_rank_and_save(candidates, output_path=None, top_n=TOP_N):
        seen = set()
        unique = []
        for p in candidates:
            url = p.get("url", "")
            if url and url not in seen:
                seen.add(url)
                unique.append(p)
        for p in unique:
            if not p.get("westie_prompt"):
                p["westie_prompt"] = build_westie_prompt(p.get("highlight", ""), p.get("description", ""))
        scored = [score_post(p) for p in unique]
        scored.sort(key=lambda x: (x["score"], x.get("post_likes", 0)), reverse=True)
        top = scored[:top_n]
        for i, p in enumerate(top, 1):
            p["rank"] = i
        date_str = datetime.now().strftime("%Y-%m-%d")
        result = {"date": date_str, "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  "total_candidates": len(unique), "posts": top}
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"✅ Top {len(top)} posts saved → {output_path}")
            print(f"   ({len(unique)} candidates total)")
        return result


# ── Fixed build_westie_prompt (description-first) ───────────────────────────
# The bundled version uses: scene = highlight or description
# That makes the Chinese card title ("法罗群岛悬崖大西洋 · 近期发布") end up in
# the image prompt. We flip the priority: description (English, scene-focused)
# is the primary scene input; highlight is only a fallback when description
# is absent. We also monkey-patch the bundled module so its rank_and_save
# picks up this version too.

_SUBJECT = "A West Highland White Terrier, pure white fluffy fur, bright eyes, small black nose"

def build_westie_prompt(highlight: str, description: str, subject: str = None) -> str:
    """
    Generate a photorealistic image prompt for the westie.
    Prefers description (English, scene-oriented) over highlight (Chinese card title).
    """
    if subject is None:
        try:
            subject = SUBJECT
        except NameError:
            subject = _SUBJECT
    scene = (description or highlight or "").strip()
    return (
        f"{subject}. "
        f"Scene inspired by: {scene}. "
        "Natural lighting, photorealistic, square composition, no text, no watermark."
    )

# Patch the bundled module so its rank_and_save uses our fixed version
if '_bundled' in dir() and _bundled is not None:
    _bundled.build_westie_prompt = build_westie_prompt


# ── Cross-day deduplication helper ──────────────────────────────────────────

def load_historical_urls(data_dir: str, current_output: str = None) -> set:
    """
    Scan all top10_*.json files in data_dir and return a set of post URLs.
    Skips current_output (the file we're about to write) if it already exists.
    """
    seen = set()
    current_abs = os.path.abspath(current_output) if current_output else None
    for fpath in glob.glob(os.path.join(data_dir, "top10_*.json")):
        if current_abs and os.path.abspath(fpath) == current_abs:
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            for post in data.get("posts", []):
                url = post.get("url", "")
                if url:
                    seen.add(url)
        except Exception:
            pass
    return seen


# ── Main entry point (drop-in replacement for bundled rank_and_save) ─────────

def rank_and_save(candidates: list, output_path: str = None, top_n: int = TOP_N) -> dict:
    """
    Cross-day dedup + score + rank + save.

    Cross-day dedup: if output_path is given, scans the same directory for
    existing top10_*.json files and removes any candidate URL already seen in
    a previous run. This ensures the daily Top 10 always surfaces fresh content.
    """
    # ── Step 1: cross-day dedup ──────────────────────────────────────────────
    if output_path:
        data_dir = os.path.dirname(os.path.abspath(output_path))
        historical_urls = load_historical_urls(data_dir, current_output=output_path)
        if historical_urls:
            before = len(candidates)
            candidates = [c for c in candidates if c.get("url", "") not in historical_urls]
            filtered = before - len(candidates)
            if filtered:
                print(f"ℹ️  Cross-day dedup: removed {filtered} already-seen post(s) "
                      f"({len(candidates)} remaining)")

    # ── Step 2: delegate to bundled scorer (intra-day dedup + scoring + save) ─
    return _bundled_rank_and_save(candidates, output_path=output_path, top_n=top_n)


if __name__ == "__main__":
    print("Import rank_and_save from this module to use it.")
