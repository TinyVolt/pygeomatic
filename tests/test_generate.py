"""Prompt → python → DSL pipeline, exercised with fake `complete` callables."""

import pytest

import pygeomatic as gm
from pygeomatic.prompting import python_name


GOOD_REPLY = """\
Here you go:

```python
def build(gm):
    a = gm.point(1, 2, out="a")
    b = gm.point(4, 6)
    gm.distance(a, b)
    gm.highlight(a, b)
```
"""

BROKEN_REPLY = """\
```python
def build(gm):
    a = gm.point(1, 2, out="my_point")  # invalid id
```
"""

NO_BUILD_REPLY = """\
```python
x = 1
```
"""


def test_python_name_maps_every_keyword_to_an_export():
    for keyword, fdef in gm.REGISTRY.items():
        fn = getattr(gm, python_name(keyword))
        assert fn.geomatic is fdef, keyword


def test_system_prompt_documents_every_function():
    text = gm.system_prompt()
    for keyword in gm.REGISTRY:
        assert f"gm.{python_name(keyword)}(" in text, keyword
    assert "def build(gm):" in text
    assert "underscores" in text


def test_run_generated_success():
    result = gm.run_generated(gm.extract_code(GOOD_REPLY))
    assert result.ok
    assert result.dsl == [
        "a = \\point 1 2",
        "b = \\point 4 6",
        "num-0 = \\distance a b",
        "\\highlight a b",
    ]


def test_run_generated_reports_errors():
    result = gm.run_generated(gm.extract_code(BROKEN_REPLY))
    assert not result.ok
    assert "underscores" in result.error

    result = gm.run_generated(gm.extract_code(NO_BUILD_REPLY))
    assert not result.ok
    assert "build(gm)" in result.error


def test_run_generated_timeout():
    result = gm.run_generated("def build(gm):\n    while True: pass", timeout=1.5)
    assert not result.ok
    assert "timed out" in result.error


def test_generate_dsl_first_try():
    calls = []

    def complete(system, messages):
        calls.append((system, list(messages)))
        return GOOD_REPLY

    result = gm.generate_dsl("two points, distance, highlight", complete)
    assert result.attempts == 1
    assert result.dsl[0] == "a = \\point 1 2"
    system, messages = calls[0]
    assert "def build(gm):" in system
    assert messages == [{"role": "user", "content": "two points, distance, highlight"}]


def test_generate_dsl_retries_with_error_feedback():
    seen_errors = []

    def complete(system, messages):
        if len(messages) == 1:
            return BROKEN_REPLY
        seen_errors.append(messages[-1]["content"])
        return GOOD_REPLY

    result = gm.generate_dsl("scene", complete)
    assert result.attempts == 2
    assert result.dsl[-1] == "\\highlight a b"
    # the retry message contained the actual failure
    assert "underscores" in seen_errors[0]


def test_generate_dsl_exhausts_attempts():
    def complete(system, messages):
        return BROKEN_REPLY

    with pytest.raises(gm.GenerationError) as exc:
        gm.generate_dsl("scene", complete, max_attempts=2)
    assert len(exc.value.attempts) == 2


def test_extract_code_variants():
    assert gm.extract_code("```python\nx = 1\n```") == "x = 1"
    assert gm.extract_code("```\nx = 1\n```") == "x = 1"
    assert gm.extract_code("def build(gm):\n    pass") == "def build(gm):\n    pass"
