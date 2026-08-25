import requests
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

MAX_HOPS = 15


def get_redirect_chain(url: str, timeout: int = 10) -> list[dict]:
    """
    Follow a URL hop by hop without auto-redirecting.
    Returns a list of steps: [{url, status, label, error}]
    Final step is the landing page (non-redirect or error).
    """
    chain = []
    current = url
    seen: set[str] = set()

    for _ in range(MAX_HOPS):
        if current in seen:
            chain.append({"url": current, "status": None,
                          "label": "Loop", "error": "Redirect loop detected"})
            break
        seen.add(current)

        try:
            resp = requests.get(current, allow_redirects=False,
                                timeout=timeout, headers=HEADERS)
            status = resp.status_code
            label = _label(status)
            step = {"url": current, "status": status, "label": label, "error": ""}
            chain.append(step)

            if status in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location", "").strip()
                if not location:
                    break
                current = urljoin(current, location)
            else:
                break

        except requests.exceptions.ConnectionError:
            chain.append({"url": current, "status": None,
                          "label": "Error", "error": "Connection failed"})
            break
        except requests.exceptions.Timeout:
            chain.append({"url": current, "status": None,
                          "label": "Error", "error": "Timed out"})
            break
        except Exception as e:
            chain.append({"url": current, "status": None,
                          "label": "Error", "error": str(e)})
            break

    return chain


def _label(status: int) -> str:
    labels = {
        200: "200 OK",
        301: "301 Moved Permanently",
        302: "302 Found",
        303: "303 See Other",
        307: "307 Temporary Redirect",
        308: "308 Permanent Redirect",
        404: "404 Not Found",
        403: "403 Forbidden",
        500: "500 Server Error",
        503: "503 Unavailable",
    }
    return labels.get(status, f"{status}")


def status_colour(status) -> tuple[str, str]:
    """Return (background, foreground) hex colours for a status code."""
    if status is None:
        return "#f0f0f0", "#888888"
    if 200 <= status < 300:
        return "#edfaf1", "#1a7a3e"   # green
    if status in (301, 308):
        return "#eff6ff", "#1d4ed8"   # blue – permanent
    if status in (302, 303, 307):
        return "#fffbeb", "#b45309"   # amber – temporary
    if 400 <= status < 500:
        return "#fdecea", "#b71c1c"   # red
    if 500 <= status < 600:
        return "#2d0a0a", "#ff8a80"   # dark red
    return "#f0f0f0", "#555555"
