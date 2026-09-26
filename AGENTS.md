# RT Translator — 開発メモ

Windows + CUDA 向けローカルリアルタイム翻訳 (PySide6 GUI)。

## コマンド

```bat
:: 環境構築
uv venv .venv --python 3.12
uv pip install -r requirements.txt --python .venv\Scripts\python.exe

:: モデル一括DL (NLLB/話者/セグメンテーション/whisper)
.venv\Scripts\python.exe tools\download_models.py all

:: 起動
run.bat   (= .venv\Scripts\python.exe main.py)

:: テスト
.venv\Scripts\python.exe tests\smoke.py   :: 構文/デバイス/VAD/DB/GUI(offscreen)
.venv\Scripts\python.exe tests\e2e.py     :: 実モデルE2E (要モデルDL済)
```

## 注意点

- **-X utf8 を付けて実行しない**: ユーザーのHFトークンファイルがCP932のため
  huggingface_hub の stored_tokens 読込で落ちる。通常起動は問題なし。
- ctranslate2 は cuBLAS/cuDNN を同梱しない → `nvidia-cublas-cu12` /
  `nvidia-cudnn-cu12` を requirements に含め、`rttrans/cudaenv.py` が
  `os.add_dll_directory` で site-packages/nvidia/*/bin を登録する。
- silero-vad 6.x は torch 依存のラッパーだが、`rttrans/vad.py` は同梱ONNXを
  onnxruntime で直接駆動し torch を実行時に使わない(エコモードの軽量化)。
  onnx実体は `rttrans/assets/silero_vad.onnx` に同梱(exe用)。
- ctranslate2 の推論で実際に必要なのは `cublas64_12.dll`+`cublasLt64_12.dll`
  のみ(推論時ロード確認済)。cuDNNはCT2が静的リンク同梱のため
  `nvidia-cudnn-cu12` は**インストール不要**(1.4GB削減)。
- exe: `tools/build_package.py` (pyinstaller + portable.txt + models/
  + 3分割zip を一括実行)。COLLECTは dist/RTTranslator を毎回消すので
  pyinstaller単体実行後は必ず `build_package.py --assemble` で再配置。
  torch/silero_vad等は spec で exclude 済。
- `main.py --selftest` : 非GUI診断(モデル/デバイス/DB) → selftest.txt。
- 初回起動DL: `modeldl.missing_models/ensure_models` が不足分だけDL。
  portable時whisperは `models/whisper-<name>` へ `output_dir` 直DL。
  GUIは `gui/model_dialog.py` のダイアログを app 起動時に自動表示。
- 設定・モデル・DB は `%APPDATA%\RTTranslator\` 配下。録音WAVは設定の record_dir。
- **ポータブルモード**: exe隣に `portable.txt` があれば config/models/data を
  exe基準に解決(`config.portable_root`)。whisperは `models/whisper-<name>`
  ディレクトリを `cfg.resolve_whisper` が名前解決(HF不要・完全オフライン)。
  `dist/RTTranslator` はマーカー+モデル同梱済みの配布パッケージ。
- コンソール出力の日本語はCP932で文字化けするがGUI表示は正常。
