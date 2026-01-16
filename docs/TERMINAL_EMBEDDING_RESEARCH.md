# Terminal Embedding in Textual TUI - Windows Research

## Problem Statement

Attempting to embed a PTY terminal (running Claude Code) inside Ralph's Textual TUI on Windows. The terminal widget freezes or fails to display.

## Findings

### 1. PyWinpty

- **Source**: [pywinpty on PyPI](https://pypi.org/project/pywinpty/), [GitHub](https://github.com/andfoy/pywinpty)
- PyWinpty provides Windows pseudoterminal support using either native ConPTY or legacy winpty
- Basic test (`winpty.PTY(80, 24).spawn('cmd.exe')`) works fine
- Issue appears when integrating with async event loop in Textual

### 2. textual-terminal Package

- **Source**: [textual-terminal on PyPI](https://pypi.org/project/textual-terminal/)
- Third-party terminal emulator widget for Textual using Pyte
- Claims Windows 10/11 support
- Beta status (v0.3.0)
- Known to be "extremely slow" according to Textual maintainers because it fully emulates a terminal in Python

### 3. Textual Maintainers' Recommendation

- **Source**: [Textual Discussion #5461](https://github.com/Textualize/textual/discussions/5461)
- Creating a performant terminal widget is inherently complex
- Suggested workaround: Use **Log + Input/TextArea widgets** instead
  - Log widget for displaying output
  - Input widget for accepting commands with tab-completion

### 4. Known ConPTY Issues on Windows

- **Source**: [Microsoft Terminal Issues](https://github.com/microsoft/terminal/issues)

| Issue | Description |
|-------|-------------|
| [#17688](https://github.com/microsoft/terminal/issues/17688) | ConPTY hangs when calling `ClosePseudoConsole` - race condition |
| [#11276](https://github.com/microsoft/terminal/issues/11276) | ConPTY fails when parent process output is redirected |
| [#1965](https://github.com/microsoft/terminal/issues/1965) | Escape sequences written as literal characters initially |
| [#405](https://github.com/microsoft/terminal/issues/405) | Text wrapping issues - conhost wraps before sending to ConPTY |

### 5. VS Code / Textual Integration

- **Source**: [VS Code Issue #164800](https://github.com/microsoft/vscode/issues/164800)
- TUI apps (like Textual) have mouse/interaction issues under VS Code's terminal
- Tagged with `terminal-conpty` indicating ConPTY backend problems

## Options

### Option A: Use textual-terminal package
```bash
pip install textual-terminal
```
- Pros: Designed for this, claims Windows support
- Cons: Known to be slow, beta quality

### Option B: Log + Input approach
- Pros: Simple, reliable, uses native Textual widgets
- Cons: Not a full terminal, limited interactivity

### Option C: Side-by-side windows
- Run Ralph TUI in one terminal, Claude in another
- Pros: Most reliable, full Claude Code experience
- Cons: Not integrated

### Option D: Fix async PTY reading
- Wrap PTY reads in `asyncio.to_thread()` to avoid blocking event loop
- Tried but still froze - issue may be deeper in ConPTY/winpty

## Technical Details

### Why it freezes

The freeze likely occurs because:
1. ConPTY operations may block even when marked non-blocking
2. The Textual event loop gets blocked waiting for PTY data
3. Race conditions in ConPTY when handling rapid read/write

### Code that was tried

```python
# Wrapping PTY read in thread (didn't help)
async def _read_pty_data_windows(self) -> bytes:
    def do_read():
        if not self._pty.isalive():
            return None
        return self._pty.read(4096, blocking=False)

    result = await asyncio.to_thread(do_read)
    # ... still froze
```

## Recommendation

For Windows, the most practical approach is:

1. **Short term**: Run Claude in a separate terminal window alongside Ralph TUI
2. **Medium term**: Try the `textual-terminal` package with explicit Windows testing
3. **Long term**: Wait for Textual to potentially add official terminal widget support, or for ConPTY improvements from Microsoft

## References

- [PyWinpty GitHub](https://github.com/andfoy/pywinpty)
- [Textual Framework](https://github.com/Textualize/textual)
- [textual-terminal PyPI](https://pypi.org/project/textual-terminal/)
- [Microsoft Terminal ConPTY](https://github.com/microsoft/terminal)
- [Pyte Terminal Emulator](https://github.com/selectel/pyte)
