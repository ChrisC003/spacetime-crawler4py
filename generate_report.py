import argparse
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urldefrag, urlparse

from bs4 import BeautifulSoup
from tokenizer import stopwords


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", default=None)
    parser.add_argument("--out", default=None)
    return parser.parse_args()


def latest_state_path():
    candidates = list(Path("states").glob("run_*/state.json"))
    candidates.extend(Path("pages").glob("run_*/state.json"))
    if not candidates:
        raise FileNotFoundError("No state.json found under states/ or pages/.")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def extract_words(saved_path):
    content = saved_path.read_bytes()
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True).lower()
    return re.findall(r"\b[a-z0-9]+\b", text)


def analyze(state_path):
    state = json.loads(state_path.read_text(encoding="utf-8"))
    pages = state.get("pages", {})
    failed = state.get("failed", {})
    traps = state.get("traps", {})

    unique_urls = set()
    word_counter = Counter()
    subdomains = Counter()
    longest_page = {"url": "", "word_count": 0, "saved_path": ""}
    missing_files = []

    for url, info in pages.items():
        defragged_url, _ = urldefrag(url)
        unique_urls.add(defragged_url)

        host = (urlparse(defragged_url).hostname or "").lower()
        if host.endswith(".uci.edu"):
            subdomains[host] += 1

        saved_path = Path(info.get("saved_path", ""))
        if not saved_path.exists():
            missing_files.append((url, str(saved_path)))
            continue

        words = extract_words(saved_path)
        if len(words) > longest_page["word_count"]:
            longest_page = {
                "url": defragged_url,
                "word_count": len(words),
                "saved_path": str(saved_path),
            }

        filtered = [
            word for word in words
            if word not in stopwords and len(word) > 1
        ]
        word_counter.update(filtered)

    return {
        "state": state,
        "unique_pages": len(unique_urls),
        "longest_page": longest_page,
        "top_words": word_counter.most_common(50),
        "subdomains": dict(sorted(subdomains.items())),
        "failed_count": len(failed),
        "traps_count": len(traps),
        "trap_reasons": Counter(
            item.get("reason", "unknown") for item in traps.values()
        ),
        "missing_files": missing_files,
    }


def write_outputs(result, state_path, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "state_path": str(state_path),
        "started_at": result["state"].get("started_at"),
        "last_saved_at": result["state"].get("last_saved_at"),
        "unique_pages": result["unique_pages"],
        "longest_page": result["longest_page"],
        "subdomain_count": len(result["subdomains"]),
        "failed_count": result["failed_count"],
        "traps_count": result["traps_count"],
        "missing_saved_files": len(result["missing_files"]),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    (out_dir / "top50_words.txt").write_text(
        "\n".join(
            f"{word}, {count}" for word, count in result["top_words"]
        ) + "\n",
        encoding="utf-8",
    )

    (out_dir / "subdomains.txt").write_text(
        "\n".join(
            f"{host}, {count}"
            for host, count in result["subdomains"].items()
        ) + "\n",
        encoding="utf-8",
    )

    report = build_report(result, summary)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    return out_dir


def generate_from_state(state_path, out_dir=None):
    state_path = Path(state_path)
    run_name = state_path.parent.name
    out_dir = Path(out_dir) if out_dir else Path("reports") / run_name
    result = analyze(state_path)
    return write_outputs(result, state_path, out_dir)


def build_report(result, summary):
    lines = [
        "# CS121 Web Crawler Report",
        "",
        f"1. Unique pages found: {summary['unique_pages']}",
        "",
        "2. Longest page by word count:",
        f"   - URL: {summary['longest_page']['url']}",
        f"   - Word count: {summary['longest_page']['word_count']}",
        "",
        "3. Top 50 words excluding English stop words:",
    ]
    for index, (word, count) in enumerate(result["top_words"], 1):
        lines.append(f"   {index}. {word}, {count}")

    lines.append("")
    lines.append(f"4. Subdomains found: {summary['subdomain_count']}")
    lines.append("")
    for host, count in result["subdomains"].items():
        lines.append(f"   - {host}, {count}")

    lines.extend([
        "",
        "",
        "## Other Information",
        f"- Failed URLs recorded: {summary['failed_count']}",
        f"- Trap URLs recorded: {summary['traps_count']}",
        f"- Missing saved files: {summary['missing_saved_files']}",
        "",
        "Top trap reasons:",
    ])
    for reason, count in result["trap_reasons"].most_common(20):
        lines.append(f"   - {reason}: {count}")

    lines.append("")
    return "\n".join(lines)


def main():
    args = parse_args()
    state_path = Path(args.state) if args.state else latest_state_path()
    generate_from_state(state_path, args.out)


if __name__ == "__main__":
    main()
