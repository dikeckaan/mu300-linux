// site/assets/web-installer/audio.js: the call audio package as a sponsor receives it (a zip with mu300-audio.tar.gz
// and SHA256SUMS), checked in the browser before anything is sent; and the package service, which is not wired yet.
import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import zlib from "node:zlib";

import { AudioError, fetchAudioPackage, readAudioPackage, untar } from "../../site/assets/web-installer/audio.js";

const sha = (b) => crypto.createHash("sha256").update(b).digest("hex");

function makeZip(files) {
  const locals = [], central = [];
  let off = 0;
  for (const [name, data] of files) {
    const raw = Buffer.from(data), body = zlib.deflateRawSync(raw), n = Buffer.from(name);
    const lh = Buffer.alloc(30);
    lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(8, 8);
    lh.writeUInt32LE(body.length, 18); lh.writeUInt32LE(raw.length, 22); lh.writeUInt16LE(n.length, 26);
    locals.push(lh, n, body);
    const ch = Buffer.alloc(46);
    ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(8, 10); ch.writeUInt32LE(body.length, 20); ch.writeUInt32LE(raw.length, 24);
    ch.writeUInt16LE(n.length, 28); ch.writeUInt32LE(off, 42);
    central.push(ch, n);
    off += 30 + n.length + body.length;
  }
  const cd = Buffer.concat(central), eocd = Buffer.alloc(22);
  eocd.writeUInt32LE(0x06054b50, 0); eocd.writeUInt16LE(files.length, 8); eocd.writeUInt16LE(files.length, 10);
  eocd.writeUInt32LE(cd.length, 12); eocd.writeUInt32LE(off, 16);
  return new Blob([Buffer.concat([...locals, cd, eocd])]);
}

// a ustar archive: [name, data | null (a directory), type]
function makeTar(entries) {
  const out = [];
  for (const [name, data, type] of entries) {
    const body = data === null ? Buffer.alloc(0) : Buffer.from(data);
    const h = Buffer.alloc(512);
    h.write(name, 0, 100);
    h.write("0000644\0", 100); h.write("0000000\0", 108); h.write("0000000\0", 116);
    h.write(body.length.toString(8).padStart(11, "0") + "\0", 124);
    h.write("00000000000\0", 136);
    h.write(type || (data === null ? "5" : "0"), 156);
    h.write("ustar\0", 257); h.write("00", 263);
    h.write("        ", 148);
    let sum = 0; for (const b of h) sum += b;
    h.write(sum.toString(8).padStart(6, "0") + "\0 ", 148);
    out.push(h, body, Buffer.alloc((512 - (body.length % 512)) % 512));
  }
  out.push(Buffer.alloc(1024));
  return Buffer.concat(out);
}

function audioFiles(o = {}) {
  const files = {
    "./name": "mu300-audio\n", "./release": "v1.2.0\n", "./components": "mu300-audio v1.2.0\n",
    "./bin/mu300-audio-dsp": "#!/bin/sh\n", "./bin/mu300-voice": "#!/bin/sh\n",
    "./hooks/link": "#!/bin/sh\n", "./hooks/unlink": "#!/bin/sh\n",
    "./modules/7.3.0/KERNEL": "KEY=7.3\nKREL=7.3.0\nCONFIG=" + "c".repeat(64) + "\nTAG=v2026.10.29.1\n",
    "./modules/7.3.0/saudio.ko": "ko", "./modules/6.18.59/KERNEL": "KEY=6.18\nKREL=6.18.59\nCONFIG=" + "d".repeat(64) + "\n",
    ...o,
  };
  for (const k of Object.keys(files)) if (files[k] === undefined) delete files[k];
  return files;
}
function audioTar(files, { manifest = true, extra = [] } = {}) {
  const entries = [["./", null], ["./bin/", null], ["./hooks/", null], ["./modules/", null], ["./modules/7.3.0/", null], ["./modules/6.18.59/", null]];
  for (const [n, d] of Object.entries(files)) entries.push([n, d]);
  if (manifest) entries.push(["./manifest", Object.entries(files).map(([n, d]) => `${sha(Buffer.from(d))}  ${n}\n`).join("")]);
  return zlib.gzipSync(makeTar([...entries, ...extra]));
}
function audioZip(tgz, { sums, top = "mu300-audio-v1.2.0/" } = {}) {
  return makeZip([[top + "mu300-audio.tar.gz", tgz], [top + "SHA256SUMS", sums ?? `${sha(tgz)}  mu300-audio.tar.gz\n`],
    [top + "VERSIONS", "mu300-audio\tv1.2.0\n"], [top + "README.txt", "readme\n"]]);
}

test("a sponsor's zip: checked, its tarball and checksum for the device, the kernels it has drivers for", async () => {
  const tgz = audioTar(audioFiles());
  const r = await readAudioPackage(audioZip(tgz), { kernel: "7.3" });
  assert.equal(r.release, "v1.2.0");
  assert.equal(r.sha256, sha(tgz));
  assert.equal(r.fits, true);
  assert.deepEqual(r.kernels.map((k) => `${k.key}:${k.krel}`), ["6.18:6.18.59", "7.3:7.3.0"]);
  assert.deepEqual(Buffer.from(await r.tarball.arrayBuffer()), tgz);
  // the files at the top of the zip are read the same
  assert.equal((await readAudioPackage(audioZip(tgz, { top: "" }), { kernel: "7.3" })).release, "v1.2.0");
  // no drivers for that kernel: usable, but it does not fit
  assert.equal((await readAudioPackage(audioZip(tgz), { kernel: "5.4" })).fits, false);
  // no firmware in it is fine (the firmware may come from the user's own device)
  assert.ok(!r.kernels.some((k) => k.krel === "firmware"));
});

test("what is not a usable audio package is refused with a reason", async () => {
  const code = (c) => (e) => e instanceof AudioError && e.code === c;
  const good = audioTar(audioFiles());
  await assert.rejects(readAudioPackage(new Blob(["hello"])), code("not-a-zip"));
  await assert.rejects(readAudioPackage(makeZip([["x/readme.txt", "hi"]])), code("not-audio"));
  await assert.rejects(readAudioPackage(makeZip([["x/mu300-audio.tar.gz", good]])), code("no-sums"));
  await assert.rejects(readAudioPackage(audioZip(good, { sums: `${"0".repeat(64)}  mu300-audio.tar.gz\n` })), code("damaged"));
  await assert.rejects(readAudioPackage(audioZip(good, { sums: `${sha(good)}  other.tar.gz\n` })), code("no-sums"));
  await assert.rejects(readAudioPackage(audioZip(Buffer.from("not gzip"))), code("bad-tarball"));
  await assert.rejects(readAudioPackage(audioZip(audioTar(audioFiles({ "./name": "vpn\n" })))), code("not-audio"));
  await assert.rejects(readAudioPackage(audioZip(audioTar(audioFiles({ "./hooks/link": undefined })))), code("bad-tarball"));
  await assert.rejects(readAudioPackage(audioZip(audioTar(audioFiles(), { manifest: false }))), code("bad-tarball"));
  // a file the manifest does not name, a file that is not what it says, a link, a name that climbs out
  const files = audioFiles();
  const manifest = Object.entries(files).map(([n, d]) => `${sha(Buffer.from(d))}  ${n}\n`).join("");
  const tamper = zlib.gzipSync(makeTar([...Object.entries({ ...files, "./bin/mu300-voice": "evil" }), ["./manifest", manifest]]));
  await assert.rejects(readAudioPackage(audioZip(tamper)), code("bad-tarball"));
  await assert.rejects(readAudioPackage(audioZip(audioTar(files, { extra: [["./bin/extra", "x"]] }))), code("bad-tarball"));
  await assert.rejects(readAudioPackage(audioZip(audioTar(files, { extra: [["./bin/sh", "", "2"]] }))), code("bad-tarball"));
  assert.throws(() => untar(makeTar([["../etc/passwd", "x"]])), code("bad-tarball"));
});

test("the package service is not wired yet: it says so, and fetches nothing", async () => {
  await assert.rejects(fetchAudioPackage({ licenceKey: "K", deviceCode: "0123456789abcdef", turnstileToken: null }), (e) => e instanceof AudioError && e.code === "not-available");
});
