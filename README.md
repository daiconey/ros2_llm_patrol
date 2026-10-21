# ROS 2 × LLM Autonomous Patrol Robot

LLM（Gemini 2.5 Flash）と ROS 2（Humble）および物理シミュレータ（Gazebo）を統合し、自然言語指示から自律的なパトロール行動計画を動的に推論・実行するロボット制御システムです。

## 🎥 実証デモ動画 (YouTube)
- **YouTube Link**:https://youtu.be/MEllDi12MaA

## 📌 概要
ユーザーが自然言語（例：「前方の狭い通路をジグザグに進みながらパトロールして」）を入力すると、Gemini APIが差動二輪ロボットの物理的制約を考慮した制御パラメータ（直進速度・旋回角速度・継続時間）のシーケンスをJSON形式で推論生成します。
PythonベースのROS 2ノードがこの計画を受信・解析し、`/model/vehicle_blue/cmd_vel` トピックを介してGazeboシミュレータ上のロボットを実時間で自律走行させます。

## 🛠️ システム構成
- **OS**: Ubuntu 22.04 LTS (WSL2)
- **Middleware**: ROS 2 Humble
- **Simulator**: Gazebo Fortress (Ignition Gazebo 6)
- **LLM**: Google Gemini 2.5 Flash API (REST API連携)
- **Node**: Python 3.10 (`rclpy`, `geometry_msgs.msg.Twist`)

## 🚀 動作の流れ
1. **指示入力**: ターミナルから日本語でパトロール任務を入力。
2. **LLM推論**: システムプロンプトで差動二輪の運動制約を課されたGemini 2.5 Flashが、タスクを多段階の直進・旋回ステップに分解し、理由付きのJSONを出力。
3. **ROS 2パブリッシュ**: ノードが各ステップの目標速度（Twistメッセージ）を定周期発行。
4. **シミュレーション実行**: `ros_gz_bridge` を経由してGazebo上のロボットが自律走行を実行。

## 📁 主要ファイル
- `llm_patrol_robot.py`: LLM推論クライアントおよびROS 2自律走行制御ノード本体
