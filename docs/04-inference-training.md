# 4. 推論・疑似ラベル・追加学習

## Raspiで推論も行う場合
raspi フォルダで requirements-inference.txt を追加インストールし、config/edge.yaml に people_model と elevator_model の実在パスを設定します。モデルのクラス名と floor_map / up_classes / down_classes / people_classes を一致させます。

推論なしのcaptureプロセスを停止してから実行します。
```bash
python run.py production --config config/edge.yaml
```

送信プロセスは別に起動したまま使用します。production と capture は同時にカメラを占有できません。Pi4で3秒5フレームの実時間性能はモデル次第で、達成保証はありません。実際のフレーム数を確認してください。

## 集計の意味
- 3秒のウィンドウ内で最大5回、新しいフレームを推論します。
- 人数は画面内検出人数の平均です。入退場追跡や正確な在室人数とは異なります。
- 階数には平均と代表値、方向には投票結果を使います。平均階数は存在する階を表すとは限りません。
- 1階までの時間は最高階・階間移動秒数・各階停止秒数・折り返し時間に基づく仮定上の予測です。実際の呼び出しや運行予定は分かりません。
- 階数や方向が不明なら到着時間も推定できない場合があります。
- 画像には予測メタデータを付けますが、確定した教師ラベルとして扱いません。

画像周期は transfer_seconds、集計の送信処理周期は telemetry_seconds です。telemetry_seconds を延ばすだけでは3秒ごとの集計イベントの生成数は減りません。送信は最大20件ずつなので、長い周期ではキューが増える可能性があります。

## PCで疑似ラベル生成
PCで requirements-training.txt をインストールし、プロジェクトへ教師モデルを登録・選択してから実行します。
```powershell
.\.venv\Scripts\python.exe run.py label --config config/server.yaml
```

1回最大100件の未取り込み画像を処理し、人間レビュー必須の候補として登録します。無制限の定期学習ジョブではありません。

## PCで追加学習
config/server.yaml に project_id / dataset_yaml / epochs / imgsz / batch / workers / device を設定します。GUI設定も使用できます。学習元はプロジェクトで現在選択中のモデルです。

```powershell
.\.venv\Scripts\python.exe run.py train --config config/server.yaml
```

現在のv3学習は、ラベル付きtrain/valを持つ外部dataset.yamlの指定が必要です。受信画像を保存しただけでは学習対象になりません。レビューしたラベルを学習データへ反映してから実行してください。レビューからデータセットの自動更新までが完全自動でつながっている、と解釈しないでください。

## 更新条件
別の固定validationセットで既存モデルと候補を評価します。同一画像のtrain/val混入、学習中のデータ変更、現在モデルの変更、非有限な評価値では昇格を止めます。

promote_if_passed は初期値falseです。trueでも評価ポリシーに合格した場合だけPCの現在モデルを更新します。学習結果と比較はプロジェクトの runs/v3/<job_id>/report.json に残ります。

Piへのモデルの自動配布・切り替えは未実装です。PCで評価合格したモデルを別名でPiへ配置し、旧モデルを残して設定を変更・再起動してください。問題時は旧パスへ戻します。画像転送とモデル配布は別の処理です。
