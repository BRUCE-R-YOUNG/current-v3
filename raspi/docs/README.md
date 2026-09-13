# Sustainable Vision Learning v3 運用ガイド

対象は current-v3 の独立した raspi / pc 配布版です。以前のバージョンは previous-versions に保管しています。

## 最初に進める順番
1. [PCの準備](01-pc.md): 受信サーバーを起動し、プロジェクトを作成。
2. [Tailscale VPN](02-tailscale.md): 別ネットワークのPCとRaspiを接続。
3. [推論なし収集・定期送信](03-capture-transfer.md): モデル不要で画像を蓄積・送信。
4. [推論と学習](04-inference-training.md): 必要になってからモデルを追加。
5. [障害対応・検証](05-troubleshooting.md): 送信失敗や容量不足を確認。

## 役割
|機能|実行する機器|単独起動|
|---|---|---|
|カメラ画像だけ収集|Raspi|auto_capture.py|
|キューから定期HTTP送信|Raspi|periodic_transfer.py|
|受信接続確認（送信なし）|Raspi|check_connection.py|
|推論しながら収集|Raspi|run.py production|
|受信・ダッシュボード|PC|run.py dashboard|
|受信画像の疑似ラベル生成|PC|run.py label|
|追加学習・評価|PC|run.py train|

キャプチャーと送信は別プロセスです。送信先が停止しても収集は継続しますが、保存上限に達すると収集は停止します。推論なし収集では人数・階数・方向・到着時間の集計は作成しません。

## 保存場所
各配布版の config/<設定名>.yaml に設定し、config/runtime/<設定名>/ にキューDB・実行状態・プレビューを保存します。同じ設定ファイルを収集・送信の両方に指定してください。異なる設定名は別キューです。

画像本体は events.sqlite3 のBLOBです。通常のJPEGフォルダへ連番保存する方式ではありません。preview.jpg は最新フレームだけで、学習用画像一覧ではありません。PC側のプロジェクト別データ・モデル・学習結果はプロジェクト管理設定に従います。

未送信データは再起動後も残ります。Piの送信処理は、作成から7日を超えた送信済みデータを削除します。未送信データは自動削除しません。PCの受信データはこの送信処理による自動削除の対象ではありません。

配布ZIPには個別設定、アクセストークン、モデル、データ、仮想環境を含めません。更新時に運用中の config/runtime を上書きしないでください。
