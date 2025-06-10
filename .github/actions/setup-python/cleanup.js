const {execSync} = require('child_process');

function run() {
  const venvPath = process.env['STATE_venvPath'];
  if (!venvPath) {
    console.log('No virtual environment to remove.');
    return;
  }
  try {
    console.log(`Removing virtual environment at ${venvPath}`);
    execSync(`rm -rf "${venvPath}"`, {stdio: 'inherit'});
  } catch (err) {
    console.error(err.message);
  }
}

run();
