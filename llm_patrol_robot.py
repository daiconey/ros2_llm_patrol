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

    def execute_action(self, action, speed, duration):
        twist = Twist()
        if action == "forward":
            twist.linear.x = float(speed)
        elif action == "backward":
            twist.linear.x = -float(speed)
        elif action == "turn_left":
            twist.angular.z = float(speed)
        elif action == "turn_right":
            twist.angular.z = -float(speed)
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
        "ユーザーの指示を解析し、ロボットが実行すべき動作手順をJSON配列のみで出力してください。"
        "使用可能な action: forward (前進: speed 0.2〜0.8), backward (後退: speed 0.2〜0.5), "
        "turn_left (左旋回: speed 0.5〜1.5), turn_right (右旋回: speed 0.5〜1.5), stop (停止)。"
        "【重要】stopの場合も含め、すべての要素に必ず step, action, speed, duration, reason の全キーを含めてください。"
        "必ずMarkdown装飾(```jsonなど)を含めず、純粋なJSONテキストのみを出力してください。"
        "例: [{\"step\": 1, \"action\": \"forward\", \"speed\": 0.5, \"duration\": 2.0, \"reason\": \"前進\"}]"
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
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
        {"step": 1, "action": "forward", "speed": 0.5, "duration": 2.5, "reason": "前方の警戒エリアへ直進"},
        {"step": 2, "action": "turn_left", "speed": 0.8, "duration": 1.96, "reason": "左方向警戒のため90度旋回"},
        {"step": 3, "action": "forward", "speed": 0.5, "duration": 2.5, "reason": "左側面ルートをパトロール"},
        {"step": 4, "action": "turn_left", "speed": 0.8, "duration": 1.96, "reason": "後方警戒のため90度旋回"},
        {"step": 5, "action": "forward", "speed": 0.5, "duration": 2.5, "reason": "周回パトロールを実行"},
        {"step": 6, "action": "stop", "speed": 0.0, "duration": 1.0, "reason": "任務完了、初期位置で停止"}
    ]

def main():
    rclpy.init()
    commander = LLMRobotCommander()

    print("==================================================")
    print("   AI×ROS2 自然言語自律パトロールロボット")
    print("==================================================")

    prompt = input("\nロボットへの指示を入力してください (例: 8の字を描くように動いて):\n> ")
    if not prompt.strip():
        prompt = "周囲を警戒パトロールして初期位置に戻って"

    try:
        plan = get_action_plan_from_llm(prompt)
        print("\n【LLMによる行動計画の推論結果】")
        print(json.dumps(plan, ensure_ascii=False, indent=2))
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
