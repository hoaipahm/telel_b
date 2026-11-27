"""Link & RSS Feed Digest module protected by SSRF validation."""

from __future__ import annotations

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.db.repositories import Repository
from app.llm.base import ChatMessage, LLMRequest
from app.llm.router import LLMRouter
from app.security.ssrf import resolve_and_validate_url, safe_fetch_text


def extract_readable_html(html: str, max_chars: int = 12000) -> tuple[str, str]:
    """Extract clean page title and readable body text without executing scripts."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else "Untitled Page"
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    lines = [ln.strip() for ln in soup.get_text(separator="\n").splitlines() if ln.strip()]
    body = "\n".join(lines)[:max_chars]
    return title[:180], body


def parse_rss_items(xml_text: str, limit: int = 5) -> list[dict[str, str]]:
    """Parse RSS/Atom entries safely without DTD/entity expansion."""
    # Rename <link> so html.parser does not treat it as an HTML void element
    safe_markup = re.sub(r"<(/?)link\b", r"<\1rsslink", xml_text, flags=re.I)
    soup = BeautifulSoup(safe_markup, "html.parser")
    entries = soup.find_all(["item", "entry"], limit=limit)
    results: list[dict[str, str]] = []
    for entry in entries:
        title_tag = entry.find("title")
        link_tag = entry.find("rsslink")
        title = title_tag.get_text(strip=True) if title_tag else "Untitled"
        href = ""
        if link_tag:
            href = str(link_tag.get("href") or link_tag.get_text(strip=True) or "")
        results.append({"title": title[:160], "url": href.strip()})
    return results


class DigestService:
    """Summarizes web links and tracks RSS feeds safely."""

    def __init__(
        self,
        repo: Repository,
        router: LLMRouter,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._repo = repo
        self._router = router
        self._http = http_client

    async def summarize_url(self, url: str) -> dict[str, Any]:
        """Fetch a public URL through SSRF checks, summarize via LLM, and persist."""
        final_url, content_type, raw_text = await safe_fetch_text(url, client=self._http)
        if "html" in content_type.lower():
            title, readable = extract_readable_html(raw_text)
        else:
            title = final_url.rsplit("/", 1)[-1] or final_url
            readable = raw_text[:12000]

        if not readable.strip():
            raise ValueError("Trang web không có nội dung văn bản đọc được.")

        res = await self._router.complete(
            LLMRequest(
                messages=[
                    ChatMessage(
                        role="user",
                        content=(
                            "Hãy tóm tắt bài viết sau bằng tiếng Việt thành 5 gạch đầu dòng "
                            "súc tích, kèm 1 câu 'Điểm đáng chú ý nhất':\n\n"
                            f"Tiêu đề: {title}\nURL: {final_url}\n\n{readable}"
                        ),
                    )
                ],
                temperature=0.3,
                max_tokens=700,
            )
        )
        return await self._repo.save_digest(url=final_url, title=title, summary=res.text)

    async def subscribe_feed(self, url: str, title: str = "") -> dict[str, Any]:
        clean_url = await resolve_and_validate_url(url)
        final_title = title.strip() or clean_url
        return await self._repo.add_feed(url=clean_url, title=final_title)

    async def fetch_feed_headlines(self, url: str, limit: int = 5) -> list[dict[str, str]]:
        _, _, xml_text = await safe_fetch_text(url, client=self._http)
        return parse_rss_items(xml_text, limit=limit)

    async def build_morning_briefing(self, limit_per_feed: int = 3) -> str:
        """Fetch latest headlines across enabled RSS feeds and format a compact digest."""
        feeds = [f for f in await self._repo.list_feeds() if f.get("enabled")]
        if not feeds:
            return ""
        sections: list[str] = ["Điểm tin sáng từ RSS đã theo dõi:"]
        for feed in feeds[:6]:
            title = str(feed.get("title") or feed["url"])
            try:
                items = await self.fetch_feed_headlines(str(feed["url"]), limit=limit_per_feed)
            except Exception as exc:
                sections.append(f"\n• {title}: lỗi tải ({str(exc)[:80]})")
                continue
            if not items:
                continue
            sections.append(f"\n**{title}**")
            for item in items:
                link = item.get("url") or ""
                if link:
                    sections.append(f"• [{item['title']}]({link})")
                else:
                    sections.append(f"• {item['title']}")
        return "\n".join(sections) if len(sections) > 1 else ""
