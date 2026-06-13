from __future__ import annotations

import re
from typing import Dict, List, Tuple
from urllib.parse import quote

# LINE image message 支援 jpeg/png（HTTPS、原圖 <= 10MB）
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def rewrite_local_paths(text: str, *, local_root: str, public_base: str) -> Tuple[str, List[str]]:
    """把文字中的本地路徑換成公開 URL。

    回傳 (改寫後的文字, 圖片 URL 清單)。
    local_root 例：/Users/bowwow/XX/outputs
    public_base 例：https://XX.org/files
    """
    if not local_root or not public_base or local_root not in text:
        return text, _collect_image_urls(text, public_base)

    pattern = re.compile(re.escape(local_root) + r"[^\s'\"`)\]>，。、）】]*")

    def _to_url(match: re.Match) -> str:
        path = match.group(0)
        rel = path[len(local_root):].lstrip("/")
        return "{base}/{rel}".format(base=public_base, rel=quote(rel))

    rewritten = pattern.sub(_to_url, text)
    return rewritten, _collect_image_urls(rewritten, public_base)


def _collect_image_urls(text: str, public_base: str) -> List[str]:
    if not public_base:
        return []
    pattern = re.compile(re.escape(public_base) + r"[^\s'\"`)\]>，。、）】]*")
    urls: List[str] = []
    for match in pattern.finditer(text):
        url = match.group(0)
        if url.lower().endswith(IMAGE_EXTENSIONS) and url not in urls:
            urls.append(url)
    return urls


def image_messages(urls: List[str], limit: int = 4) -> List[Dict[str, str]]:
    return [
        {
            "type": "image",
            "originalContentUrl": url,
            "previewImageUrl": url,
        }
        for url in urls[:limit]
    ]
