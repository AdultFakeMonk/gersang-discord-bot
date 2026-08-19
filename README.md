# 거상 공지사항 + 이벤트 -> Discord 알림

거상 공식 홈페이지의 **공지사항**과 **이벤트**를 약 10분 간격으로 확인하고, 새 항목이 생기면 Discord Webhook으로 전송합니다.

## 감시 대상
- 공지사항: `https://www.gersang.co.kr/news/notice.gs?GSbid=1001`
- 이벤트: `https://www.gersang.co.kr/news/event.gs`

## 중복 방지 방식
- 공지사항: 게시글 URL의 `main=` 번호를 기준으로 마지막 게시물 번호 저장
- 이벤트: `/event/...` 이벤트 URL 자체를 고유값으로 저장
- 첫 실행에서는 기존 글/이벤트를 전송하지 않고 현재 상태만 기준점으로 저장

## Discord Webhook
Discord 채널 설정 -> 연동(Integrations) -> Webhooks -> New Webhook -> Copy Webhook URL

Webhook URL은 공개하지 마세요.

## GitHub Actions 무료 운영 설정
1. GitHub에서 새 저장소를 만듭니다.
2. 이 폴더 안의 파일을 저장소 루트에 그대로 업로드합니다.
3. `.github/workflows/check.yml` 경로가 유지되어야 합니다.
4. 저장소 `Settings -> Secrets and variables -> Actions -> New repository secret`로 이동합니다.
5. Secret 이름: `DISCORD_WEBHOOK_URL`
6. 값: Discord에서 복사한 Webhook URL
7. `Actions -> Check Gersang notices and events -> Run workflow`를 한 번 실행합니다.
8. 첫 실행은 현재 공지/이벤트를 기준점으로 저장합니다. 이후 새 항목부터 Discord로 전송됩니다.

## 기존 v1에서 교체하는 경우
기존 저장소의 `main.py`, `.github/workflows/check.yml`을 새 버전으로 덮어쓰면 됩니다.
기존 `last_seen.json`에 `last_seen`만 있어도 공지 번호는 자동으로 이어받습니다.
이벤트는 첫 실행 시 현재 노출 이벤트를 기준점으로 초기화합니다.

## 주의
- GitHub Actions의 cron 예약 실행은 정확히 해당 분에 시작되지 않고 지연될 수 있습니다.
- 사이트 HTML 구조가 변경되면 파서 수정이 필요할 수 있습니다.
- 홈페이지 부담을 줄이기 위해 너무 짧은 간격으로 조회하지 않는 것을 권장합니다.
