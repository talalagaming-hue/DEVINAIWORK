# sysrfx-core

A small Python rendering engine that wraps structured log output into tagged
sections for downstream pipelines.

## Sections

| Builder method | Tag                  | Intended payload                          |
|----------------|----------------------|-------------------------------------------|
| `.chat(...)`        | `<ЧАТ>...</ЧАТ>`                 | Messages exchanged in the chat channel    |
| `.monologue(...)`   | `<МОНОЛОГ>...</МОНОЛОГ>`         | Internal technical reasoning notes        |
| `.code(...)`        | `<КОД>...</КОД>`                 | Source code blocks                        |
| `.tools(...)`       | `<ИНСТРУМЕНТЫ>...</ИНСТРУМЕНТЫ>` | Tool invocations and their results        |

The engine is purely a formatter — it does not execute anything and does not
drive any external behavior. It accepts strings, escapes XML-significant
characters (`&`, `<`, `>`), and emits a deterministic, line-delimited rendering
of the sections in the order they were appended.

## Usage

```python
from sysrfx_core.engine import ChatRenderer

rendered = (
    ChatRenderer()
    .chat("Привет, erafox.")
    .monologue("Need to confirm requirements before estimating.")
    .code("print('hello')")
    .tools("ls -la")
    .render()
)
print(rendered)
```

Output:

```
<ЧАТ>Привет, erafox.</ЧАТ>
<МОНОЛОГ>Need to confirm requirements before estimating.</МОНОЛОГ>
<КОД>print('hello')</КОД>
<ИНСТРУМЕНТЫ>ls -la</ИНСТРУМЕНТЫ>
```

Literal `<`, `>`, `&` inside section content are escaped to `&lt;`, `&gt;`,
`&amp;` so the rendered document is well-formed and round-trippable.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```
