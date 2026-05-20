import unittest

from engine import ChatMessage, RenderTag, SysrfxEngine


class SysrfxEngineTest(unittest.TestCase):
    def test_wraps_supported_tags(self):
        engine = SysrfxEngine()

        self.assertEqual(engine.wrap(RenderTag.CHAT, "привет"), "<ЧАТ>\nпривет\n</ЧАТ>")
        self.assertEqual(engine.monologue("Проверка"), "<МОНОЛОГ>\nЗадача: Проверка\n</МОНОЛОГ>")
        self.assertIn("<КОД>", engine.code("print('ok')"))
        self.assertEqual(engine.tools(["терминал открыт"]), "<ИНСТРУМЕНТЫ>\n[терминал открыт]\n</ИНСТРУМЕНТЫ>")

    def test_renders_group_chat_messages(self):
        engine = SysrfxEngine()
        output = engine.chat(
            [
                ChatMessage("erafox", "сделай движок", "12:00"),
                ChatMessage("Ден", "принял", "12:01"),
            ]
        )

        self.assertIn("erafox, 12:00\nсделай движок", output)
        self.assertIn("Ден, 12:01\nпринял", output)
        self.assertTrue(output.startswith("<ЧАТ>"))
        self.assertTrue(output.endswith("</ЧАТ>"))

    def test_reply_as_den_is_tagged_and_russian(self):
        engine = SysrfxEngine()
        output = engine.reply_as_den("проверь engine")

        self.assertIn("<ЧАТ>", output)
        self.assertIn("<МОНОЛОГ>", output)
        self.assertIn("Ден", output)
        self.assertIn("принял", output)

    def test_boot_does_not_double_wrap_status_actions(self):
        output = SysrfxEngine().boot()

        self.assertIn("[OK] engine ready", output)
        self.assertNotIn("[[OK]", output)


if __name__ == "__main__":
    unittest.main()
