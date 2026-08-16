# JQSubtitle — Just Quality AI Subtitle Maker

Create **SRT + SMI subtitles from video or audio in one click** on Windows.
Whisper (large-v3) transcribes with word-level timing. An AI engine then rebuilds those
words into real sentences — one sentence per line, split where the speaker actually
changes, punctuated — fixes mis-heard words, and translates into 15 languages.

**Free with a Gemini API key — no credit card.** That is the recommended setup.
Prefer to stay offline? A local model runs entirely on your own PC, no key and no internet.

- **Clean subtitles from messy speech.** Speech recognition returns a stream of words with
  no sentence boundaries. Cutting that at silences glues separate sentences together and
  chops lines mid-thought. JQSubtitle rebuilds the lines from word-level timings instead,
  so timing always comes from real measurements — never from guesswork.
- **Nothing is trusted blindly.** Every AI reply is validated. If it drops words, invents
  text, or breaks the numbering, it is rejected and the original is kept.

## Features

- **Transcription**: Whisper large-v3 with true word-level timestamps (uses GPU automatically, falls back to CPU)
- **Sentence rebuilding**: subtitles are assembled from word timings, not patched afterwards — run-on lines are separated, words cut into the wrong line are put back, and long lines are split at natural pauses
- **Validated output**: replies with missing, duplicate or out-of-range word numbers are rejected; the original is kept and the reason is logged
- **SRT + SMI output together**: SMI uses cp949 encoding and KRCC-style classes for Korean players
- **Three AI engines** — pick one in the app:
  - **Gemini** — free API key, no credit card. Default and recommended.
  - **Claude** — paid API, the best quality if you want to pay per use.
  - **Local AI** — Ollama on your own PC, no key, fully offline. Quality is now close to the
    free API; what matters is your graphics card. Needs a ~7.6 GB download.
  You must pick one of the three — there is no "off". Sentence rebuilding, proofreading and
  translation are all AI steps, so turning them off only ever produced broken subtitles.
- **Custom AI instructions**: free-text box, e.g. "fix these character names", "translate politely"
- **Batch processing**: many files at once, per-file error isolation with a final error summary, completion chime
- **Automatic update check**: tells you when a new version is out and updates itself in one click
- **7 UI languages** (English, 한국어, 日本語, 中文, Français, Português, Español), settings auto-saved, drag & drop

## Install

**Option A — Quick install (one line).** Open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/i3luegirl/jqsubtitle/main/install.ps1 | iex
```

This installs Python if needed, downloads JQSubtitle, sets up the speech engine and
puts a **JQSubtitle icon on your Desktop**.

**Option B — Manual install.**

1. Install [Python 3.10+](https://www.python.org/downloads/) (check "Add to PATH")
2. Download `jqsubtitle.py` and double-click it, or run:
   ```
   python jqsubtitle.py
   ```
3. On first launch the required engine (faster-whisper) installs itself.

Either way, the Whisper model (~3 GB) downloads once on your first transcription.

## Updating

From v1.1 on, JQSubtitle checks for a new version on start and offers to update itself —
one click, then it restarts. You can turn the check off under **Help → Check for updates
on start**, or check manually any time from the same menu.

If you are still on v1.0, run the one-line installer above once; after that the built-in
updater takes over.

## AI engines

You pick one of the three in the app — there is no "off" switch. Sentence rebuilding,
proofreading and translation are all AI steps, so running without them only ever
produced broken subtitles. Set up whichever suits you:

- **Gemini (free)** — get a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
  and paste it into the app. No credit card. The free tier has per-minute rate limits;
  the app waits and retries automatically.
- **Claude (paid)** — get a key at [console.anthropic.com](https://console.anthropic.com/settings/keys).
  Correcting + translating one ~25 min episode usually costs a few cents.
- **Local AI (free, offline)** — select it in the app and click Install; it sets up
  Ollama and a ~7.6 GB model (Gemma 4 12B). An NVIDIA GPU with 10 GB+ VRAM is recommended.
  Quality is close to the free API, but with too little VRAM the model spills over to the CPU
  and gets much slower — use it when you need to work offline or want
  nothing to leave your computer.

Keys are stored only in `config.json` on your own PC.

## About the developer

Made by JQ Park, who also makes **[sunny friends STEM](https://www.youtube.com/@sunnyfriends.science)** —
a YouTube channel with STEM animations for kids. JQSubtitle started as the tool used to
subtitle those videos.

## Feedback · Support

- Bug reports / ideas: [GitHub Issues](https://github.com/i3luegirl/jqsubtitle/issues)
- If this saved you time: [Support via PayPal](https://paypal.me/jqpark) ☕

---

# 한국어 소개

영상/음성 파일에서 **SRT + SMI 자막을 한 번에 자동 생성**하는 Windows용 프로그램입니다.
Whisper(large-v3)가 단어 단위 타임스탬프까지 받아쓰면, AI 엔진이 그 단어들을 진짜 문장으로
다시 조립합니다 — 한 줄에 한 문장씩, 말하는 사람이 바뀌는 자리에서 끊고, 문장부호를 붙여서.
잘못 들은 단어를 고치고 15개 언어로 번역까지 합니다.

**Gemini API 키로 무료 사용 — 카드 등록 불필요.** 이 조합을 권합니다.
오프라인으로 쓰고 싶다면 로컬 모델이 이 PC 안에서만 돌아갑니다. 키도 인터넷도 필요 없습니다.

## 주요 기능

- **음성 인식**: Whisper large-v3, 단어 단위 실측 타임스탬프 (GPU 자동 사용, 없으면 CPU)
- **문장 재조립**: 자막을 사후에 손보는 게 아니라 단어 타임스탬프에서 새로 조립 — 붙어 나온 문장을 나누고, 옆 줄로 잘려 넘어간 단어를 되돌리고, 긴 줄은 쉬는 자리에서 분할
- **응답 검증**: 단어 번호가 빠지거나 겹치거나 범위를 벗어난 응답은 거부하고 원본 유지 (사유는 로그에 기록)
- **SRT + SMI 동시 출력**: SMI는 cp949 인코딩·KRCC 클래스 등 국내 플레이어 호환 형식
- **AI 엔진 3종** — 프로그램에서 선택:
  - **Gemini** — 무료 API 키, 카드 등록 불필요. 기본값이자 권장.
  - **Claude** — 유료 API. 돈을 써서라도 최고 품질을 원할 때.
  - **로컬 AI** — 내 PC의 Ollama, 키 없음·완전 오프라인. 품질은 무료 API에 근접했고,
    관건은 그래픽카드입니다. 약 7.6GB 다운로드가 필요합니다.
  셋 중 하나를 반드시 골라야 하며 "끄기"는 없습니다. 문장 재조립·교정·번역이 전부 AI
  단계라, 끄면 사실상 망가진 자막만 나오기 때문입니다.
- **AI 추가 지시**: "이름 표기 교정", "존댓말 번역" 등 자유 요청 입력
- **배치 처리**: 여러 파일 한 번에, 파일별 에러 격리 + 마지막 에러 요약, 완료 알림
- **자동 업데이트 확인**: 새 버전이 나오면 알려주고, 클릭 한 번으로 업데이트
- **UI 표시 언어 7종**, 설정 자동 저장(config.json), 드래그 앤 드롭

## 설치

**방법 A — 빠른 설치 (한 줄).** PowerShell을 열고 붙여넣기:

```powershell
irm https://raw.githubusercontent.com/i3luegirl/jqsubtitle/main/install.ps1 | iex
```

Python이 없으면 자동 설치하고, 프로그램 다운로드·음성 엔진 설치 후 **바탕화면에
JQSubtitle 아이콘**을 만들어 줍니다.

**방법 B — 수동 설치.**

1. [Python 3.10+](https://www.python.org/downloads/) 설치 (설치 시 "Add to PATH" 체크)
2. `jqsubtitle.py` 다운로드 후 더블클릭 또는:
   ```
   python jqsubtitle.py
   ```
3. 첫 실행 때 필요한 엔진(faster-whisper)이 자동 설치됩니다.

어느 방법이든 첫 자막 생성 때 Whisper 모델(~3GB)을 한 번 내려받습니다.

## 업데이트

v1.1부터는 프로그램이 시작할 때 새 버전을 확인하고, 있으면 클릭 한 번으로 업데이트한 뒤
자동으로 다시 시작합니다. **도움말 → 시작할 때 업데이트 확인**에서 끌 수 있고,
같은 메뉴에서 언제든 수동으로 확인할 수도 있습니다.

v1.0을 쓰고 계시면 위의 한 줄 설치 명령을 한 번만 다시 실행해 주세요. 그다음부터는
프로그램이 알아서 업데이트합니다.

## AI 엔진

프로그램에서 셋 중 하나를 고릅니다 — "끄기"는 없습니다. 문장 재조립·교정·번역이 전부
AI 단계라, 없이 돌리면 사실상 망가진 자막만 나오기 때문입니다. 편한 쪽으로 준비하세요:

- **Gemini (무료)** — [aistudio.google.com/apikey](https://aistudio.google.com/apikey)에서
  키를 발급받아 프로그램에 붙여넣기. 카드 등록 불필요. 무료 티어는 분당 요청 제한이 있는데
  걸리면 알아서 기다렸다 재시도합니다.
- **Claude (유료)** — [console.anthropic.com](https://console.anthropic.com/settings/keys)에서
  키 발급. 에피소드 1편 교정+번역에 보통 수십 원 수준.
- **로컬 AI (무료·오프라인)** — 프로그램에서 선택하고 설치 버튼을 누르면 Ollama와
  모델(~7.6GB, Gemma 4 12B)이 설치됩니다. NVIDIA GPU VRAM 10GB 이상 권장. 품질은 무료 API에
  근접하지만 VRAM이 부족하면 CPU로 흘러넘쳐 크게 느려집니다.
  인터넷 없이 작업해야 하거나 텍스트를 외부로 보내고 싶지 않을 때
  쓰세요.

키는 이 PC의 `config.json`에만 저장됩니다.

## 만든 사람

JQ Park이 만들었습니다. 어린이 STEM 애니메이션 유튜브 채널
**[sunny friends STEM](https://www.youtube.com/@sunnyfriends.science)** 도 함께 운영하고 있습니다.
JQSubtitle은 원래 그 영상들의 자막을 만들려고 시작한 도구입니다.

## 문의 · 후원

- 버그 제보/의견: [GitHub Issues](https://github.com/i3luegirl/jqsubtitle/issues)
- 도움이 됐다면: [PayPal로 후원하기](https://paypal.me/jqpark) ☕

## License

MIT License · © 2026 JQ Park
