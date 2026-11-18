from app.overlay import SubtitleState


def test_commit_and_clear():
    state = SubtitleState()
    state.commit("Hello.", "你好。")
    assert state.display() == ("Hello.", "你好。")
    state.clear_partial()
    assert state.display() == ("Hello.", "你好。")


def test_partial_overrides_and_falls_back_to_final():
    state = SubtitleState()
    state.commit("Hello.", "你好。")
    state.set_partial_en("Next sentence")
    assert state.display() == ("Next sentence", "你好。")
    state.set_partial_zh("下一句。")
    assert state.display() == ("Next sentence", "下一句。")
    state.commit("Next sentence", "下一句。")
    assert state.display() == ("Next sentence", "下一句。")
    assert state.partial_en == ""
    assert state.partial_zh == ""


def test_hide_english():
    state = SubtitleState(show_english=False)
    state.commit("Hello.", "你好。")
    assert state.display() == ("", "你好。")
