# KonomiTV 最小連携スクリプト

このディレクトリは、KonomiTV のキャプチャ処理から AniCapShelf の
`POST /api/captures/annotated` へ画像と再生位置メタデータを送るための
最小クライアントを置く場所です。

現時点では、KonomiTV 本体へそのまま入る完成パッチではなく、
KonomiTV 側へ差し込むための小さな TypeScript クライアントです。
まず自分の録画PC環境で動作を確認し、安定したらパッチ化や配布方法を決めます。

## AniCapShelf API の起動

KonomiTV をブラウザで開いている origin を `--allow-origin` に指定します。
例では KonomiTV が `http://127.0.0.1:7000` で動いている想定です。

```powershell
python -m anicapshelf --db .\anicapshelf.db serve-api `
  --host 127.0.0.1 `
  --port 8765 `
  --allow-origin http://127.0.0.1:7000
```

Linux 側で動かす場合も考え方は同じです。KonomiTV を開いているブラウザから
到達できる AniCapShelf のURLを `endpoint` に指定します。

## 使い方のイメージ

KonomiTV のキャプチャ画像 Blob ができた直後に、
`uploadAnnotatedCapture()` を呼びます。既存の KonomiTV キャプチャ保存は
そのまま残し、AniCapShelf への送信に失敗しても視聴や通常保存を壊さない形にします。

```ts
import { uploadAnnotatedCapture } from "./anicapshelf-capture-client";

await uploadAnnotatedCapture({
  endpoint: "http://127.0.0.1:8765/api/captures/annotated",
  image: captureBlob,
  filename: captureFilename,
  recordedProgram: playerStore.recorded_program,
  playbackPositionSeconds: player.video.currentTime,
  quickTags: ["SNS候補"],
  konomitvUrl: window.location.href,
});
```

KonomiTV 側で最初に差し込む候補は `CaptureManager` 相当のキャプチャ完了直後です。
`recordedProgram` は `PlayerStore.recorded_program`、再生位置は
`player.video.currentTime` から取る想定です。

## クイックタグ

最小クライアントには、最初から次のクイックタグ候補を入れています。

- `SNS候補`
- `アイキャッチ`
- `OP`
- `ED`
- `名シーン`
- `要整理`

`quickTags` は `tags` と一緒に送れます。重複や空文字は AniCapShelf 側で
整理されます。

## 送信される主なメタデータ

- `source_app`: `KonomiTV`
- `captured_at`: キャプチャ送信時刻
- `recorded_program_id`: KonomiTV 側の録画番組ID
- `recorded_video_id`: KonomiTV 側の録画ファイルID
- `recording_file_path`: KonomiTV 側の録画ファイルパス
- `playback_position_seconds`: 動画内時刻
- `title`: 番組タイトル
- `series_title`: シリーズ名
- `episode_number`: 話数
- `subtitle`: サブタイトル
- `konomitv_url`: キャプチャ元ページURL

## 注意点

- `--allow-origin` は必要な KonomiTV origin だけに絞ります。
- AniCapShelf API を `0.0.0.0` で公開する場合は、家庭内LANの範囲や
  ファイアウォール設定を確認します。
- KonomiTV がコンテナ内パスを返す場合、AniCapShelf 側の録画パスと
  一致しない可能性があります。その場合は後でパスマッピングを追加します。
- ライブ視聴では録画ファイルIDや録画パスが取れない場合があります。
  最初は録画視聴画面を対象にします。
