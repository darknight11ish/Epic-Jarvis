"""test_thinking.py - Unit and integration tests for Section 5.5 per-model thinking levels."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import jarvis_thinking as JT
import jarvis_quick as JQ


class TestThinkingUnits(unittest.TestCase):
    def setUp(self):
        JT.reset_for_tests()

    def tearDown(self):
        JT.reset_for_tests()

    def test_default_levels(self):
        self.assertEqual(JT.get_level("everyday"), JT.OFF)
        self.assertEqual(JT.get_level("second"), JT.OFF)
        self.assertEqual(JT.get_level("third"), JT.OFF)

    def test_set_and_get_level(self):
        code, out = JT.set_level("everyday", "deep")
        self.assertEqual(code, 200)
        self.assertEqual(out["level"], "deep")
        self.assertEqual(JT.get_level("everyday"), "deep")

        # Invalid level
        code, out = JT.set_level("everyday", "super_deep")
        self.assertEqual(code, 400)
        self.assertIn("must be one of", out["error"])

    def test_capabilities_and_supported_levels(self):
        # Override capabilities for test models
        JT._CAP_OVERRIDE[("http://127.0.0.1:11434", "smart-model")] = ["tools", "thinking"]
        JT._CAP_OVERRIDE[("http://127.0.0.1:11434", "plain-model")] = ["tools"]

        self.assertTrue(JT.supports_thinking("smart-model"))
        self.assertFalse(JT.supports_thinking("plain-model"))

        self.assertEqual(JT.supported_levels("smart-model"), (JT.OFF, JT.QUICK, JT.DEEP, JT.AUTO))
        self.assertEqual(JT.supported_levels("plain-model"), (JT.OFF,))

        # Setting unsupported level on plain-model must fail in plain words
        code, out = JT.set_level("everyday", "deep", model_name="plain-model")
        self.assertEqual(code, 400)
        self.assertIn("does not support thinking controls", out["error"])

        # Setting off must succeed
        code, out = JT.set_level("everyday", "off", model_name="plain-model")
        self.assertEqual(code, 200)

        # Setting deep on smart-model must succeed
        code, out = JT.set_level("everyday", "deep", model_name="smart-model")
        self.assertEqual(code, 200)

    def test_decide_auto(self):
        # Greetings and simple phrases -> off
        self.assertEqual(JT.decide_auto("hi"), JT.OFF)
        self.assertEqual(JT.decide_auto("hello jarvis, how are you?"), JT.OFF)
        self.assertEqual(JT.decide_auto("what time is it?"), JT.OFF)

        # Analytical / comparison -> quick
        self.assertEqual(JT.decide_auto("compare and contrast sqlite and postgresql for local apps"), JT.QUICK)
        self.assertEqual(JT.decide_auto("what are the pros and cons of using webview vs native compose?"), JT.QUICK)

        # Math / logic / debugging -> deep
        self.assertEqual(JT.decide_auto("solve the equation 3x^2 - 12x + 9 = 0 step by step"), JT.DEEP)
        self.assertEqual(JT.decide_auto("why is this bug causing a deadlock in my multi-threaded worker?"), JT.DEEP)
        self.assertEqual(JT.decide_auto("debug this python script and trace this memory leak"), JT.DEEP)

    def test_reasoning_parameters(self):
        JT._CAP_OVERRIDE[("http://127.0.0.1:11434", "smart-model")] = ["thinking"]
        JT._CAP_OVERRIDE[("http://127.0.0.1:11434", "plain-model")] = []

        # Plain model without thinking gets reasoning_effort none (thinking off)
        self.assertEqual(JT.reasoning_parameters("plain-model"), {"reasoning_effort": "none"})

        # Voice answers (spoken=True) are always fast
        JT.set_level("everyday", "deep")
        self.assertEqual(JT.reasoning_parameters("smart-model", spoken=True), {"reasoning_effort": "none"})

        # Text answers follow configured level
        JT.set_level("everyday", "off")
        self.assertEqual(JT.reasoning_parameters("smart-model", spoken=False), {"reasoning_effort": "none"})

        JT.set_level("everyday", "quick")
        self.assertEqual(JT.reasoning_parameters("smart-model", spoken=False), {"reasoning_effort": "low"})

        JT.set_level("everyday", "deep")
        self.assertEqual(JT.reasoning_parameters("smart-model", spoken=False), {"reasoning_effort": "high"})

        # Auto level
        JT.set_level("everyday", "auto")
        params_simple = JT.reasoning_parameters("smart-model", question="hello jarvis", spoken=False)
        self.assertEqual(params_simple, {"reasoning_effort": "none"})

        params_math = JT.reasoning_parameters("smart-model", question="solve the complex integral proof", spoken=False)
        self.assertEqual(params_math, {"reasoning_effort": "high"})

    def test_handle_get_and_set(self):
        code, data = JT.handle_get()
        self.assertEqual(code, 200)
        self.assertIn("models", data)
        self.assertIn("notice", data)

        # Post valid change
        code, out = JT.handle_set({"role": "everyday", "level": "quick"})
        self.assertEqual(code, 200)
        self.assertEqual(JT.get_level("everyday"), "quick")

        # Post invalid change
        code, out = JT.handle_set({"role": "everyday", "level": "invalid"})
        self.assertEqual(code, 400)


def _own_words(text, cid="conv-thinking1", temporary=None):
    body = {"messages": [{"role": "user", "content": text, "provenance": "typed"}],
            "conversation_id": cid}
    if temporary is not None:
        body["temporary"] = temporary
    return body


class TestThinkingQuickCommands(unittest.TestCase):
    def setUp(self):
        JT.reset_for_tests()

    def tearDown(self):
        JT.reset_for_tests()

    def test_quick_phrases(self):
        # "think harder"
        turn = _own_words("think harder")
        res = JQ.answer_turn(turn)
        self.assertIsNotNone(res)
        self.assertIn("thinking deeply", res.reply.lower())
        self.assertEqual(JT.get_level("everyday"), "deep")

        # "think fast"
        turn = _own_words("think fast")
        res = JQ.answer_turn(turn)
        self.assertIsNotNone(res)
        self.assertIn("quick thinking", res.reply.lower())
        self.assertEqual(JT.get_level("everyday"), "quick")

        # "stop thinking"
        turn = _own_words("stop thinking")
        res = JQ.answer_turn(turn)
        self.assertIsNotNone(res)
        self.assertIn("thinking is off", res.reply.lower())
        self.assertEqual(JT.get_level("everyday"), "off")

        # "think automatically"
        turn = _own_words("think automatically")
        res = JQ.answer_turn(turn)
        self.assertIsNotNone(res)
        self.assertIn("automatic thinking", res.reply.lower())
        self.assertEqual(JT.get_level("everyday"), "auto")

        # "thinking status"
        turn = _own_words("thinking status")
        res = JQ.answer_turn(turn)
        self.assertIsNotNone(res)
        self.assertIn("thinking is currently", res.reply.lower())

        # "from now on, think harder"
        turn = _own_words("from now on, think harder")
        res = JQ.answer_turn(turn)
        self.assertIsNotNone(res)
        self.assertIn("thinking deeply", res.reply.lower())
        self.assertEqual(JT.get_level("everyday"), "deep")


class TestThinkingAgentIntegration(unittest.TestCase):
    def setUp(self):
        JT.reset_for_tests()

    def tearDown(self):
        JT.reset_for_tests()

    def test_agent_chat_body_reasoning(self):
        import jarvis_agent
        JT._CAP_OVERRIDE[("http://127.0.0.1:11434", "test-think-model")] = ["thinking"]
        JT._CAP_OVERRIDE[("http://127.0.0.1:11434", "test-no-think-model")] = []

        # Model with thinking, level deep
        JT.set_level("everyday", "deep")
        body = jarvis_agent.chat_body("test-think-model", [{"role": "user", "content": "hello"}], {}, spoken=False, ollama_url="http://127.0.0.1:11434")
        self.assertEqual(body.get("reasoning_effort"), "high")

        # Spoken turn always overrides to none
        body_spoken = jarvis_agent.chat_body("test-think-model", [{"role": "user", "content": "hello"}], {}, spoken=True, ollama_url="http://127.0.0.1:11434")
        self.assertEqual(body_spoken.get("reasoning_effort"), "none")

        # Model without thinking gets reasoning_effort none (thinking off)
        body_no_think = jarvis_agent.chat_body("test-no-think-model", [{"role": "user", "content": "hello"}], {}, spoken=False, ollama_url="http://127.0.0.1:11434")
        self.assertEqual(body_no_think.get("reasoning_effort"), "none")


if __name__ == "__main__":
    unittest.main()
