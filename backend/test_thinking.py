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

        # A level is WHEN-gated (2026-10-11): on the default - "only when I
        # ask" - it is used on the questions the owner asks for thinking about
        # and nowhere else, so these checks put the model on "always" first.
        JT.set_when(JT.ALWAYS)

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

    def test_when_thinking_happens(self):
        """"Only when I ask" and "Always" (2026-10-11), and the safe default."""
        JT._CAP_OVERRIDE[("http://127.0.0.1:11434", "smart-model")] = ["thinking"]

        # Nothing chosen: answering directly, and an asked-for question thinks
        # briefly rather than not at all.
        self.assertEqual(JT.get_when(), JT.WHEN_ASKED)
        self.assertEqual(JT.reasoning_parameters("smart-model"), {"reasoning_effort": "none"})
        self.assertEqual(JT.reasoning_parameters("smart-model", per_turn=True),
                         {"reasoning_effort": "low"})

        # Always: an ordinary question thinks at the level that is set.
        JT.set_level("everyday", "deep")
        code, _out = JT.set_when(JT.ALWAYS)
        self.assertEqual(code, 200)
        self.assertEqual(JT.reasoning_parameters("smart-model"), {"reasoning_effort": "high"})

        # Back to only-when-asked: the level is kept, and used when asked for.
        code, _out = JT.set_when(JT.WHEN_ASKED)
        self.assertEqual(code, 200)
        self.assertEqual(JT.reasoning_parameters("smart-model"), {"reasoning_effort": "none"})
        self.assertEqual(JT.reasoning_parameters("smart-model", per_turn=True),
                         {"reasoning_effort": "high"})

        # A bad choice is refused in plain words and changes nothing.
        code, out = JT.set_when("sometimes")
        self.assertEqual(code, 400)
        self.assertIn("must be one of", out["error"])
        self.assertEqual(JT.get_when(), JT.WHEN_ASKED)

        # A model the owner set to answer directly is never overridden - not
        # even by a question that asked for thinking.
        JT.set_level("everyday", "off")
        self.assertEqual(JT.reasoning_parameters("smart-model", per_turn=True),
                         {"reasoning_effort": "none"})

    def test_a_damaged_setting_cannot_make_an_answer_blank(self):
        """A missing, empty or unreadable thinking.json reads as "only when I
        ask" - never as "always", which is the fault this setting exists to
        prevent (2026-10-11)."""
        self.assertEqual(JT.get_when(), JT.WHEN_ASKED)
        for damaged in ("", "{not json", '["a list, not an object"]',
                        '{"when": "sometimes"}'):
            JT.settings_path().write_text(damaged, encoding="utf-8")
            self.assertEqual(JT.get_when(), JT.WHEN_ASKED, repr(damaged))
            self.assertEqual(JT.get_level("everyday"), JT.OFF, repr(damaged))

    def test_asked_flag_is_the_apps_own_true_and_nothing_else(self):
        self.assertTrue(JT.asked_for_this_turn({"think": True}))
        for other in ({}, {"think": False}, {"think": "true"}, {"think": 1},
                      {"think": "yes"}, None, [], "think", True):
            self.assertFalse(JT.asked_for_this_turn(other), repr(other))

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

    def test_quick_words_for_when_thinking_happens(self):
        """"Always think" / "only think when I ask" (2026-10-11) - and the
        level commands saying which of the two they are on, so "from now on"
        never promises something the next answer will not do."""
        # A level set while on the default: used when asked for, and said so.
        JT.set_level("everyday", "quick")
        turn = _own_words("think harder")
        res = JQ.answer_turn(turn)
        self.assertIsNotNone(res)
        self.assertIn("thinking deeply", res.reply.lower())
        self.assertIn("questions you ask", res.reply)
        self.assertIn("always think", res.reply)
        self.assertEqual(JT.get_when(), JT.WHEN_ASKED)
        self.assertEqual(JT.get_level("everyday"), "deep")

        # The status line says the same thing.
        res = JQ.answer_turn(_own_words("thinking status"))
        self.assertIsNotNone(res)
        self.assertIn("only on the questions you ask", res.reply)

        # "always think": every answer may think first, said plainly.
        res = JQ.answer_turn(_own_words("always think"))
        self.assertIsNotNone(res)
        self.assertIn("every answer", res.reply.lower())
        self.assertIn("conversation room", res.reply)
        self.assertEqual(JT.get_when(), JT.ALWAYS)
        # On "always" the level command no longer warns.
        res = JQ.answer_turn(_own_words("think harder"))
        self.assertIsNotNone(res)
        self.assertNotIn("always think", res.reply)

        # ...and back, in the owner's own words for it.
        res = JQ.answer_turn(_own_words("only think when I ask"))
        self.assertIsNotNone(res)
        self.assertIn("only on the questions you ask", res.reply)
        self.assertEqual(JT.get_when(), JT.WHEN_ASKED)

        # A sentence that is none of these is not a command at all.
        self.assertFalse(JQ.is_command("think about whether I should buy a van"))


class TestThinkingAgentIntegration(unittest.TestCase):
    def setUp(self):
        JT.reset_for_tests()

    def tearDown(self):
        JT.reset_for_tests()

    def test_agent_chat_body_reasoning(self):
        import jarvis_agent
        JT._CAP_OVERRIDE[("http://127.0.0.1:11434", "test-think-model")] = ["thinking"]
        JT._CAP_OVERRIDE[("http://127.0.0.1:11434", "test-no-think-model")] = []

        # Model with thinking, level deep, on "always" - so this is the level
        # talking and not the WHEN setting (2026-10-11).
        JT.set_level("everyday", "deep")
        JT.set_when(JT.ALWAYS)
        body = jarvis_agent.chat_body("test-think-model", [{"role": "user", "content": "hello"}], {}, spoken=False, ollama_url="http://127.0.0.1:11434")
        self.assertEqual(body.get("reasoning_effort"), "high")

        # Spoken turn always overrides to none
        body_spoken = jarvis_agent.chat_body("test-think-model", [{"role": "user", "content": "hello"}], {}, spoken=True, ollama_url="http://127.0.0.1:11434")
        self.assertEqual(body_spoken.get("reasoning_effort"), "none")

        # Model without thinking gets reasoning_effort none (thinking off)
        body_no_think = jarvis_agent.chat_body("test-no-think-model", [{"role": "user", "content": "hello"}], {}, spoken=False, ollama_url="http://127.0.0.1:11434")
        self.assertEqual(body_no_think.get("reasoning_effort"), "none")

        # The owner's own question, on the default "only when I ask": the flag
        # chat_body is handed is what thinking follows.
        JT.set_when(JT.WHEN_ASKED)
        ordinary = jarvis_agent.chat_body("test-think-model", [{"role": "user", "content": "hello"}], {}, spoken=False, ollama_url="http://127.0.0.1:11434")
        self.assertEqual(ordinary.get("reasoning_effort"), "none")
        asked = jarvis_agent.chat_body("test-think-model", [{"role": "user", "content": "hello"}], {}, spoken=False, ollama_url="http://127.0.0.1:11434", per_turn=True)
        self.assertEqual(asked.get("reasoning_effort"), "high")


if __name__ == "__main__":
    unittest.main()
