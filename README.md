KAU LXP Automation

한국항공대학교 LXP의 온라인 동영상 강의를 확인하고 자동재생하는 Python 프로그램입니다.

GitHub Actions를 통해 자동으로 실행하며, Telegram으로 강의 목록과 실행 결과를 알림받을 수 있습니다.

주요 기능

- Check: 미완료 강의 목록 및 마감일 확인
- Autoplay: 선택한 과목의 미완료 강의 자동재생
- Resume: 이어보기 및 재생 중단 시 자동 복구 시도
- Telegram: 강의 목록, 실행 상태 및 오류 알림
- Schedule: 매주 화요일 00:10(KST) 자동 확인

파일 구성

파일| 설명
"lxp.py"| 메인 프로그램
"courses.json"| 수강 과목 및 ID
"requirements.txt"| Python 라이브러리
"lxp.yml"| GitHub Actions 실행 설정

초기 설정

1. GitHub Secrets 등록

"Settings → Secrets and variables → Actions"

다음 Secrets를 등록합니다.

- "KAU_ID": LXP 아이디
- "KAU_PASSWORD": LXP 비밀번호
- "TELEGRAM_TOKEN": Telegram 봇 토큰
- "TELEGRAM_CHAT_ID": Telegram 채팅 ID

2. 수강 과목 설정

"courses.json"에 과목명과 과목 ID를 등록합니다.

3. 실행할 과목 선택

GitHub Actions의 Variables에 "LXP_SELECTED_COURSES"를 등록합니다.

예시: "1234,5678"

실행 방법

"Actions → KAU LXP → Run workflow"

- "check": 강의 목록 확인
- "autoplay": 강의 자동재생

예약 실행은 Check 모드로 동작합니다.

참고사항

- LXP 페이지 구조 변경 시 정상 작동하지 않을 수 있습니다.
- 자동재생이 실제 출석 또는 학습 완료를 보장하지는 않습니다.
- 학교 및 강의 운영 규정을 확인한 후 사용하세요.
- 계정 정보와 봇 토큰은 GitHub Secrets로 관리하세요.



Telegram 봇 설정

1. Telegram 봇 생성

1. Telegram에서 "@BotFather" (https://t.me/BotFather)를 검색합니다.
2. "/newbot" 명령어를 입력합니다.
3. 봇 이름과 사용자 이름을 설정합니다. (사용자 이름은 "bot"으로 끝나야 합니다.)
4. 발급된 Bot Token을 복사합니다.

2. Chat ID 확인

1. Telegram에서 생성한 봇을 검색합니다.

2. "/start"를 입력하고 메시지를 하나 보냅니다.

3. 브라우저에서 다음 주소에 접속합니다.
   
   "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"

4. "<YOUR_TOKEN>"을 발급받은 Bot Token으로 바꿉니다.

5. 표시된 JSON에서 ""chat":{"id":123456789}" 부분을 찾습니다.

6. "id" 뒤의 숫자가 Chat ID입니다.

결과가 비어 있다면 봇에게 메시지를 다시 보내고 새로고침합니다.

3. GitHub Secrets 등록

GitHub 저장소의 "Settings → Secrets and variables → Actions → New repository secret"에서 다음 두 항목을 등록합니다.

Name| Secret
"TELEGRAM_TOKEN"| BotFather에서 발급받은 토큰
"TELEGRAM_CHAT_ID"| 확인한 Chat ID

설정 완료 후 GitHub Actions를 실행하면 Telegram으로 강의 목록과 실행 결과를 받을 수 있습니다.

주의: Bot Token은 비밀번호처럼 관리해야 합니다. 외부에 공유하거나 GitHub 코드에 직접 입력하지 마세요. 토큰이 포함된 API 주소도 공유하지 마세요.
