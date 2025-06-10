# Setup Python via Homebrew

This action installs Python using Homebrew on macOS, creates a virtual environment, and removes it when the job completes.

## Inputs

- `python-version`: Version to install. The value is appended to the `python@` Homebrew formula (default `3.11`).
- `venv-path`: Directory where the virtual environment will be created (default `.venv`).

## Example

```yaml
- name: Setup Python
  uses: ./.github/actions/setup-python
  with:
    python-version: '3.11'
    venv-path: '.venv'
```
