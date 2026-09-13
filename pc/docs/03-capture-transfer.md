# 3. Raspi: 推論なしキャプチャーと定期送信

モデルもUltralyticsも不要です。まずこのモードで接続とデータ収集を確認します。Raspberry Pi OS 64-bitを想定し、USBカメラなどOpenCV VideoCapture対応の入力を使います。CSIカメラのPicamera2専用入力は未実装です。

## インストールと設定
raspi フォルダで実行します。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

config/edge.yaml がない場合だけ config/capture-only.example.yaml をコピーして作成します。既存ファイルがある場合は直接編集し、上書きコピーしません。

|設定|意味|例|
|---|---|---|
|project_id|PCに作成済みのプロジェクトID|elevator-a|
|device_id|Piの識別名|raspi-01|
|camera|カメラ番号または動画入力URL|'0'|
|capture_seconds|保存の最短間隔（秒）|30|
|transfer_seconds|画像の送信処理間隔（秒）|300|
|server_url|PCのTailscale Serve HTTPS origin|実際のURL|
|duplicate_threshold|同じような画像の除外|0.02|
|roi|保存対象の領域、正規化座標|[0,0,1,1]|

一定間隔でも、類似画像・カメラ切断・容量上限の場合は保存しません。静止画像も毎回保存したい場合は duplicate_threshold: 0.0 にします。difficult_only は推論なしモードでは判定に使用しません。画像はデフォルトで長辺640pxへ縮小されるので、小さい階数表示の学習にはROIと解像度を検討してください。

## ターミナル1: キャプチャー
```bash
source .venv/bin/activate
python auto_capture.py --config config/edge.yaml
```

これは python run.py capture と同じ処理です。学習モデルをロードしません。停止はCtrl+C。短い確認なら --windows 2 を追加すると2ウィンドウで終了します（初期設定で約6秒）。画面プレビューは保存されますが、PiにGUIダッシュボードを起動するコマンドではありません。

## ターミナル2: 定期送信
```bash
source .venv/bin/activate
read -rsp 'PC access token: ' SVL_EDGE_TOKEN; echo
export SVL_EDGE_TOKEN
python check_connection.py --config config/edge.yaml
python periodic_transfer.py --config config/edge.yaml
```

起動直後に送信を試み、以後 transfer_seconds ごとに未送信画像を最大20件ずつ処理します。これは1回のHTTPへ20枚まとめる方式ではなく、画像ごとにPOSTします。滞留が増えた場合は間隔と予算を見直してください。

1回だけ送信処理を試す場合:
```bash
python periodic_transfer.py --config config/edge.yaml --once
```

--once の正常終了は全件配達の保証ではありません。失敗はキューに残り、予算不足や再試行待ちのイベントは送信しません。PCの受信件数とPiのDB内エラーを確認します。通信エラー後は永続化された指数バックオフと次の送信周期に従って再試行します。

## Pi起動時の自動実行
deploy/svl-capture.service と deploy/svl-transfer.service を用意しています。既定のユーザーpi・配置先 /home/pi/svl/raspi を実際のユーザーと絶対パスに変更します。設定変更後はサービスを再起動してください。

config/transfer.env を作成して以下を記載します。実際のトークンをGitに入れないでください。
```text
SVL_EDGE_TOKEN=PCで生成された実際のトークン
```

```bash
chmod 600 config/transfer.env
sudo cp deploy/svl-capture.service deploy/svl-transfer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now svl-capture svl-transfer
systemctl status svl-capture svl-transfer
journalctl -u svl-capture -u svl-transfer -f
```

手動実行とsystemdを重複起動しないでください。停止するには sudo systemctl stop svl-capture svl-transfer を使います。収集のみなら svl-capture だけを有効化できます。ネットワーク断でもキューが上限に達するまでは収集可能です。
