import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup

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

            print(
                f"페이지 접속 성공: {url} "
                f"(HTTP {response.status_code}, {len(response.text)} bytes)"
            )

            return response.text

        except requests.RequestException as e:
            last_error = e

            print(f"접속 실패 ({attempt + 1}/5): {e}")

            if attempt < 4:
                wait_seconds = 5 * (attempt + 1)

                print(f"{wait_seconds}초 후 다시 시도합니다.")

                time.sleep(wait_seconds)

    raise last_error


def clean_text(text: str) -> str:
    return " ".join(text.split()).strip()


def normalize_date(value: str) -> str:
    return value.replace(".", "-").replace("/", "-")


def extract_url_from_anchor(a, base_url: str):
    href = (a.get("href") or "").strip()

    if href and not href.lower().startswith("javascript:") and href != "#":
        return urljoin(base_url, href)

    onclick = a.get("onclick") or ""

    patterns = [
        r"""['"]([^'"]*notice\.gs[^'"]*)['"]""",
        r"""['"]([^'"]*view[^'"]*)['"]""",
        r"""location(?:\.href)?\s*=\s*['"]([^'"]+)['"]""",
        r"""window\.open\(\s*['"]([^'"]+)['"]""",
    ]

    for pattern in patterns:
        m = re.search(pattern, onclick, re.I)

        if m:
            return urljoin(base_url, m.group(1))

    return NOTICE_URL


def is_probable_notice_title(text: str) -> bool:
    text = clean_text(text)

    if len(text) < 4:
        return False

    excluded = {
        "공지사항",
        "업데이트 소개",
        "이벤트",
        "개발자 노트",
        "확률형 아이템",
        "주술 확률",
        "검색",
        "SEARCH",
        "다음",
        "이전",
        "처음",
        "마지막",
        "로그인",
        "회원가입",
    }

    if text in excluded:
        return False

    if DATE_RE.fullmatch(text):
        return False

    if text.isdigit():
        return False

    return True


def make_notice_key(title: str, date: str, url: str) -> str:
    parsed = urlparse(url)

    if parsed.query:
        return f"url:{url}"

    return f"title:{title}|date:{date}"


def parse_notices(html: str):
    soup = BeautifulSoup(html, "html.parser")

    notices = []
    seen_keys = set()

    # -----------------------------------------------------
    # 1차 방법
    # 게시판의 각 행(tr)을 기준으로 제목과 등록일을 찾는다.
    # -----------------------------------------------------
    for row in soup.find_all("tr"):
        row_text = clean_text(" ".join(row.stripped_strings))

        date_match = DATE_RE.search(row_text)

        if not date_match:
            continue

        date = normalize_date(date_match.group(0))

        anchors = row.find_all("a")

        best_anchor = None
        best_title = ""

        for a in anchors:
            title = clean_text(" ".join(a.stripped_strings))

            if not is_probable_notice_title(title):
                continue

            # 보통 실제 게시물 제목이 행 내에서 가장 긴 의미있는 링크이다.
            if len(title) > len(best_title):
                best_title = title
                best_anchor = a

        if best_anchor is None:
            continue

        url = extract_url_from_anchor(best_anchor, NOTICE_URL)

        key = make_notice_key(
            best_title,
            date,
            url,
        )

        if key in seen_keys:
            continue

        seen_keys.add(key)

        notices.append(
            {
                "kind": "공지",
                "key": key,
                "title": best_title,
                "date": date,
                "url": url,
            }
        )

    # -----------------------------------------------------
    # 2차 방법
    # 사이트 구조가 달라 tr 방식이 실패하면
    # 날짜가 포함된 부모 영역을 기준으로 다시 찾는다.
    # -----------------------------------------------------
    if not notices:
        for a in soup.find_all("a"):
            title = clean_text(" ".join(a.stripped_strings))

            if not is_probable_notice_title(title):
                continue

            container = (
                a.find_parent("li")
                or a.find_parent("div")
                or a.parent
            )

            if not container:
                continue

            container_text = clean_text(
                " ".join(container.stripped_strings)
            )

            date_match = DATE_RE.search(container_text)

            if not date_match:
                continue

            date = normalize_date(date_match.group(0))

            url = extract_url_from_anchor(a, NOTICE_URL)

            key = make_notice_key(
                title,
                date,
                url,
            )

            if key in seen_keys:
                continue

            seen_keys.add(key)

            notices.append(
                {
                    "kind": "공지",
                    "key": key,
                    "title": title,
                    "date": date,
                    "url": url,
                }
            )

    return notices


def event_title(a, full_url: str) -> str:
    text = clean_text(" ".join(a.stripped_strings))

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

    if parsed.netloc.lower() not in {
        "gersang.co.kr",
        "www.gersang.co.kr",
    }:
        return None

    if not parsed.path.lower().startswith("/event/"):
        return None

    return parsed._replace(
        query="",
        fragment="",
    ).geturl()


def parse_events(html: str):
    soup = BeautifulSoup(html, "html.parser")

    events = {}

    for a in soup.find_all("a", href=True):
        full_url = normalize_event_url(
            a.get("href", "")
        )

        if not full_url:
            continue

        title = event_title(
            a,
            full_url,
        )

        container = (
            a.find_parent(["li", "tr", "div"])
            or a.parent
        )

        container_text = (
            clean_text(
                " ".join(container.stripped_strings)
            )
            if container
            else title
        )

        m = DATE_RE.search(container_text)

        date = (
            normalize_date(m.group(0))
            if m
            else ""
        )

        events[full_url] = {
            "kind": "이벤트",
            "title": title,
            "date": date,
            "url": full_url,
        }

    return list(events.values())


def load_state():
    default = {
        "notice_seen_keys": [],
        "event_seen_urls": [],
    }

    if not STATE_FILE.exists():
        return default

    try:
        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        return {
            "notice_seen_keys": list(
                data.get(
                    "notice_seen_keys",
                    [],
                )
            ),
            "event_seen_urls": list(
                data.get(
                    "event_seen_urls",
                    [],
                )
            ),
        }

    except Exception as e:
        print(
            f"상태 파일 읽기 실패: {e}"
        )

        return default


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def send_discord(item):
    if not WEBHOOK_URL:
        raise RuntimeError(
            "DISCORD_WEBHOOK_URL 환경변수가 없습니다."
        )

    fields = []

    if item.get("date"):
        fields.append(
            {
                "name": "등록일",
                "value": item["date"],
                "inline": True,
            }
        )

    kind = item["kind"]

    payload = {
        "username": "거상 소식 알림",
        "embeds": [
            {
                "title": (
                    f"[{kind}] "
                    f"{item['title']}"
                )[:256],
                "url": item["url"],
                "description": (
                    f"거상 홈페이지에 새 "
                    f"{kind}이(가) 등록되었습니다."
                ),
                "fields": fields,
                "footer": {
                    "text": (
                        "천하제일상 거상 "
                        "공식 홈페이지"
                    )
                },
            }
        ],
    }

    response = requests.post(
        WEBHOOK_URL,
        json=payload,
        timeout=20,
    )

    response.raise_for_status()


def process_notices(state):
    print("")
    print("===== 공지사항 확인 =====")

    try:
        notice_html = fetch_html(
            NOTICE_URL
        )

    except Exception as e:
        print(
            f"공지사항 페이지 접속 실패: {e}"
        )

        return False

    notices = parse_notices(
        notice_html
    )

    print(
        f"공지사항 감지 개수: "
        f"{len(notices)}"
    )

    if notices:
        for item in notices[:5]:
            print(
                f"감지: "
                f"{item['date']} / "
                f"{item['title']}"
            )

    if not notices:
        print(
            "경고: 공지사항 게시물을 "
            "찾지 못했습니다."
        )

        return False

    old_seen = set(
        state.get(
            "notice_seen_keys",
            [],
        )
    )

    current_keys = [
        item["key"]
        for item in notices
    ]

    # 기존 프로그램에서 새 형식으로 처음 넘어온 경우
    # 기존 공지를 Discord에 한꺼번에 보내지 않고
    # 현재 목록을 기준점으로 저장한다.
    if not old_seen:
        state["notice_seen_keys"] = (
            current_keys[:100]
        )

        print(
            "공지 초기화: "
            f"현재 공지 {len(current_keys)}개를 "
            "기준점으로 저장"
        )

        return True

    new_notices = [
        item
        for item in notices
        if item["key"] not in old_seen
    ]

    if new_notices:
        print(
            f"새 공지 "
            f"{len(new_notices)}개 발견"
        )

        selected = new_notices[
            :MAX_SEND_PER_RUN
        ]

        # 오래된 것부터 Discord에 전송
        for item in reversed(selected):
            send_discord(item)

            print(
                "공지 Discord 전송: "
                f"{item['title']}"
            )

    else:
        print("새 공지 없음")

    merged = []

    for key in (
        current_keys
        + list(old_seen)
    ):
        if key not in merged:
            merged.append(key)

    new_state = merged[:100]

    changed = (
        new_state
        != state.get(
            "notice_seen_keys",
            [],
        )
    )

    state["notice_seen_keys"] = new_state

    return changed


def process_events(state):
    print("")
    print("===== 이벤트 확인 =====")

    try:
        event_html = fetch_html(
            EVENT_URL
        )

    except Exception as e:
        print(
            f"이벤트 페이지 접속 실패: {e}"
        )

        return False

    events = parse_events(
        event_html
    )

    print(
        f"이벤트 감지 개수: "
        f"{len(events)}"
    )

    if not events:
        print(
            "경고: 이벤트 링크를 찾지 못했습니다."
        )

        return False

    old_seen = set(
        state.get(
            "event_seen_urls",
            [],
        )
    )

    current_urls = [
        item["url"]
        for item in events
    ]

    if not old_seen:
        state["event_seen_urls"] = (
            current_urls[:100]
        )

        print(
            "이벤트 초기화: "
            f"현재 이벤트 {len(current_urls)}개를 "
            "기준점으로 저장"
        )

        return True

    new_events = [
        item
        for item in events
        if item["url"] not in old_seen
    ]

    if new_events:
        print(
            f"새 이벤트 "
            f"{len(new_events)}개 발견"
        )

        for item in new_events[
            :MAX_SEND_PER_RUN
        ]:
            send_discord(item)

            print(
                "이벤트 Discord 전송: "
                f"{item['title']}"
            )

    else:
        print("새 이벤트 없음")

    merged = []

    for url in (
        current_urls
        + list(old_seen)
    ):
        if url not in merged:
            merged.append(url)

    new_state = merged[:100]

    changed = (
        new_state
        != state.get(
            "event_seen_urls",
            [],
        )
    )

    state["event_seen_urls"] = new_state

    return changed


def main():
    print(
        "거상 공지/이벤트 확인을 시작합니다."
    )

    state = load_state()

    state_changed = False

    notice_changed = process_notices(
        state
    )

    if notice_changed:
        state_changed = True

    event_changed = process_events(
        state
    )

    if event_changed:
        state_changed = True

    if state_changed:
        save_state(state)

        print("")
        print("상태 파일 저장 완료")

    else:
        print("")
        print("상태 변경 없음")

    print("")
    print("확인 작업 완료")

    return 0


if __name__ == "__main__":
    sys.exit(main())
