// Pre-compile wizard.jsx -> wizard.js (plain browser JS).
//
// The wizard UI used to compile JSX in the browser via @babel/standalone
// loaded from unpkg.com. That made the page blank whenever the browser could
// not reach the CDN (offline / InPrivate / corporate proxy). We now vendor
// React locally and ship a pre-compiled wizard.js, so the app needs zero
// internet access.
//
// Run this whenever you edit wizard.jsx:
//     node platform/frontend/build.js
//
// Requires only the vendored Babel (vendor/babel.min.js) — no npm install.

const fs = require('fs');
const path = require('path');

const dir = __dirname;
const Babel = require(path.join(dir, 'vendor', 'babel.min.js'));

const src = fs.readFileSync(path.join(dir, 'wizard.jsx'), 'utf8');
const { code } = Babel.transform(src, {
  presets: ['react', ['env', { targets: { esmodules: true } }]],
  compact: false,
});

fs.writeFileSync(path.join(dir, 'wizard.js'), code, 'utf8');
console.log(`✓ wrote wizard.js (${code.length} bytes) from wizard.jsx`);
