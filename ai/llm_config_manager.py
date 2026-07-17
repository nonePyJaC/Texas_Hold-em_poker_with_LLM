"""LLM 配置管理：从 GameApp 中抽离的 LLM 配置读写、测试、加载逻辑。"""

import os
import json


def _get_app_root():
    import sys
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LLMConfigManager:
    """LLM 配置控制器，持有 GameApp 引用。"""

    def __init__(self, app):
        self.app = app

    def read(self):
        """读取 LLM 配置文件"""
        config_path = os.path.join(_get_app_root(), "config", "llm_config.json")
        if not os.path.exists(config_path):
            return {}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self):
        """从设置界面读取并保存 LLM 配置"""
        app = self.app
        model_idx = app.settings_components["llm_model"].selected_index
        model = "deepseek-v4-pro" if model_idx == 1 else "deepseek-v4-flash"

        prob_idx = app.settings_components["llm_prob"].selected_index
        prob_values = [0.1, 0.3, 0.5, 0.8, 1.0]
        prob = prob_values[prob_idx]

        cfg = {
            "enabled": app.settings_components["llm_enabled"].selected_index == 1,
            "api_key": app.settings_components["llm_api_key"].text.strip(),
            "api_base": app.settings_components["llm_api_base"].text.strip() or "https://api.deepseek.com/v1",
            "model": model,
            "temperature": 0.8,
            "max_tokens": 100,
            "timeout": 5.0,
            "llm_probability": prob,
        }

        config_dir = os.path.join(_get_app_root(), "config")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "llm_config.json")

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            app._llm_test_result = "配置已保存!"
            app._llm_test_result_color = (80, 200, 80)
        except Exception as e:
            app._llm_test_result = f"保存失败: {e}"
            app._llm_test_result_color = (220, 80, 80)

    def test_connection(self):
        """测试 LLM API 连接"""
        app = self.app
        api_key = app.settings_components["llm_api_key"].text.strip()
        api_base = app.settings_components["llm_api_base"].text.strip() or "https://api.deepseek.com/v1"
        model_idx = app.settings_components["llm_model"].selected_index
        model = "deepseek-v4-pro" if model_idx == 1 else "deepseek-v4-flash"

        if not api_key:
            app._llm_test_result = "请先输入 API Key"
            app._llm_test_result_color = (220, 180, 60)
            return

        app._llm_test_result = "测试中..."
        app._llm_test_result_color = (180, 180, 60)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=api_base)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "说一个字：好"}],
                max_tokens=10,
                temperature=0.5,
                timeout=10.0,
            )
            reply = response.choices[0].message.content.strip()
            app._llm_test_result = f"连接成功! 回复: {reply}"
            app._llm_test_result_color = (80, 200, 80)
        except Exception as e:
            err = str(e)[:80]
            app._llm_test_result = f"连接失败: {err}"
            app._llm_test_result_color = (220, 80, 80)

    def load_bridge(self):
        """加载 LLM 配置并创建 LLMBridge

        读取 config/llm_config.json，如果 enabled 且有 api_key 则创建 LLMBridge。
        失败时返回 (None, 0.3)，游戏正常使用模板台词。

        Returns: (llm_bridge, llm_probability)
        """
        cfg = self.read()
        if not cfg:
            return None, 0.3

        llm_prob = cfg.get("llm_probability", 0.3)

        if not cfg.get("enabled") or not cfg.get("api_key"):
            return None, llm_prob

        try:
            from ai.dialogue_manager.providers.llm_bridge import LLMBridge, LLMConfig
            llm_config = LLMConfig(
                api_key=cfg["api_key"],
                api_base=cfg.get("api_base", "https://api.deepseek.com/v1"),
                model=cfg.get("model", "deepseek-v4-flash"),
                temperature=cfg.get("temperature", 0.8),
                max_tokens=cfg.get("max_tokens", 100),
                timeout=cfg.get("timeout", 5.0),
            )
            bridge = LLMBridge(config=llm_config)
            return bridge, llm_prob
        except Exception:
            return None, llm_prob
