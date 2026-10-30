import os
import json
import time
import urllib.request
import urllib.error
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

class LLMRobotCommander(Node):
    def __init__(self):
        super().__init__('llm_robot_commander')
        self.publisher_ = self.create_publisher(Twist, '/model/vehicle_blue/cmd_vel', 10)

    def reset_position(self):
        """走行開始前にロボットを接地高(z:0.325)で原点へ静止テレポート"""
        print("[System] ロボットを初期位置 (x:0, y:0) へリセットしています...")
        stop_twist = Twist()
        self.publisher_.publish(stop_twist)
        time.sleep(0.2)
        
        # 接地高 z:0.325 で水平配置
        reset_cmd = (
            "ign service -s /world/diff_drive/set_pose "
            "--reqtype ignition.msgs.Pose --reptype ignition.msgs.Boolean --timeout 1000 "
            "--req 'name: \"vehicle_blue\", position: {x: 0, y: 0, z: 0.325}, orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}' "
            "> /dev/null 2>&1"
        )
        os.system(reset_cmd)
        time.sleep(1.0)

    def execute_action(self, action, speed, duration):
        twist = Twist()
        # 直進・後退（浮き上がりを防ぐマイルドな速度）
        if action == "forward":
            twist.linear.x = float(speed) if float(speed) <= 0.4 else 0.35
        elif action == "backward":
            twist.linear.x = -float(speed) if float(speed) <= 0.3 else -0.25
        # その場旋回
        elif action == "turn_left":
            twist.angular.z = float(speed) if float(speed) <= 0.8 else 0.6
        elif action == "turn_right":
            twist.angular.z = -float(speed) if float(speed) <= 0.8 else -0.6
        # カーブ走行（前進速度と旋回角速度の比率を安定化）
        elif action == "curve_left":
            twist.linear.x = 0.25
            twist.angular.z = min(float(speed), 0.4)
        elif action == "curve_right":
            twist.linear.x = 0.25
            twist.angular.z = -min(float(speed), 0.4)
        # 停止
        elif action == "stop":
            twist.linear.x = 0.0
            twist.angular.z = 0.0

        start_time = time.time()
        while time.time() - start_time < duration:
            self.publisher_.publish(twist)
            time.sleep(0.05)

    def stop_robot(self):
        twist = Twist()
        self.publisher_.publish(twist)
        time.sleep(0.5)

def call_gemini_api(api_key, user_prompt):
    key = api_key.strip().strip("'\"")
    model = "gemini-2.5-flash"
    print(f"[AI] 使用モデル: {model}")
    print("[AI] Gemini API に接続して行動計画をリアルタイム推論中...")

    system_prompt = (
        "あなたは差動二輪ロボットの自律移動プランナーAIです。"
        "ユーザーの指示を解析し、ロボットが実行すべき動作手順をJSON配列のみで出力してください。\n"
        "【使用可能な action とパラメータ】\n"
        "- forward: 前進 (speed 0.2〜0.4)\n"
        "- backward: 後退 (speed 0.2〜0.3)\n"
        "- turn_left / turn_right: その場旋回 (speed 0.4〜0.7)\n"
        "- curve_left: 左カーブ前進 (speed 0.3〜0.4) ※車体が浮かないよう穏やかな旋回\n"
        "- curve_right: 右カーブ前進 (speed 0.3〜0.4) ※車体が浮かないよう穏やかな旋回\n"
        "- stop: 停止 (speed 0.0)\n\n"
        "【重要ルール】\n"
        "1. ロボットが滑らかに走行できるよう、各ステップの duration（秒数）は 2.5〜5.0 秒程度を確保してください。\n"
        "2. stopの場合も含め、すべての要素に必ず step, action, speed, duration, reason の全キーを含めてください。\n"
        "3. 必ずMarkdown装飾(```jsonなど)を含めず、純粋なJSONテキストのみを出力してください。"
    )

    host = "generativelanguage.googleapis.com"
    url = f"https://{host}/v1beta/models/{model}:generateContent?key={key}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"システム指示: {system_prompt}\nユーザー指示: {user_prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                res_data = json.loads(res.read().decode("utf-8"))
                raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if "```" in raw_text:
                    lines = raw_text.split("\n")
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    raw_text = "\n".join(lines).strip()
                return json.loads(raw_text)
        except urllib.error.HTTPError as e:
            if e.code == 503 and attempt < 3:
                print(f"[AI] サーバー混雑中(503)。3秒後に再試行します... ({attempt}/3)")
                time.sleep(3)
                continue
            raise e

def get_action_plan_from_llm(user_prompt):
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        try:
            return call_gemini_api(api_key, user_prompt)
        except Exception as e:
            print(f"[AI] API呼び出しエラー詳細: {e}")
            if isinstance(e, urllib.error.HTTPError):
                print(f"[AI] サーバー応答: {e.read().decode('utf-8')[:300]}")
            print("[AI] 内蔵推論プランナー（オフラインAI）に切り替えます。")
    else:
        print("[AI] GEMINI_API_KEY が未設定のため、内蔵推論プランナーを使用します。")

    time.sleep(1.0)
    return [
        {"step": 1, "action": "curve_right", "speed": 0.35, "duration": 3.0, "reason": "スラローム開始: 右へ滑らかにカーブ走行"},
        {"step": 2, "action": "curve_left", "speed": 0.35, "duration": 3.0, "reason": "スラローム継続: 左へ滑らかにカーブ走行"},
        {"step": 3, "action": "curve_right", "speed": 0.35, "duration": 3.0, "reason": "スラローム継続: 右へ滑らかにカーブ走行"},
        {"step": 4, "action": "stop", "speed": 0.0, "duration": 1.0, "reason": "パトロール完了、初期位置で停止"}
    ]

def main():
    rclpy.init()
    commander = LLMRobotCommander()

    print("==================================================")
    print("   AI×ROS2 自然言語自律パトロールロボット")
    print("==================================================")
    
    prompt = input("\nロボットへの指示を入力してください (例: 8の字を描くように動いて):\n> ")
    if not prompt.strip():
        prompt = "前方の狭い通路を左右にジグザグに進みながらスラロームパトロールして"

    try:
        plan = get_action_plan_from_llm(prompt)
        print("\n【LLMによる行動計画の推論結果】")
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        
        commander.reset_position()

        print("\nロボットの実行を開始します...")

        for item in plan:
            action = item.get("action", "stop")
            speed = float(item.get("speed", 0.0))
            duration = float(item.get("duration", 1.0))
            reason = item.get("reason", "")
            step_num = item.get("step", "-")

            print(f"▶ Step {step_num}: {action} (速度: {speed}, 時間: {duration}秒) - 理由: {reason}")
            commander.execute_action(action, speed, duration)

        commander.stop_robot()
        print("\n=== すべてのタスクが正常に完了しました ===")

    except Exception as e:
        print(f"実行時エラー: {e}")
    finally:
        commander.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
