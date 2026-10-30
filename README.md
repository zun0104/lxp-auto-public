lxp자동재생\
동영상강의를 배속재생하기 위한 프로그램입니다. 출결에 사용하지 마세요.\
준비물 : 깃허브, 텔레그램\
크롬에서 깃허브 로그인 후 링크 접속\
https://github.com/zun0104/lxp-auto-public

1. template복사\
  use this template -> create a new repository\
  repository name : lxp-auto\
  visibility : private\
  create repository\
  앞으로의 모든 작업은 lxp-auto-public이 아닌 lxp-auto에서만 진행됨

2. 수강 과목 등록\
  courses.json 클릭 -> 연필 모양 클릭해서 수정 -> 양식에 맞춰서 과목명과 과목id수정\
  과목id는 인터넷으로 lxp접속 후 수강 과목 홈에 들어가면 링크가\
  https://lxp.kau.ac.kr/course/view.php?id=****\
  이렇게 생겼는데 ****이 id임\
  수정 후 commit changes로 저장

3. telegram 봇 만들기\
  telegram에서 @botfather을 열어 /newbot입력\
  알아서 설정하면 api token발급됨 복사해둘것 유출안되게 조심

  telegram에서 @userinfobot을 열고 start를 누르면 chat id 확인가능 복사해둘것 유출안되게 조심\
  @userinfobot낚시용 계정들이 많으니 조심할것 초록프로필에 공식인증마크있는걸로ㄱㄱ

  본인이 직접 만든 봇에게 /start보내서 대화 시작하기 그래야 알림받을 수 있음

4. github secrets등록\
  처음에 만들었던 github의 lxp-auto repository로 돌아와서\
  settings -> secrets and variables -> actions -> secrets -> new repository secrets\
  대소문자 꼭! 지켜서\
  Name*에 KAU_ID\
  Secret*에 lxp아이디\
  add secret 하면 등록됨\
  마찬가지로\
  KAU_PASSWORD : lxp비번\
  TELEGRAM_TOKEN : Botfather에서 발급받은 토큰\
  TELEGRAM_CHAT_ID : 아까 확인한 Chat id

6. 자동재생실행할 과목 선택\
  secrets등록한 화면에서 variables -> new repository variable\
  마찬가지로 대소문자 지켜서\
  Name*에 LXP_SELECTED_COURSES\
  Value*에 courses.json에 등록했던 과목 id　(예시)1234,5678

  courses.json에는 이번학기 수강하는 과목id를 전부 등록해놓고 \
  LXP_SELETED_COURSES에는 자동재생 원하는 과목id만 입력

6. github actions 실행\
  lxp-auto에서 actions탭으로 이동\
  만약 actions가 비활성화되어있으면 활성화할것\
  모바일 환경이면 all workflow 왼쪽에 감춰진 탭꺼내는 버튼이 있음\
  KAU LXP선택\
  run workflow클릭하고 원하는 모드 선택

  check : 미완료 강의 확인 및 telegram에 알림\
  autoplay : 선택한 과목의 미완료 강의 자동재생

  일단 check모드로 해본 후 잘되면 autoplayㄱㄱ

7.알아야 될 것\
  매주 화요일 오전 00:10(KST)에 자동으로 check가 실행됨\
  화요일마다 알림확인 후 깃허브들어가서 workflow를 autoplay모드로 실행하면됨\
  자동재생 중 본인이 직접 동영상재생하면 자동재생 중단 됨 그럼 다시 workflow











