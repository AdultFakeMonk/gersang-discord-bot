import os
import sys
import time
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup


urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)

NOTICE_URL = (
    "https://www.gersang.co.kr/"
    "news/notice.gs?GSbid=1001"
)

EVENT_URL = (
    "https://www.gersang.co.kr/"
    "news/event.gs"
)

NOTICE_WEBHOOK_URL = os.environ.get(
    "DISCORD_NOTICE_WEBHOOK_URL",
    "",
).strip()

EVENT_WEBHOOK_URL = os.environ.get(
    "DISCORD_EVENT_WEBHOOK_URL",
    "",
).strip()


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
    "Accept-Language": (
        "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    ),
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


def get_latest_notice():
    html = fetch_html(
        NOTICE_URL
    )

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

        notices.append(
            {
                "kind": "공지",
                "id": int(uid_text),
                "title": title,
                "date": date,
                "url": NOTICE_URL,
            }
        )

    if not notices:
        raise RuntimeError(
            "공지사항을 찾지 못했습니다."
        )

    notices.sort(
        key=lambda item: item["id"],
        reverse=True,
    )

    return notices[0]


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


def get_latest_active_event():
    html = fetch_html(
        EVENT_URL
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    events = []

    for box in soup.select(
        "div.list-box"
    ):
        label_box = box.select_one(
            ".txt-box .label"
        )

        subject_link = box.select_one(
            ".txt-box .subject a"
        )

        subject_box = box.select_one(
            ".txt-box .subject"
        )

        date_box = box.select_one(
            ".txt-box .date"
        )

        if label_box is None:
            continue

        status = " ".join(
            label_box.stripped_strings
        ).strip()

        # 진행중 이벤트만 테스트 대상
        if status != "진행중":
            continue

        if subject_link is None:
            continue

        href = (
            subject_link.get("href")
            or ""
        ).strip()

        full_url = normalize_event_url(
            href
        )

        if not full_url:
            continue

        title = ""

        if subject_box:
            title = " ".join(
                subject_box.stripped_strings
            ).strip()

        if not title:
            continue

        period = ""

        if date_box:
            period = " ".join(
                date_box.stripped_strings
            ).strip()

        events.append(
            {
                "kind": "이벤트",
                "title": title,
                "status": status,
                "period": period,
                "url": full_url,
            }
        )

    if not events:
        raise RuntimeError(
            "진행중인 이벤트를 찾지 못했습니다."
        )

    return events[0]


def send_discord(
    webhook_url,
    item,
):
    if not webhook_url:
        raise RuntimeError(
            f"{item['kind']}용 "
            "Discord Webhook이 없습니다."
        )

    fields = []

    if (
        item["kind"] == "공지"
        and item.get("date")
    ):
        fields.append(
            {
                "name": "등록일",
                "value": item["date"],
                "inline": False,
            }
        )

    if (
        item["kind"] == "이벤트"
        and item.get("period")
    ):
        fields.append(
            {
                "name": "이벤트 기간",
                "value": item["period"],
                "inline": False,
            }
        )

    payload = {
        "username": "거상 소식 알림",
        "embeds": [
            {
                "title": (
                    f"[{item['kind']}] "
                    f"{item['title']}"
                )[:256],
                "url": item["url"],
                "description": (
                    "현재 거상 홈페이지 기준 "
                    "실제 알림 표시 테스트입니다."
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


def main():
    print(
        "현재 최신 공지/이벤트 "
        "Discord 테스트를 시작합니다."
    )

    print("")
    print(
        "===== 최신 공지 테스트 ====="
    )

    notice = get_latest_notice()

    print(
        f"공지 ID: {notice['id']}"
    )

    print(
        f"공지 제목: {notice['title']}"
    )

    print(
        f"등록일: {notice['date']}"
    )

    send_discord(
        NOTICE_WEBHOOK_URL,
        notice,
    )

    print(
        "최신 공지 Discord 전송 완료"
    )

    print("")
    print(
        "===== 진행중 이벤트 테스트 ====="
    )

    event = get_latest_active_event()

    print(
        f"이벤트 제목: "
        f"{event['title']}"
    )

    print(
        f"상태: "
        f"{event['status']}"
    )

    print(
        f"이벤트 기간: "
        f"{event['period']}"
    )

    print(
        f"이벤트 링크: "
        f"{event['url']}"
    )

    send_discord(
        EVENT_WEBHOOK_URL,
        event,
    )

    print(
        "진행중 이벤트 Discord 전송 완료"
    )

    print("")
    print(
        "테스트 완료"
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
