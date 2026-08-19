import json
import os
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

NOTICE_WEBHOOK_URL = os.environ.get(
    "DISCORD_NOTICE_WEBHOOK_URL",
    "",
).strip()

EVENT_WEBHOOK_URL = os.environ.get(
    "DISCORD_EVENT_WEBHOOK_URL",
    "",
).strip()

MAX_SEND_PER_RUN = int(
    os.environ.get(
        "MAX_SEND_PER_RUN",
        "5",
    )
)

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


def fetch_html(url):
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

            if (
                not response.encoding
                or response.encoding.lower() == "iso-8859-1"
            ):
                response.encoding = (
                    response.apparent_encoding
                    or "utf-8"
                )

            print(
                f"페이지 접속 성공: {url} "
                f"(HTTP {response.status_code}, "
                f"{len(response.text)} bytes)"
            )

            return response.text

        except requests.RequestException as e:
            last_error = e

            print(
                f"접속 실패 "
                f"({attempt + 1}/5): {e}"
            )

            if attempt < 4:
                wait_seconds = 5 * (attempt + 1)

                print(
                    f"{wait_seconds}초 후 "
                    "다시 시도합니다."
                )

                time.sleep(wait_seconds)

    raise last_error


def parse_notices(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    notices = []

    for row in soup.select(
        "div.tr[data-uid]"
    ):
        uid_text = (
            row.get("data-uid")
            or ""
        ).strip()

        if not uid_text.isdigit():
            continue

        subject = row.select_one(
            ".box-subject"
        )

        date_box = row.select_one(
            ".box-date"
        )

        category_box = row.select_one(
            ".box-category"
        )

        if subject is None:
            continue

        title = " ".join(
            subject.stripped_strings
        ).strip()

        if not title:
            continue

        date = ""

        if date_box:
            date = " ".join(
                date_box.stripped_strings
            ).strip()

        category = ""

        if category_box:
            category = " ".join(
                category_box.stripped_strings
            ).strip()

        notices.append(
            {
                "kind": "공지",
                "id": int(uid_text),
                "title": title,
                "date": date,
                "category": category,
                "url": NOTICE_URL,
            }
        )

    notices.sort(
        key=lambda item: item["id"],
        reverse=True,
    )

    return notices


def event_title(a, full_url):
    text = " ".join(
        a.stripped_strings
    ).strip()

    if text:
        return text

    img = a.find("img")

    if img:
        alt = (
            img.get("alt")
            or ""
        ).strip()

        if (
            alt
            and alt.lower() != "image"
        ):
            return alt

    title_attr = (
        a.get("title")
        or ""
    ).strip()

    if title_attr:
        return title_attr

    path = urlparse(
        full_url
    ).path.rstrip("/")

    slug = (
        path.split("/")[-1]
        if path
        else ""
    )

    if slug.lower() in {
        "main.gs",
        "intro.gs",
    }:
        parts = path.split("/")

        slug = (
            parts[-2]
            if len(parts) >= 2
            else slug
        )

    return slug or "새 이벤트"


def normalize_event_url(href):
    full_url = urljoin(
        EVENT_URL,
        href,
    )

    parsed = urlparse(
        full_url
    )

    if parsed.netloc.lower() not in {
        "gersang.co.kr",
        "www.gersang.co.kr",
    }:
        return None

    if not parsed.path.lower().startswith(
        "/event/"
    ):
        return None

    return parsed._replace(
        query="",
        fragment="",
    ).geturl()


def parse_events(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    events = {}

    for a in soup.find_all(
        "a",
        href=True,
    ):
        full_url = normalize_event_url(
            a.get("href", "")
        )

        if not full_url:
            continue

        title = event_title(
            a,
            full_url,
        )

        events[full_url] = {
            "kind": "이벤트",
            "title": title,
            "date": "",
            "url": full_url,
        }

    return list(
        events.values()
    )


def load_state():
    default = {
        "notice_last_id": None,
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
            "notice_last_id": data.get(
                "notice_last_id"
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
    kind = item["kind"]

    if kind == "공지":
        webhook_url = (
            NOTICE_WEBHOOK_URL
        )

    elif kind == "이벤트":
        webhook_url = (
            EVENT_WEBHOOK_URL
        )

    else:
        raise RuntimeError(
            f"알 수 없는 알림 종류입니다: "
            f"{kind}"
        )

    if not webhook_url:
        raise RuntimeError(
            f"{kind}용 Discord Webhook "
            "환경변수가 없습니다."
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
        webhook_url,
        json=payload,
        timeout=20,
    )

    response.raise_for_status()


def process_notices(state):
    print("")
    print(
        "===== 공지사항 확인 ====="
    )

    try:
        html = fetch_html(
            NOTICE_URL
        )

    except Exception as e:
        print(
            "공지사항 페이지 "
            f"접속 실패: {e}"
        )

        return False

    notices = parse_notices(
        html
    )

    print(
        f"공지사항 감지 개수: "
        f"{len(notices)}"
    )

    for item in notices[:5]:
        print(
            f"감지: ID={item['id']} / "
            f"{item['date']} / "
            f"{item['title']}"
        )

    if not notices:
        print(
            "경고: 공지사항 게시물을 "
            "찾지 못했습니다."
        )

        return False

    newest_id = notices[0]["id"]

    last_id = state.get(
        "notice_last_id"
    )

    if last_id is None:
        state[
            "notice_last_id"
        ] = newest_id

        print(
            f"공지 초기화: 최신 ID "
            f"{newest_id}을 "
            "기준점으로 저장"
        )

        return True

    try:
        last_id = int(
            last_id
        )

    except Exception:
        last_id = 0

    new_notices = [
        item
        for item in notices
        if item["id"] > last_id
    ]

    if not new_notices:
        print(
            f"새 공지 없음. "
            f"last={last_id}, "
            f"newest={newest_id}"
        )

        return False

    print(
        f"새 공지 "
        f"{len(new_notices)}개 발견"
    )

    new_notices.sort(
        key=lambda item: item["id"]
    )

    selected = new_notices[
        -MAX_SEND_PER_RUN:
    ]

    for item in selected:
        send_discord(
            item
        )

        print(
            f"공지 Discord 전송: "
            f"{item['id']} / "
            f"{item['title']}"
        )

    state[
        "notice_last_id"
    ] = max(
        item["id"]
        for item in selected
    )

    return True


def process_events(state):
    print("")
    print(
        "===== 이벤트 확인 ====="
    )

    try:
        html = fetch_html(
            EVENT_URL
        )

    except Exception as e:
        print(
            "이벤트 페이지 "
            f"접속 실패: {e}"
        )

        return False

    events = parse_events(
        html
    )

    print(
        f"이벤트 감지 개수: "
        f"{len(events)}"
    )

    if not events:
        print(
            "경고: 이벤트를 "
            "찾지 못했습니다."
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
        state[
            "event_seen_urls"
        ] = current_urls[:100]

        print(
            f"이벤트 초기화: "
            f"현재 이벤트 "
            f"{len(current_urls)}개를 "
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
            send_discord(
                item
            )

            print(
                "이벤트 Discord 전송: "
                f"{item['title']}"
            )

    else:
        print(
            "새 이벤트 없음"
        )

    merged = []

    for url in (
        current_urls
        + list(old_seen)
    ):
        if url not in merged:
            merged.append(
                url
            )

    new_state = merged[:100]

    changed = (
        new_state
        != state.get(
            "event_seen_urls",
            [],
        )
    )

    state[
        "event_seen_urls"
    ] = new_state

    return changed


def main():
    print(
        "거상 공지/이벤트 "
        "확인을 시작합니다."
    )

    state = load_state()

    changed = False

    if process_notices(
        state
    ):
        changed = True

    if process_events(
        state
    ):
        changed = True

    if changed:
        save_state(
            state
        )

        print("")
        print(
            "상태 파일 저장 완료"
        )

    else:
        print("")
        print(
            "상태 변경 없음"
        )

    print("")
    print(
        "확인 작업 완료"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
