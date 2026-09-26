# RT Translator

Windows + CUDA 向けリアルタイム翻訳アプリ(完全ローカル / Web依存なし / Qt GUI)。

マイクまたはスピーカー出力(ループバック)をリアルタイムで文字起こしし、
言語ごとのフィルタルールに従って翻訳・表示します。ゲーム中に使える
常時最前面の字幕オーバーレイ付き。録音して後から高精度な再文字起こし、
話者分離、サマリー、エクスポートができます。

## 特徴

- **低遅延パイプライン**: キャプチャ → Silero VAD → faster-whisper(CTranslate2/CUDA)
  → 言語フィルタ → NLLB-200(CTranslate2) → 字幕/オーバーレイ
- **2モード**:
  - **エコ**: Whisper `base` int8 + 翻訳CPU。VRAM ~0.5GB。ゲーム併用向け
  - **フルパワー**: Whisper `large-v3-turbo` fp16 + beam5 + 話者分離。高精度
- **言語フィルタ**: 検出言語ごとに「無視 / 原文のみ / 翻訳」を設定
  (例: 日本語=スルー、英語=日本語へ翻訳)。未登録言語の既定動作も選べる
- **話者分離**: sherpa-onnx 話者埋め込みでライブ中に `SPEAKER_XX` 付与
  (フルパワーモード)。録音にはオフライン分離(pyannote-segmentation)
- **録音→分析**: 16kHz WAV + SQLite。後から任意モデルで再文字起こし、
  話者分離、抽出サマリー/キーワード/話者統計、txt/srt/json/md 出力
- **字幕オーバーレイ**: 半透明・ドラッグ移動・クリックスルー対応

## セットアップ

### 方法A: スタンドアロン版 (推奨・完全ポータブル)

`dist\RTTranslator\RTTranslator.exe` を実行するだけ。
**モデル・設定・録音すべてフォルダ内完結**(約3.7GB)。
`dist\RTTranslator-standalone.zip` を解凍すれば別PCでも
インストール・ダウンロード一切不要で動きます(NVIDIA GPU必須)。

**軽量版 (初回起動ダウンロード方式)**: `models\` を同梱しない
exeフォルダ(~1.2GB)でも動きます — 初回起動時に不足モデル一覧と
ダウンロードダイアログが出るので、そのままDLすればOK。
途中で切れても再実行で続きから再開します。

構成:
```
RTTranslator\
  RTTranslator.exe
  portable.txt          ポータブルモードのマーカー(消すと%APPDATA%使用に戻る)
  models\               NLLB / whisper-tiny,base,large-v3-turbo / 話者モデル
  data\                 初回起動で作成(設定・DB・録音がここに入る)
  _internal\            Python/Qt/CUDAランタイム
```

### 方法B: ソースから

```bat
cd E:\dev\rt-translator
uv venv .venv --python 3.12
uv pip install -r requirements.txt --python .venv\Scripts\python.exe
```

モデルのダウンロード(約1.5GB):

```bat
.venv\Scripts\python.exe tools\download_models.py all
```

個別: `nllb` / `speaker` / `segmentation` / `whisper <model名>`

GUIの「設定」タブにあるDLボタンからもダウンロードできます。
Whisper モデルは初回実行時に自動ダウンロードもされます。

## 起動

```bat
run.bat
```
または `dist\RTTranslator\RTTranslator.exe` / `.venv\Scripts\python.exe main.py`

## exe ビルド

```bat
uv pip install pyinstaller --python .venv\Scripts\python.exe
.venv\Scripts\pyinstaller.exe rt-translator.spec --clean --noconfirm
:: -> dist\RTTranslator\RTTranslator.exe (onedir, torch/cudnn除外で軽量化済)
```

## 診断

```bat
RTTranslator.exe --selftest
```
VAD/Whisper(CUDA)/NLLB/話者モデル/デバイス/DBを検査し
`%APPDATA%\RTTranslator\selftest.txt` にレポート出力。

## 使い方

1. **ライブ翻訳タブ**
   - 入力デバイスを選択(`[出力]`=ループバック/スピーカー音, `[マイク]`=マイク)
   - モードを選択(エコ/フルパワー)
   - 言語フィルタを設定(例: `en → 翻訳`, `ja → 原文のみ`)
   - 「開始」→「字幕オーバーレイ」で字幕表示
   - 「録音する」をONで開始すると録音+セグメントをDB保存
2. **録音・分析タブ**
   - 録音を選択 →「再文字起こし」(大きいモデル推奨)/「話者分離」/「サマリー」
   - エクスポート: txt / srt / json / md
3. **設定タブ**
   - モデルパス、モード別プリセット(モデル/量子化/beam/VAD感度)、
     キャプチャ設定、オーバーレイ外観、LLM(GGUF)パス

## モデル

| 用途 | モデル | サイズ |
|---|---|---|
| STT エコ | faster-whisper `base` (int8) | ~150MB |
| STT フル | faster-whisper `large-v3-turbo` (fp16) | ~1.6GB |
| 翻訳 | NLLB-200-distilled-600M (CT2 int8) | ~600MB |
| VAD | silero-vad ONNX (同梱) | ~2MB |
| 話者分離 | pyannote-segmentation-3-0 + 3dspeaker embedding | ~45MB |

## パフォーマンス目安 (RTX 3070)

- エコ: STT 30-80ms/セグメント + 翻訳 ~100ms(CPU) → 体感 ~1s
- フルパワー: STT 100-300ms + 翻訳 ~50ms(GPU) → 体感 1-2s
- 遅延は主に VAD の無音判定(エコ400ms/フル600ms)で決まります

## 任意: LLM要約

`llama-cpp-python` をインストールし、設定でGGUFパスを指定すると
サマリーにローカルLLMの要約も出力されます(未設定なら抽出式のみ)。

## 構成

```
main.py               エントリ
rttrans/
  capture.py          WASAPIキャプチャ(マイク+ループバック)
  vad.py              silero ONNX セグメンタ(torch不使用)
  stt.py              faster-whisper + ハルシネーションフィルタ
  translator.py       NLLB CT2 + sentencepiece
  speakers.py         話者埋め込み/オンラインクラスタ/オフライン分離
  pipeline.py         ライブパイプライン(スレッド+キュー)
  store.py            SQLite + WAV 書き出し
  analysis.py         再文字起こし/話者分離/サマリー/エクスポート
  summary.py          抽出サマリー/キーワード/話者統計 (+任意LLM)
  langs.py            言語テーブル(Whisper→NLLB)
  gui/                PySide6 (ライブ/録音/設定/オーバーレイ)
tools/download_models.py
tests/smoke.py        スモークテスト
```
