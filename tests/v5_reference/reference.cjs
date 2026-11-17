// GPL-3.0-only: deterministic offline reference for cross-language V5 signing.
'use strict';
const fs = require('node:fs');
const crypto = require('node:crypto');
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
let counter = 0;
crypto.randomBytes = n => Buffer.alloc(n, ++counter);
Date.now = () => data.now;
const { signPlaybackV5 } = require('./playback-v5');
const result = signPlaybackV5({
  base: data.base,
  values: data.values,
  body: Buffer.from(data.body, 'base64'),
  now: data.now,
});
process.stdout.write(JSON.stringify(result));
