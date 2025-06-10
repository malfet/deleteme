const {execSync} = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function run() {
  try {
    if (process.platform !== 'darwin') {
      console.error('This action only runs on macOS.');
      process.exit(1);
    }

    const pythonVersion = process.env['INPUT_PYTHON-VERSION'] || '3.11';
    const venvPath = process.env['INPUT_VENV-PATH'] || '.venv';
    const formula = `python@${pythonVersion}`;

    execSync(`brew install ${formula}`, {stdio: 'inherit'});
    const prefix = execSync(`brew --prefix`, {encoding: 'utf8'}).trim();
    const pythonBin = path.join(prefix, 'bin', `python${pythonVersion}`);

    console.log(`Using python at ${pythonBin}`);
    execSync(`"${pythonBin}" -m venv "${venvPath}"`, {stdio: 'inherit'});

    fs.appendFileSync(process.env['GITHUB_PATH'], path.join(venvPath, 'bin') + os.EOL);
    fs.appendFileSync(process.env['GITHUB_STATE'], `venvPath=${venvPath}${os.EOL}`);
  } catch (err) {
    console.error(err.message);
    process.exit(1);
  }
}

run();
