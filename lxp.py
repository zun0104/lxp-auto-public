
import os
import json
import time
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    UnexpectedAlertPresentException,
    NoAlertPresentException,
)

LOGIN_URL = 'https://lxp.kau.ac.kr/login/index.php'
COURSES_FILE = 'courses.json'
KST = ZoneInfo('Asia/Seoul')

KAU_ID = os.environ.get('KAU_ID', '').strip()
KAU_PASSWORD = os.environ.get('KAU_PASSWORD', '')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', '').strip()
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
SELECTED_COURSES_RAW = os.environ.get('LXP_SELECTED_COURSES', '').strip()
LXP_MODE = os.environ.get('LXP_MODE', 'check').strip().lower()

MONITOR_INTERVAL = 10
LOG_INTERVAL_SECONDS = 300
PAUSE_GRACE_SECONDS = 20
STALL_GRACE_SECONDS = 60
RECOVERY_COOLDOWN_SECONDS = 120
MAX_RECOVERY_ATTEMPTS = 2
JOB_SAFE_LIMIT_SECONDS = int(5.5 * 60 * 60)


class OtherDevicePlaybackDetected(Exception):
    pass


class PlaybackRecoveryFailed(Exception):
    pass


class JobTimeLimitReached(Exception):
    pass


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print('[WARN] Telegram 설정 없음')
        return

    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'

    try:
        response = requests.post(
            url,
            data={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'disable_web_page_preview': True
            },
            timeout=20
        )
        response.raise_for_status()
        print('[OK] Telegram 전송 완료')

    except Exception as e:
        # 토큰이 포함될 수 있는 오류 메시지는 출력하지 않음
        response = getattr(e, 'response', None)
        status_code = getattr(response, 'status_code', None)

        if status_code is not None:
            print(f'[WARN] Telegram 전송 실패 (HTTP {status_code})')
        else:
            print(f'[WARN] Telegram 전송 실패 ({type(e).__name__})')


def parse_lxp_time(text):
    dt = datetime.strptime(text.strip(), '%Y-%m-%d %H:%M:%S')
    return dt.replace(tzinfo=KST)


def format_seconds(seconds):
    try:
        if seconds is None:
            return '알 수 없음'
        if math.isnan(seconds):
            return '알 수 없음'
        seconds = int(seconds)
    except Exception:
        return '알 수 없음'

    hour = seconds // 3600
    minute = seconds % 3600 // 60
    second = seconds % 60
    return f'{hour:02d}:{minute:02d}:{second:02d}'


def load_courses():
    if not os.path.exists(COURSES_FILE):
        raise RuntimeError(f'{COURSES_FILE} 파일이 없습니다.')

    with open(COURSES_FILE, 'r', encoding='utf-8') as f:
        courses = json.load(f)

    result = {}
    for name, course_id in courses.items():
        result[str(name)] = int(course_id)
    return result


def get_selected_course_ids():
    if not SELECTED_COURSES_RAW:
        raise RuntimeError('LXP_SELECTED_COURSES Variable이 비어 있습니다.')

    selected = set()
    for value in SELECTED_COURSES_RAW.split(','):
        value = value.strip()
        if value:
            selected.add(int(value))

    if not selected:
        raise RuntimeError('선택된 과목이 없습니다.')
    return selected


def build_selected_courses():
    all_courses = load_courses()
    selected_ids = get_selected_course_ids()
    selected = {}

    for name, course_id in all_courses.items():
        if course_id in selected_ids:
            selected[name] = course_id

    unknown_ids = selected_ids - set(all_courses.values())
    if unknown_ids:
        raise RuntimeError(
            'courses.json에 없는 과목 ID: '
            + ', '.join((str(x) for x in sorted(unknown_ids)))
        )

    if not selected:
        raise RuntimeError('실행할 과목이 없습니다.')

    return selected


def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--autoplay-policy=no-user-gesture-required')
    options.add_argument('--mute-audio')

    return webdriver.Chrome(options=options)


def login(driver):
    print()
    print('[1] LXP 로그인')

    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 30)

    username = wait.until(
        EC.visibility_of_element_located((By.ID, 'input-username'))
    )
    password = wait.until(
        EC.visibility_of_element_located((By.ID, 'input-password'))
    )

    username.clear()
    username.send_keys(KAU_ID)
    password.clear()
    password.send_keys(KAU_PASSWORD)

    driver.find_element(
        By.CSS_SELECTOR, 'button[name="loginbutton"]'
    ).click()

    wait.until(lambda d: '/login/index.php' not in d.current_url)
    print('[OK] 로그인 성공')


def find_current_unfinished_vods(driver, course_name, course_id):
    print()
    print('=' * 60)
    print('[과목]', course_name)
    print('=' * 60)

    course_url = (
        f'https://lxp.kau.ac.kr/course/view.php'
        f'?id={course_id}&mode=sections'
    )
    driver.get(course_url)

    wait = WebDriverWait(driver, 30)
    wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

    time.sleep(5)
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
    time.sleep(3)

    vod_links = driver.find_elements(
        By.CSS_SELECTOR, 'a[href*="/mod/vod/view.php"]'
    )
    print(f'VOD 링크: {len(vod_links)}개')

    now = datetime.now(KST)
    checked = set()
    targets = []

    for link in vod_links:
        url = link.get_attribute('href')
        if not url:
            continue
        if url in checked:
            continue
        checked.add(url)

        try:
            card = link.find_element(
                By.XPATH, "./ancestor::*[@data-region='activity-card'][1]"
            )
        except Exception:
            continue

        try:
            title = card.find_element(
                By.CSS_SELECTOR, '.activityname'
            ).text.strip()
        except Exception:
            title = card.get_attribute('data-activityname') or '제목 없음'

        try:
            playtime = card.find_element(
                By.CSS_SELECTOR, '.text-playtime'
            ).text.strip()
        except Exception:
            playtime = '정보 없음'

        try:
            open_text = card.find_element(
                By.CSS_SELECTOR, '.timeopen'
            ).text.strip()
            close_text = card.find_element(
                By.CSS_SELECTOR, '.timeclose'
            ).text.strip()

            open_time = parse_lxp_time(open_text)
            close_time = parse_lxp_time(close_text)
        except Exception:
            continue

        statuses = []
        for element in card.find_elements(
            By.CSS_SELECTOR, '.csms-chips .text'
        ):
            text = element.text.strip()
            if text:
                statuses.append(text)

        completed = '완료' in statuses
        active = open_time <= now <= close_time

        print()
        print('제목:', title)
        print('기간 내:', active)
        print('완료:', completed)

        if active and not completed:
            targets.append({
                'course': course_name,
                'course_id': course_id,
                'title': title,
                'playtime': playtime,
                'url': url,
                'open': open_time,
                'close': close_time,
            })

    print()
    print(f'[{course_name}] 미완료 VOD:', len(targets), '개')
    return targets


def collect_all_targets(driver, selected_courses):
    all_targets = []
    for course_name, course_id in selected_courses.items():
        targets = find_current_unfinished_vods(
            driver, course_name, course_id
        )
        all_targets.extend(targets)
    return all_targets


def send_check_result(targets):
    now = datetime.now(KST)

    if not targets:
        send_telegram(
            f"✅ KAU LXP 주간 강의 확인\n\n"
            f"{now.strftime('%Y-%m-%d %H:%M')} KST\n\n"
            "현재 참여기간에 있는 미완료 VOD가 없습니다."
        )
        return

    message = f'📚 KAU LXP 미완료 강의\n\n총 {len(targets)}개\n\n'

    for index, target in enumerate(targets, start=1):
        message += (
            f"{index}. [{target['course']}]\n"
            f"{target['title']}\n"
            f"⏱ {target['playtime']}\n"
            f"📅 마감: {target['close'].strftime('%m/%d %H:%M')}\n"
            f"🔗 {target['url']}\n\n"
        )

    send_telegram(message.rstrip())


def send_autoplay_plan(targets):
    if not targets:
        return

    message = f'📚 KAU LXP 자동재생 예정\n\n총 {len(targets)}개\n\n'

    for index, target in enumerate(targets, start=1):
        message += f"{index}. [{target['course']}] {target['title']}\n"

    message += '\n자동재생을 시작합니다.'
    send_telegram(message)


def handle_browser_alert(driver):
    try:
        alert = driver.switch_to.alert
        text = alert.text.strip()
    except NoAlertPresentException:
        return 'none'

    print()
    print('[ALERT]', text)

    other_device_keywords = [
        '다른 동영상',
        '다른 플레이어',
        '다른 기기',
        '중복 재생',
        '동시 재생',
        '현재 창의 동영상 플레이를 중단'
    ]

    if any(keyword in text for keyword in other_device_keywords):
        try:
            alert.accept()
        except Exception:
            pass
        raise OtherDevicePlaybackDetected(text)

    resume_keywords = [
        '이어', '이전', '계속', '시청하던', '재생 위치'
    ]

    if any(keyword in text for keyword in resume_keywords):
        print('[INFO] JS 이어보기 팝업')
        alert.accept()
        return 'resume'

    try:
        alert.accept()
    except Exception:
        pass

    return 'unknown'


def handle_resume_banner(driver, video=None):
    try:
        buttons = driver.find_elements(
            By.CSS_SELECTOR, 'button.btn-continue'
        )
    except Exception:
        return False

    for button in buttons:
        try:
            if not button.is_displayed():
                continue
        except Exception:
            continue

        print()
        print('[INFO] LXP 이어보기 배너 발견')

        before = 0
        if video is not None:
            try:
                before = driver.execute_script(
                    'return arguments[0].currentTime;', video
                )
            except Exception:
                pass

        print('[INFO] 이어보기 전:', format_seconds(before))

        try:
            driver.execute_script('arguments[0].click();', button)
        except Exception:
            button.click()

        print('[OK] 이어보기 클릭')
        time.sleep(3)

        if video is not None:
            for _ in range(10):
                try:
                    position = driver.execute_script(
                        'return arguments[0].currentTime;', video
                    )
                    if position > before + 2:
                        print('[OK] 이어보기 위치:', format_seconds(position))
                        return True
                except UnexpectedAlertPresentException:
                    handle_browser_alert(driver)
                except Exception:
                    pass
                time.sleep(1)

        return True

    return False


def handle_generic_resume_modal(driver):
    dialogs = driver.find_elements(
        By.CSS_SELECTOR, ".modal.show, [role='dialog']"
    )

    for dialog in dialogs:
        try:
            if not dialog.is_displayed():
                continue
            text = dialog.text.strip()
        except Exception:
            continue

        resume_words = [
            '이어', '시청하던', '이전 위치', '계속 재생'
        ]

        if not any(word in text for word in resume_words):
            continue

        buttons = dialog.find_elements(By.TAG_NAME, 'button')
        preferred = [
            '이어보기', '이어 재생', '계속', '확인', '예'
        ]

        for keyword in preferred:
            for button in buttons:
                try:
                    text = button.text.strip()
                    if keyword in text:
                        driver.execute_script(
                            'arguments[0].click();', button
                        )
                        print('[OK] 이어보기 클릭:', text)
                        time.sleep(3)
                        return True
                except Exception:
                    continue

    return False


def get_video_state(driver, video):
    script = """
        return {
            currentTime: arguments[0].currentTime,
            duration: arguments[0].duration,
            paused: arguments[0].paused,
            ended: arguments[0].ended,
            readyState: arguments[0].readyState
        };
    """

    try:
        return driver.execute_script(script, video)
    except UnexpectedAlertPresentException:
        handle_browser_alert(driver)
        time.sleep(1)
        return driver.execute_script(script, video)


def open_player(driver, vod):
    print()
    print('=' * 60)
    print(f"[재생 준비] [{vod['course']}]")
    print(vod['title'])
    print('=' * 60)

    driver.get(vod['url'])
    wait = WebDriverWait(driver, 40)

    video = wait.until(
        EC.presence_of_element_located(
            (By.ID, 'my-video_html5_api')
        )
    )

    print('[OK] Video.js 발견')
    time.sleep(3)

    resume_clicked = handle_resume_banner(driver, video)
    if not resume_clicked:
        handle_generic_resume_modal(driver)

    handle_browser_alert(driver)
    return video


def start_playback(driver, video):
    handle_resume_banner(driver, video)
    handle_generic_resume_modal(driver)
    handle_browser_alert(driver)

    state = get_video_state(driver, video)

    if state['paused'] is False and state['currentTime'] > 0:
        print('[OK] 이미 재생 중:', format_seconds(state['currentTime']))
        return state['currentTime']

    try:
        button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, 'button.vjs-big-play-button')
            )
        )
        button.click()
    except Exception:
        driver.execute_script('arguments[0].play();', video)

    for _ in range(30):
        time.sleep(1)
        handle_browser_alert(driver)

        state = get_video_state(driver, video)
        if state['paused'] is False and state['currentTime'] > 1:
            print('[OK] 실제 시작 위치:', format_seconds(state['currentTime']))
            return state['currentTime']

    raise PlaybackRecoveryFailed('영상 재생 시작 실패')


def try_recover_playback(
    driver, video, current_time, recovery_count, last_recovery_time
):
    now = time.time()

    if (
        last_recovery_time is not None
        and now - last_recovery_time < RECOVERY_COOLDOWN_SECONDS
    ):
        raise PlaybackRecoveryFailed(
            '자동 복구 직후 다시 재생 문제가 발생했습니다.'
        )

    if recovery_count >= MAX_RECOVERY_ATTEMPTS:
        raise PlaybackRecoveryFailed('자동 복구 최대 횟수를 초과했습니다.')

    recovery_count += 1
    print()
    print('[RECOVERY] 자동 복구 시도', recovery_count)

    handle_browser_alert(driver)
    handle_resume_banner(driver, video)
    handle_generic_resume_modal(driver)

    driver.execute_script('arguments[0].play();', video)
    start_position = current_time

    for _ in range(15):
        time.sleep(1)
        handle_browser_alert(driver)

        state = get_video_state(driver, video)

        if (
            state['paused'] is False
            and state['currentTime'] > start_position + 2
        ):
            print('[OK] 자동 복구 성공')
            return recovery_count, time.time()

    raise PlaybackRecoveryFailed('자동 복구 실패')


def monitor_video(driver, video, vod, job_start_time):
    state = get_video_state(driver, video)

    send_telegram(
        f"▶ KAU LXP 자동 재생 시작\n\n"
        f"[{vod['course']}]\n"
        f"{vod['title']}\n\n"
        f"길이: {vod['playtime']}\n"
        f"시작 위치: {format_seconds(state['currentTime'])}"
    )

    last_position = state['currentTime']
    last_progress_time = time.time()
    last_log_time = 0
    pause_started = None
    recovery_count = 0
    last_recovery_time = None

    while True:
        if time.time() - job_start_time >= JOB_SAFE_LIMIT_SECONDS:
            raise JobTimeLimitReached(last_position)

        state = get_video_state(driver, video)

        current_time = state['currentTime']
        duration = state['duration']
        paused = state['paused']
        ended = state['ended']
        ready_state = state['readyState']

        now_time = time.time()

        if (
            last_log_time == 0
            or now_time - last_log_time >= LOG_INTERVAL_SECONDS
        ):
            print(
                '[재생]',
                format_seconds(current_time),
                '/',
                format_seconds(duration),
                '| paused:', paused,
                '| ended:', ended,
                '| readyState:', ready_state
            )
            last_log_time = now_time

        remaining = 999999

        try:
            if not math.isnan(duration):
                remaining = duration - current_time
        except Exception:
            pass

        if ended or remaining <= 2:
            print()
            print('[COMPLETE]', vod['title'])

            send_telegram(
                f"✅ KAU LXP 영상 재생 완료\n\n"
                f"[{vod['course']}]\n"
                f"{vod['title']}\n\n"
                f"최종 위치: {format_seconds(current_time)}"
            )
            return current_time

        if current_time > last_position + 2:
            last_progress_time = time.time()
            last_position = current_time

        if paused:
            if pause_started is None:
                pause_started = time.time()
                print()
                print(
                    '[WARN] 일시정지 감지:',
                    format_seconds(current_time)
                )

            if time.time() - pause_started >= PAUSE_GRACE_SECONDS:
                recovery_count, last_recovery_time = try_recover_playback(
                    driver,
                    video,
                    current_time,
                    recovery_count,
                    last_recovery_time
                )
                pause_started = None
        else:
            pause_started = None

        if not paused:
            stall_time = time.time() - last_progress_time

            if stall_time >= STALL_GRACE_SECONDS:
                print()
                print(
                    '[WARN] 영상 진행 정지:',
                    format_seconds(current_time)
                )

                recovery_count, last_recovery_time = try_recover_playback(
                    driver,
                    video,
                    current_time,
                    recovery_count,
                    last_recovery_time
                )
                last_progress_time = time.time()

        time.sleep(MONITOR_INTERVAL)


def run_check(driver, selected_courses):
    print()
    print('===== CHECK MODE =====')

    targets = collect_all_targets(driver, selected_courses)
    send_check_result(targets)

    print()
    print('[SUCCESS] CHECK 완료')


def run_autoplay(driver, selected_courses, job_start_time):
    print()
    print('===== AUTOPLAY MODE =====')

    targets = collect_all_targets(driver, selected_courses)

    if not targets:
        send_telegram(
            '✅ KAU LXP 확인 완료\n\n'
            '선택된 과목에 현재 참여 가능한 미완료 VOD가 없습니다.'
        )
        return

    send_autoplay_plan(targets)

    print()
    print('총 재생 대상:', len(targets), '개')

    current_target = None
    video = None
    last_position = 0

    try:
        for index, target in enumerate(targets, start=1):
            current_target = target

            print()
            print(f'[{index}/{len(targets)}]')
            print(f"[{target['course']}] {target['title']}")

            video = open_player(driver, target)
            last_position = start_playback(driver, video)

            driver.save_screenshot(f'playing_{index}.png')

            last_position = monitor_video(
                driver, video, target, job_start_time
            )

            time.sleep(5)

        send_telegram(
            f'🎉 KAU LXP 자동재생 완료\n\n'
            f'총 {len(targets)}개 영상의 재생을 모두 마쳤습니다.'
        )

        print()
        print('[SUCCESS] 모든 영상 완료')

    except OtherDevicePlaybackDetected:
        if video is not None:
            try:
                state = get_video_state(driver, video)
                last_position = state['currentTime']
            except Exception:
                pass

        print()
        print('[STOP] 다른 기기 재생 감지')

        if current_target:
            send_telegram(
                f"📱 KAU LXP 다른 기기 재생 감지\n\n"
                f"[{current_target['course']}]\n"
                f"{current_target['title']}\n\n"
                f"마지막 확인 위치: {format_seconds(last_position)}\n\n"
                "다른 기기에서 영상이 재생되어 "
                "GitHub 자동재생을 종료했습니다."
            )
        return

    except JobTimeLimitReached:
        if video is not None:
            try:
                state = get_video_state(driver, video)
                last_position = state['currentTime']
            except Exception:
                pass

        if current_target:
            send_telegram(
                f"⏳ KAU LXP 자동재생 일시 종료\n\n"
                f"[{current_target['course']}]\n"
                f"{current_target['title']}\n\n"
                f"마지막 확인 위치: {format_seconds(last_position)}\n\n"
                "GitHub 실행시간 한계에 도달하기 전에 "
                "안전하게 종료했습니다.\n"
                "다시 실행하면 이어보기로 계속합니다."
            )
        return

    except PlaybackRecoveryFailed as e:
        if video is not None:
            try:
                state = get_video_state(driver, video)
                last_position = state['currentTime']
            except Exception:
                pass

        if current_target:
            send_telegram(
                f"⚠️ KAU LXP 자동재생 중단\n\n"
                f"[{current_target['course']}]\n"
                f"{current_target['title']}\n\n"
                f"마지막 확인 위치: {format_seconds(last_position)}\n\n"
                f"{e}"
            )
        return


def main():
    job_start_time = time.time()

    if LXP_MODE not in ('check', 'autoplay'):
        raise RuntimeError(f'알 수 없는 LXP_MODE: {LXP_MODE}')

    if not KAU_ID:
        raise RuntimeError('KAU_ID Secret 없음')

    if not KAU_PASSWORD:
        raise RuntimeError('KAU_PASSWORD Secret 없음')

    selected_courses = build_selected_courses()

    print()
    print('실행 모드:', LXP_MODE)
    print()
    print('선택 과목:')

    for name, course_id in selected_courses.items():
        print(f'- {name} ({course_id})')

    driver = create_driver()

    try:
        login(driver)

        if LXP_MODE == 'check':
            run_check(driver, selected_courses)
        else:
            run_autoplay(
                driver, selected_courses, job_start_time
            )

    except Exception as e:
        print()
        print('[ERROR]', repr(e))

        try:
            driver.save_screenshot('lxp_error.png')
        except Exception:
            pass

        send_telegram(
            f'❌ KAU LXP 오류\n\n'
            f'모드: {LXP_MODE}\n'
            f'{type(e).__name__}\n'
            f'{e}'
        )
        raise

    finally:
        driver.quit()


if __name__ == '__main__':
    main()
