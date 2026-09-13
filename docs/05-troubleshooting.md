# 5. 障害対応とテスト

|症状|確認と対応|
|---|---|
|camera frame not available / actual_framesが0|カメラ番号、USB接続、videoグループ権限、他プロセスの占有を確認。CSI専用入力は未対応|
|画像が少ない|capture_seconds、duplicate_threshold、ROI、保存容量を確認|
|401|PCで有効なSVL_EDGE_TOKENとPi側を一致させる。環境変数指定はPCトークンファイルより優先|
|404|project_idの登録漏れ、server_urlへ余計な /v3 を付けていないか確認|
|接続拒否/タイムアウト|PC起動、スリープ、tailscale status、tailscale ping、Serve statusを順に確認|
|HTTPS証明書エラー|正式なServeホスト名・時刻・CA証明書を確認。検証を無効化しない|
|送信処理は動くが画像が届かない|予算不足、再試行待ち、キューが別設定名、最大20件の周期制限を確認|
|Storage budget reached / 507|バックアップ後に運用データを整理。未送信DBを消して解決しない|
|train/val empty、ラベル欠落|dataset.yamlの参照先とlabelsを確認。画像追加だけでは学習できない|
|service lockエラー|同じ収集・送信サービスがすでに動いていないか確認|

## 実機での受け入れ確認
1. モデルパスを空欄にしてcaptureを実行し、画像が保存されることを確認。
2. PCとPiを別ネットワークでTailscaleへ接続し、check_connection.py が成功することを確認。
3. transfer --once 相当のコマンドを実行し、PC受信件数が増えることを確認。
4. PC受信を停止した状態で収集を続け、未送信が残ることを確認。
5. PCを再開し、再試行待ち時間・送信周期後に受信されることを確認。
6. Piの再起動後も保存データが残ること、systemdの両サービスが動くことを確認。

このWindows環境での自動テストは疑似カメラとローカルHTTPを使用します。Pi実機、異なるネットワーク、Tailscaleの実際のサインインは自動テストの対象外です。

## 開発テスト
current-v3 フォルダで実行します。
```powershell
python -m venv .venv-test
.\.venv-test\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv-test\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
.\.venv-test\Scripts\python.exe tools/package.py
```

配布ZIPはこのツールで再生成します。環境固有のconfig/runtime、モデル、トークン、.venvを除外した許可リスト方式です。docsはこのフォルダを正本とし、配布版のdocsへ同じ内容を同期します。
