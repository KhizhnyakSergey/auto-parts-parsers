from awe_tuning_parsing.description import html_to_text


def test_html_to_text_strips_scripts_and_joins_lines():
    html = "<div><p>Hello</p><script>evil()</script><p>World</p></div>"
    assert html_to_text(html) == "Hello\nWorld"


def test_html_to_text_handles_empty_input():
    assert html_to_text("") == ""
