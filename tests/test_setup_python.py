def test_index_requires_macos(tmp_path):
    import subprocess, os, sys
    env = os.environ.copy()
    env['GITHUB_PATH'] = str(tmp_path / 'path')
    env['GITHUB_STATE'] = str(tmp_path / 'state')
    env['INPUT_PYTHON-VERSION'] = '3.11'
    env['INPUT_VENV-PATH'] = str(tmp_path / '.venv')
    result = subprocess.run(['node', '.github/actions/setup-python/index.js'],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert 'only runs on macOS' in result.stderr

def test_cleanup_removes_venv(tmp_path):
    import subprocess, os
    venv_dir = tmp_path / 'venv'
    bin_dir = venv_dir / 'bin'
    bin_dir.mkdir(parents=True)
    env = os.environ.copy()
    env['STATE_venvPath'] = str(venv_dir)
    result = subprocess.run(['node', '.github/actions/setup-python/cleanup.js'],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert not venv_dir.exists()
