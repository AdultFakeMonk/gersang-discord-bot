import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

import requests
import urllib3
from bs4 import BeautifulSoup

# 거상 사이트의 SSL 인증서 체인 문제로 GitHub Actions에서 검증 오류가 날 수 있어 경고를 숨깁니다.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

NOTICE_URL = "https://www.gersang.co.kr/news/notice.gs?GSbid=1001"
EVENT_URL = "https://www.gersang.co.kr/news/event.gs"
STATE_FILE = Path("last_seen.json")
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
MAX_SEND_PER_RUN = int(os.environ.get("MAX_SEND_PER_RUN", "5"))

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
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.gersang.co.kr/",
}

DATE_RE = re.compile(r"20\d{2}[-./]\d{1,2}[-./]\d{1,2}")


def fetch_html(url: str) -> str:
    last_error = None

    for attempt in range(5):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30,
                verify=False,
            )
            response.raise_for_status()

            if not response.encoding or response.encoding.lower() == "iso-8859-1":
                response.encoding = response.apparent_encoding or "utf-8"

            return response.text

        except requests.RequestException as e:
            last_error = e
            print(f"접속 실패 ({attempt + 1}/5): {e}")

            if attempt < 4:
                wait_seconds = 5 * (attempt + 1)
                print(f"{wait_seconds}초 후 다시 시도합니다.")
                time.sleep(wait_seconds)

    raise last_error


def extract_notice_id(href: str):
    try:
        qs = parse_qs(urlparse(href).query)
        value = qs.get("main", [None])[0]
        return int(value) if value and value.isdigit() else None
    except Exception:
        return None


def parse_notices(html: str):
    soup = BeautifulSoup(html, "html.parser")
    posts = {}

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "main=" not in href:
            continue

        post_id = extract_notice_id(href)
        if post_id is None:
            continue

        title = " ".join(a.stripped_strings).strip()
        if not title:
            continue

        full_url = urljoin(NOTICE_URL, href)
        container = a.find_parent("tr") or a.parent
        row_text = " ".join(container.stripped_strings) if container else title
        m = DATE_RE.search(row_text)
        date = m.group(0).replace(".", "-").replace("/", "-") if m else ""

        posts[post_id] = {
            "kind": "공지",
            "id": post_id,
            "title": title,
            "date": date,
            "url": full_url,
        }

    return [posts[k] for k in sorted(posts, reverse=True)]


def event_title(a, full_url: str) -> str:
    text = " ".join(a.stripped_strings).strip()
    if text:
        return text

    img = a.find("img")
    if img:
        alt = (img.get("alt") or "").strip()
        if alt and alt.lower() != "image":
            return alt

    title_attr = (a.get("title") or "").strip()
    if title_attr:
        return title_attr

    path = urlparse(full_url).path.rstrip("/")
    slug = path.split("/")[-1] if path else ""
    if slug.lower() in {"main.gs", "intro.gs"}:
        parts = path.split("/")
        slug = parts[-2] if len(parts) >= 2 else slug
    return slug or "새 이벤트"


def normalize_event_url(href: str):
    full_url = urljoin(EVENT_URL, href)
    parsed = urlparse(full_url)

    if parsed.netloc.lower() not in {"gersang.co.kr", "www.gersang.co.kr"}:
        return None
    if not parsed.path.lower().startswith("/event/"):
        return None

    # 추적용 쿼리/fragment를 제거해 같은 이벤트가 중복 감지되는 것을 방지한다.
    return parsed._replace(query="", fragment="").geturl()


def parse_events(html: str):
    soup = BeautifulSoup(html, "html.parser")
    events = {}

    for a in soup.find_all("a", href=True):
        full_url = normalize_event_url(a.get("href", ""))
        if not full_url:
            continue

        title = event_title(a, full_url)
        container = a.find_parent(["li", "tr", "div"]) or a.parent
        container_text = " ".join(container.stripped_strings) if container else title
        m = DATE_RE.search(container_text)
        date = m.group(0).replace(".", "-").replace("/", "-") if m else ""

        events[full_url] = {
            "kind": "이벤트",
            "title": title,
            "date": date,
            "url": full_url,
        }

    return list(events.values())


def load_state():
    default = {"notice_last_id": None, "event_seen_urls": []}
    if not STATE_FILE.exists():
        return default

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))

        # v1 파일(last_seen) 자동 호환
        if "notice_last_id" not in data and data.get("last_seen") is not None:
            data["notice_last_id"] = int(data["last_seen"])

        return {
            "notice_last_id": data.get("notice_last_id"),
            "event_seen_urls": list(data.get("event_seen_urls", [])),
        }
    except Exception:
        return default


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def send_discord(item):
    if not WEBHOOK_URL:
        raise RuntimeError("DISCORD_WEBHOOK_URL 환경변수가 없습니다.")

    fields = []
    if item.get("date"):
        fields.append({"name": "등록일", "value": item["date"], "inline": True})

    kind = item["kind"]
    payload = {
        "username": "거상 소식 알림",
        "embeds": [
            {
                "title": f"[{kind}] {item['title']}"[:256],
                "url": item["url"],
                "description": f"거상 홈페이지에 새 {kind}이(가) 등록되었습니다.",
                "fields": fields,
                "footer": {"text": "천하제일상 거상 공식 홈페이지"},
            }
        ],
    }

    r = requests.post(WEBHOOK_URL, json=payload, timeout=20)
    r.raise_for_status()


def main():
    state = load_state()
    state_changed = False

    # 1) 공지사항 확인
    notice_html = fetch_html(NOTICE_URL)
    notices = parse_notices(notice_html)
    if not notices:
        print("경고: 공지사항 게시물을 찾지 못했습니다.")
    else:
        newest_notice_id = notices[0]["id"]
        last_id = state.get("notice_last_id")

        if last_id is None:
            state["notice_last_id"] = newest_notice_id
            state_changed = True
            print(f"공지 초기화: 최신 글 {newest_notice_id}을 기준점으로 저장")
        else:
            new_notices = [p for p in notices if p["id"] > int(last_id)]
            new_notices = sorted(new_notices, key=lambda p: p["id"])[-MAX_SEND_PER_RUN:]
            for item in new_notices:
                send_discord(item)
                print(f"공지 전송: {item['id']} {item['title']}")

            if new_notices:
                state["notice_last_id"] = max(p["id"] for p in new_notices)
                state_changed = True
            else:
                print(f"새 공지 없음. last={last_id}, newest={newest_notice_id}")

    # 2) 이벤트 확인
    event_html = fetch_html(EVENT_URL)
    events = parse_events(event_html)
    if not events:
        print("경고: 이벤트 링크를 찾지 못했습니다. 이벤트 페이지 구조를 확인해 주세요.")
    else:
        old_seen = set(state.get("event_seen_urls", []))
        current_urls = [e["url"] for e in events]

        if not old_seen:
            # 첫 실행에는 현재 노출 중인 이벤트를 전부 기준점으로만 저장
            state["event_seen_urls"] = current_urls[:100]
            state_changed = True
            print(f"이벤트 초기화: 현재 이벤트 {len(current_urls)}개를 기준점으로 저장")
        else:
            new_events = [e for e in events if e["url"] not in old_seen]
            for item in new_events[:MAX_SEND_PER_RUN]:
                send_discord(item)
                print(f"이벤트 전송: {item['title']} - {item['url']}")

            # 현재 페이지 + 과거 감지값을 합쳐 최대 100개 유지
            merged = []
            for url in current_urls + list(old_seen):
                if url not in merged:
                    merged.append(url)
            state["event_seen_urls"] = merged[:100]
            if new_events:
                state_changed = True
            elif state["event_seen_urls"] != list(old_seen):
                state_changed = True
            print(f"새 이벤트 {len(new_events)}개")

    if state_changed:
        save_state(state)
        print("상태 파일 저장 완료")
    else:
        print("상태 변경 없음")

    return 0


if __name__ == "__main__":
    sys.exit(main())
