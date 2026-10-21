"""Public article snapshots with pinned DNS, redirect and size limits."""
import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

MAX_URL_BYTES = 2 * 1024 * 1024


def parse_article(data, content_type, url, host):
    """Keep paragraph/heading locations within the saved HTML snapshot."""
    if content_type == "text/plain":
        text = data.decode("utf-8-sig")
        blocks = [{"text": value.strip(), "locator": {"type": "article", "url": url, "line": i}}
                  for i, value in enumerate(text.splitlines(), 1) if value.strip()]
        title = host
    else:
        soup = BeautifulSoup(data, "html.parser")
        title = soup.title.get_text(" ", strip=True)[:200] if soup.title else host
        if soup.find("input", attrs={"type": "password"}) and not soup.find("article"):
            raise ValueError("Trang đang yêu cầu đăng nhập; chưa có bài viết công khai.")
        for script in soup.find_all("script"):
            if (script.get("type") or "").startswith("math/tex"):
                script.replace_with("\\(" + script.get_text() + "\\)")
        for element in soup.find_all(["script", "style", "nav", "header", "footer", "form", "iframe"]):
            element.decompose()
        root = soup.find("article") or soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup
        tags = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "tr", "blockquote"}
        blocks, heading = [], ""
        for tag in root.find_all(list(tags)):
            if any(parent is not root and parent.name in tags for parent in tag.parents):
                continue
            value = tag.get_text(" ", strip=True)
            if not value:
                continue
            if tag.name.startswith("h") and tag.name[1:].isdigit():
                heading = value
            blocks.append({"text": value, "locator": {"type": "article", "url": url,
                "paragraph": len(blocks) + 1, "tag": tag.name, "heading": heading, "element_id": tag.get("id", "")}})
        if not blocks:
            blocks = [{"text": value, "locator": {"type": "article", "url": url, "line": i}}
                      for i, value in enumerate(root.get_text("\n", strip=True).splitlines(), 1) if value.strip()]
        text = "\n".join(b["text"] for b in blocks)
    if not text.strip():
        raise ValueError("Chưa lấy được chữ từ bài viết; trang động cần nguồn văn bản khác.")
    if len(text) > 120_000 or len(blocks) > 400:
        raise ValueError("Bài viết vượt giới hạn trích xuất; chưa dùng phần bị cắt để tạo bài.")
    fragments = []
    for block in blocks:
        for offset in range(0, len(block["text"]), 2400):
            fragments.append({"text": block["text"][offset:offset+2400], "locator": {**block["locator"], "character_start": offset}})
    if len(fragments) > 400:
        raise ValueError("Bài viết vượt giới hạn 400 trích đoạn; cần chia nguồn.")
    return {"title": title, "text": text, "fragments": fragments}


async def resolve(host, port):
    answers = await asyncio.to_thread(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(a[4][0] for a in answers))


async def public_target(url, resolver=resolve):
    if len(url) > 3000 or any(ord(c) < 32 for c in url):
        raise ValueError("Link quá dài hoặc chứa ký tự không hợp lệ.")
    parsed = urlsplit(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("Chỉ nhận link bài viết http/https công khai, không dùng thông tin đăng nhập trong link.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port not in {80, 443}:
        raise ValueError("Link bài viết chỉ dùng cổng web 80/443.")
    host = parsed.hostname.rstrip(".").encode("idna").decode("ascii")
    addresses = await resolver(host, port)
    if not addresses:
        raise ValueError("Không tìm thấy máy chủ của bài viết.")
    for value in addresses:
        address = ipaddress.ip_address(value)
        mapped = address.ipv4_mapped if isinstance(address, ipaddress.IPv6Address) else None
        if not address.is_global or mapped and not mapped.is_global or isinstance(address, ipaddress.IPv6Address) and address in ipaddress.ip_network("64:ff9b::/96"):
            raise ValueError("Không đọc link trỏ về localhost, mạng nội bộ hoặc địa chỉ không công khai.")
    normalized = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
    return normalized, host, addresses[0]


async def send(url, host, address):
    original = httpx.URL(url)
    pinned = original.copy_with(host=address)
    headers = {"Host": original.netloc.decode("ascii"), "User-Agent": "DocumentStudyLocal/1.0", "Accept": "text/html,text/plain", "Accept-Encoding": "identity"}
    # The TCP target stays pinned to the checked IP; Host and TLS SNI retain
    # the real domain, including normal certificate/hostname verification.
    async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=5), trust_env=False, follow_redirects=False) as client:
        request = client.build_request("GET", pinned, headers=headers, extensions={"sni_hostname": host})
        response = await client.send(request, stream=True)
        try:
            if response.status_code in {301, 302, 303, 307, 308}:
                return response.status_code, dict(response.headers), b""
            if response.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Máy chủ gửi nội dung nén dù đã yêu cầu bản không nén; chưa đọc để tránh vượt giới hạn.")
            if int(response.headers.get("content-length", "0")) > MAX_URL_BYTES:
                raise ValueError("Bài viết vượt giới hạn 2 MiB.")
            chunks, total = [], 0
            async for part in response.aiter_bytes(chunk_size=65536):
                total += len(part)
                if total > MAX_URL_BYTES:
                    raise ValueError("Bài viết vượt giới hạn 2 MiB; chưa đọc toàn bộ.")
                chunks.append(part)
            return response.status_code, dict(response.headers), b"".join(chunks)
        finally:
            await response.aclose()


async def fetch_article(url, resolver=resolve, sender=send):
    async def work():
        current = url
        for step in range(4):
            normalized, host, address = await public_target(current, resolver)
            status, headers, data = await sender(normalized, host, address)
            if status in {301, 302, 303, 307, 308}:
                if step == 3 or not headers.get("location"):
                    raise ValueError("Link chuyển hướng quá nhiều hoặc thiếu đích hợp lệ.")
                current = urljoin(normalized, headers["location"])
                continue
            if status in {401, 403}:
                raise ValueError("Bài viết cần đăng nhập hoặc không cho đọc công khai; không vượt đăng nhập.")
            if status != 200:
                raise ValueError(f"Bài viết trả trạng thái {status}; chưa có nội dung để học.")
            if len(data) > MAX_URL_BYTES:
                raise ValueError("Bài viết vượt giới hạn 2 MiB.")
            content_type = headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise ValueError("Link này chưa trả bài viết HTML/văn bản; tải file qua mục tài liệu nếu phù hợp.")
            return {"url": normalized, "original": data, "content_type": content_type, **parse_article(data, content_type, normalized, host)}
        raise ValueError("Chưa có đích bài viết.")
    try:
        return await asyncio.wait_for(work(), timeout=35)
    except (httpx.HTTPError, OSError, UnicodeError, asyncio.TimeoutError) as exc:
        raise ValueError("Không đọc được link công khai trong giới hạn; nguồn đang có không bị thay.") from exc
