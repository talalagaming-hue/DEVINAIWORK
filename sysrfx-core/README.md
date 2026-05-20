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
Forbidden C0 control characters (`\x00`–`\x08`, `\x0B`, `\x0C`, `\x0E`–`\x1F`)
and DEL (`\x7F`) are replaced with their `\uXXXX` escapes before XML
escaping. Tab, newline, and CR are preserved verbatim.

## Collector + CLI

The `Collector` class drives a `ChatRenderer` from an **injected** command
runner. The library ships no default execution behavior: importing the
collector never spawns a subprocess. Callers either supply their own
runner (e.g. a mock for tests) or opt into the bundled
`subprocess_runner`.

```python
from sysrfx_core import Collector, subprocess_runner

collector = Collector(runner=subprocess_runner)
collector.add_message("erafox: snapshot start", section="chat")
collector.add_command(["echo", "hello"], section="tools")
print(collector.render())
```

The `sysrfx-snap` console script wires `subprocess_runner` into a
`Collector` from the shell. It has no default commands — every command
must be passed explicitly via `--cmd SECTION:COMMAND`:

```bash
sysrfx-snap \
  --message chat:"erafox: review the snapshot" \
  --cmd tools:"echo hello" \
  --cmd code:"printf one-line"
```

`SECTION` must be one of `chat`, `monologue`, `code`, `tools`. `COMMAND`
is parsed with `shlex.split` by default; pass `--shell` to run it
through `/bin/sh -c` instead. The CLI exits with the worst non-zero
return code observed across all commands.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```
