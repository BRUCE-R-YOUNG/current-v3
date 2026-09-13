# 本日作成版の置き場

- `raspi/`: Raspberry Pi用。推論・画像蓄積・HTTP転送。
- `pc/`: PC用。受信・ダッシュボード・学習。
- `svl-raspi.zip`, `svl-pc.zip`: 初期配布用ZIP。トークン・モデル・ユーザーデータは含みません。
- `move-manifest.json`: 今回の移動元・移動先。

PCの本日作成した設定・トークン・受信DB・UI確認用仮想環境は `pc/` に引き継ぎました。モデル学習・推論の追加依存関係はPC側READMEを参照してください。

```powershell
cd pc
.\.venv\Scripts\python.exe run.py dashboard
```

ダッシュボード: http://127.0.0.1:8001/v3

現在の接続トークン: `pc/config/runtime/server/access-token.txt`

旧プロジェクト、旧モデル・画像、Gitリポジトリーは `../previous-versions/original-project-before-cleanup/` へ移動しています。全世代のコピーは同じ保管先の `backup-20260913-123719/` にあります。旧データは本日版のPCプロジェクトには自動投入していません。

旧 `../yolo-continuous-learning/` には、Windowsにより移動できなかった `.pytest_cache` と空の `raspi/` のみ残っています。旧フォルダーを使用中のアプリ・ターミナルが閉じられるまで、フォルダー自体の移動はできません。
