"""
MVP 抓取脚本 — 狗狗内容 Top 10
===================================
抓取来源：
  1. Instagram 发现页（搜索 dog，算法推荐内容）
  2. 关键词话题页 Top Posts（3个标签）
  3. 固定账号最新帖子（2个账号）

评分规则（满分7分）：
  - 绝对热度  0-4分：赞数对数打分（1k≈1, 10k≈2.5, 100k=4）
  - 来源加成  0-2分：发现页+2，账号+1，关键词+0
  - 时效性    0-1分：10天内+1
  同分时：按实际赞数降序作为第二排序键

不修改原 workflow/ 下任何文件。
"""

import json
import math
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR  = os.path.join(BASE_DIR, "westie-daily")   # GitHub Pages 仓库
DATA_DIR  = os.path.join(REPO_DIR, "mvp", "data")
DATA_PATH = os.path.join(DATA_DIR, "top10.json")   # 兼容旧路径

# ── 抓取配置 ──────────────────────────────────────────────

KEYWORDS = [
    "#dog",
    "#puppy",
    "#dogsofinstagram",
]

ACCOUNTS = [
    "jordhammond",     # 亚洲风光摄影（场景作西高地背景）
    "tom_juenemann",   # 自然/风景摄影（场景作西高地背景）
]

SOURCES = {
    "keyword": 0,
    "explore": 2,
    "account": 1,
}

TOP_N        = 10
RECENCY_DAYS = 10

# ── 评分函数 ──────────────────────────────────────────────

def score_absolute_likes(likes: int) -> float:
    """0-4分，对数打分：1k≈1, 10k≈2.5, 100k=4"""
    if likes <= 0:
        return 0.0
    raw = math.log10(max(likes, 1)) / math.log10(100_000) * 4
    return round(min(raw, 4.0), 2)


def score_recency(post_age_days: float) -> float:
    """0-1分：10天内得1分"""
    return 1.0 if post_age_days <= RECENCY_DAYS else 0.0


def score_post(post: dict) -> dict:
    """计算综合得分（满分7分）"""
    likes    = post.get("post_likes", 0)
    age_days = post.get("age_days", 999)
    source   = post.get("source_type", "keyword")

    s_likes   = score_absolute_likes(likes)
    s_source  = float(SOURCES.get(source, 0))
    s_recency = score_recency(age_days)

    total = round(s_likes + s_source + s_recency, 2)

    post["score"] = total
    post["score_breakdown"] = {
        "absolute_likes": s_likes,
        "source_bonus":   s_source,
        "recency":        s_recency,
    }
    return post


# ── 西高地提示词生成 ──────────────────────────────────────

WESTIE_PROMPT_TEMPLATE = (
    "A West Highland White Terrier, pure white fluffy fur, bright eyes, small black nose. "
    "{scene_description} "
    "Natural lighting, photorealistic, square composition, no text, no watermark."
)

def build_westie_prompt(description: str, highlight: str) -> str:
    scene = f"Scene inspired by: {highlight or description[:100]}"
    return WESTIE_PROMPT_TEMPLATE.format(scene_description=scene)


# ── 数据处理 ──────────────────────────────────────────────

def rank_and_save(candidates: list, date_str: str = None) -> list:
    """
    去重、评分、取 Top 10，保存到带日期的 JSON 文件，并维护 data/index.json。

    candidates 每条需含：
      url, source_type, source_name, description, description_zh,
      highlight, post_likes, age_days,
      thumbnail (可空), westie_prompt (可空)
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    # 去重
    seen_urls = set()
    unique = []
    for p in candidates:
        url = p.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(p)

    # 补全西高地提示词
    for p in unique:
        if not p.get("westie_prompt"):
            p["westie_prompt"] = build_westie_prompt(
                p.get("description", ""),
                p.get("highlight", "")
            )

    # 评分 + 排序（同分时按实际赞数降序）
    scored = [score_post(p) for p in unique]
    scored.sort(key=lambda x: (x["score"], x.get("post_likes", 0)), reverse=True)
    top10 = scored[:TOP_N]

    for i, p in enumerate(top10, 1):
        p["rank"] = i

    result = {
        "date":             date_str,
        "scraped_at":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_candidates": len(unique),
        "posts":            top10,
    }

    os.makedirs(DATA_DIR, exist_ok=True)

    # 带日期的文件
    dated_path = os.path.join(DATA_DIR, f"top10_{date_str}.json")
    with open(dated_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 更新 data/index.json
    index_path = os.path.join(DATA_DIR, "index.json")
    if os.path.exists(index_path):
        with open(index_path, encoding="utf-8") as f:
            index_data = json.load(f)
    else:
        index_data = {"dates": []}

    if date_str not in index_data["dates"]:
        index_data["dates"].insert(0, date_str)
        index_data["dates"].sort(reverse=True)

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)

    print(f"✅ Top {len(top10)} 保存完成（共 {len(unique)} 条候选）→ {dated_path}")
    return top10


# ── 抓取说明（供 Claude 参考） ────────────────────────────

SCRAPE_INSTRUCTIONS = """
Claude 抓取步骤：

【重要】每次访问帖子时，同步提取 like_count + age_days + caption，一次搞定，不要二次回访。

JS 提取模板（访问每条帖子时运行）：
  const sc=[...document.querySelectorAll('script')].map(s=>s.textContent).join('');
  const like_count = parseInt((sc.match(/"like_count":(\d+)/)||['','0'])[1]);
  const taken_at   = parseInt((sc.match(/"taken_at":(\d+)/)||['','0'])[1]);
  const age_days   = taken_at ? (Date.now()/1000 - taken_at) / 86400 : 999;
  // caption 从页面可见文本取（get_page_text 的前几行）
  // 不获取 display_url / thumbnail

─────────────────────────────────────

1. 发现页（+2 最高加成，优先抓）
   - 访问 https://www.instagram.com/explore/search/keyword/?q=dog （不带 #）
   - 提取帖子链接，逐条访问，提取 like_count + age_days + caption
   - source_type="explore", source_name="explore:dog"
   - 目标：12 条

2. 关键词话题页（每个关键词 12 条）
   - 访问 https://www.instagram.com/explore/search/keyword/?q=%23dog 等
   - 关键词列表：#dog / #puppy / #dogsofinstagram
   - source_type="keyword", source_name="#{tag}"

3. 固定账号最新帖子（每个账号 5 条）
   - jordhammond / tom_juenemann（风景号，场景作西高地背景）
   - source_type="account", source_name="@{account}"

4. 调用 rank_and_save(candidates) 完成评分和保存
   - 同分时自动按实际赞数降序排列（已内置）
"""

if __name__ == "__main__":
    print(SCRAPE_INSTRUCTIONS)
    print("\n关键词列表：", KEYWORDS)
    print("账号列表：",   ACCOUNTS)
