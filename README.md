# JQSubtitle — Just Quality AI Subtitle Maker

영상/음성 파일에서 **SRT + SMI 자막을 한 번에 자동 생성**하는 Windows용 프로그램입니다.
Whisper(large-v3)로 받아쓰고, Claude AI(선택)로 교정·문장 분할·다국어 번역까지 처리합니다.

*Create SRT + SMI subtitles from video/audio in one click — Whisper transcription with
word-level timing, plus optional Claude AI correction, sentence splitting and translation.
UI available in English, 한국어, 日本語, 中文, Français, Português, Español.*

## 주요 기능

- **음성 인식**: Whisper large-v3, 단어 단위 실측 타임스탬프 (GPU 자동 사용, 없으면 CPU)
- **자막 정리**: 문장 단위 분할, 뭉친 자막(60자/8초 초과) 자동 분할, 끝 1초 표시 연장
- **SRT + SMI 동시 출력**: SMI는 cp949 인코딩·KRCC 클래스 등 국내 플레이어 호환 형식
- **Claude AI (선택, API 키 필요)**: 받아쓰기 오류 교정, 자연스러운 문장 분할, 15개 언어 번역
- **AI 추가 지시**: "이름 표기 교정", "존댓말 번역" 등 자유 요청 입력
- **배치 처리**: 여러 파일 한 번에, 파일별 에러 격리 + 마지막 에러 요약, 완료 알림
- **UI 표시 언어 7종**, 설정 자동 저장(config.json), 드래그 앤 드롭

## 설치 및 실행

1. [Python 3.10+](https://www.python.org/downloads/) 설치 (설치 시 "Add to PATH" 체크)
2. `jqsubtitle_v1.0.py` 다운로드 후 더블클릭 또는:
   ```
   python jqsubtitle_v1.0.py
   ```
3. 첫 실행 때 필요한 엔진(faster-whisper 등)이 자동 설치되고, 첫 자막 생성 때
   Whisper 모델(~3GB)을 한 번 내려받습니다.

## Claude AI 기능 (선택)

교정·번역을 쓰려면 [console.anthropic.com](https://console.anthropic.com/settings/keys)에서
API 키를 발급받아 프로그램에 입력하세요. 사용량만큼 과금되며(에피소드 1편 교정+번역에 보통
수십 원 수준), 키 없이도 받아쓰기 자막은 만들어집니다.

## 문의 · 후원

- 버그 제보/의견: [GitHub Issues](https://github.com/i3luegirl/jqsubtitle/issues)
- 이 프로그램이 도움이 됐다면: [PayPal로 후원하기](https://paypal.me/jqpark) ☕

## License

MIT License · © 2026 JQ Park
