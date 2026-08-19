import re
import time

import requests
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://www.gersang.co.kr/news/notice.gs?GSbid=1001"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.gersang.co.kr/",
}

DATE_RE = re.compile(r"20\d{2}[-./]\d{1,2}[-./]\d{1,2}")


def fetch():
    last_error = None

    for attempt in range(5):
        try:
            r = requests.get(
                URL,
                headers=HEADERS,
                timeout=30,
                verify=False,
            )
            r.raise_for_status()

            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding or "utf-8"

            print(f"HTTP {r.status_code}")
            print(f"HTML 크기: {len(r.text)} bytes")

            return r.text

        except requests.RequestException as e:
            last_error = e
            print(f"접속 실패 ({attempt + 1}/5): {e}")

            if attempt < 4:
                time.sleep(5)

    raise last_error


def main():
    html = fetch()
    soup = BeautifulSoup(html, "html.parser")

    print()
    print("========== 기본 구조 ==========")
    print("tr 개수:", len(soup.find_all("tr")))
    print("li 개수:", len(soup.find_all("li")))
    print("a 개수:", len(soup.find_all("a")))

    print()
    print("========== 날짜 주변 HTML ==========")

    found = 0

    for text_node in soup.find_all(string=DATE_RE):
        text = " ".join(text_node.strip().split())

        if not DATE_RE.search(text):
            continue

        found += 1

        print()
        print(f"----- 날짜 후보 {found} -----")
        print("텍스트:", text)

        parent = text_node.parent

        for level in range(4):
            if parent is None:
                break

            print()
            print(
                f"[부모 단계 {level}] "
                f"태그={parent.name} "
                f"class={parent.get('class')} "
                f"id={parent.get('id')}"
            )

            snippet = str(parent)

            if len(snippet) > 2000:
                snippet = snippet[:2000] + "...(생략)"

            print(snippet)

            parent = parent.parent

        if found >= 5:
            break

    print()
    print("========== 링크 후보 ==========")

    count = 0

    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        onclick = (a.get("onclick") or "").strip()
        text = " ".join(a.stripped_strings).strip()

        combined = f"{href} {onclick} {text}".lower()

        if (
            "notice" not in combined
            and "gsbid" not in combined
            and "main=" not in combined
            and "view" not in combined
        ):
            continue

        count += 1

        print()
        print(f"----- 링크 {count} -----")
        print("TEXT:", text[:300])
        print("HREF:", href)
        print("ONCLICK:", onclick)

        if count >= 30:
            break

    print()
    print("========== 진단 완료 ==========")


if __name__ == "__main__":
    main()
