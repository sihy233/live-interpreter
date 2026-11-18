from app.mt import build_prompt, clean_translation


def test_build_prompt():
    assert build_prompt("Hello.") == (
        "Translate the following segment into Chinese, "
        "without additional explanation.\n\nHello."
    )


def test_clean_translation():
    assert clean_translation("  你好。\n") == "你好。"
    assert clean_translation("Chinese: 你好。") == "你好。"
    assert clean_translation('"你好。"') == "你好。"
    assert clean_translation("中文：你好。") == "你好。"
