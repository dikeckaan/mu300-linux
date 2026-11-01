// The call audio package (mu300-audio): given to sponsors, and added by this page only (the installers for
// computers never download it). Two parts, kept apart on purpose:
//
//   fetchAudioPackage(request)  where the package comes from: a licence key and a Turnstile check against the
//                               package service. NOT WIRED YET: it says so (AudioError "not-available") until the
//                               service's interface is set; a developer (?dev) may pick a local zip instead.
//   readAudioPackage(blob, opt) what the page accepts, whatever it came from: the zip as sponsors get it - one folder
//                               (or its files at the top) with mu300-audio.tar.gz and SHA256SUMS - checked here before
//                               anything is sent: the tarball against SHA256SUMS; inside it plain files and
//                               directories only, ./name mu300-audio, one ./release, ./manifest naming every other
//                               file with its sha256, the extra's programs and hooks; which kernels its drivers are for.
//
// The device checks the manifest again when it unpacks the extra (android-install.sh, mu300-extra), keeps whatever
// firmware the package may carry for root alone, and each system links the extra into itself at its first boot.
import { openZip, ZipError } from "./zip.js";
import { Sha256 } from "./sha256.js";

export const AUDIO_NAME = "mu300-audio";
export const SPONSOR_URL = "https://github.com/sponsors/dikeckaan";
export const FORM_URL = "https://kaandikec.com";
export const MIN_SPONSOR_USD = 10;
const TARBALL = "mu300-audio.tar.gz";
const MAX_TARBALL = 100 * 1024 * 1024;        // android-web.sh's bound for an extra (EXTRA_MAX)
const MAX_UNPACKED = 600 * 1024 * 1024;       // mu300-extra's own (extra_size_ok)
const ENTRY = /^[A-Za-z0-9_+-][A-Za-z0-9._+-]*(\/[A-Za-z0-9_+-][A-Za-z0-9._+-]*){0,3}$/;
const NEEDED = ["bin/mu300-audio-dsp", "bin/mu300-voice", "hooks/link", "hooks/unlink"];
const dec = new TextDecoder("utf-8", { fatal: false });

export class AudioError extends Error {
  // code: a word the page has a sentence for (strings.js "audio.err.<code>")
  constructor(code, detail) { super(detail ? `${code}: ${detail}` : code); this.name = "AudioError"; this.code = code; this.detail = detail || ""; }
}

// fetchAudioPackage({ licenceKey, deviceCode, turnstileToken, signal }) -> Blob (the zip, as readAudioPackage takes
// it). The one place the package service is called from; until it is wired, nothing is fetched.
export async function fetchAudioPackage(request = {}) {
  void request;
  throw new AudioError("not-available");
}

const hex = (bytes) => { const h = new Sha256(); h.update(bytes); return h.hex(); };

async function gunzip(bytes, limit) {
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip")).getReader();
  const parts = [];
  let n = 0;
  for (;;) {
    let r;
    try { r = await reader.read(); } catch (e) { throw new AudioError("bad-tarball", "not a gzip"); }
    if (r.done) break;
    n += r.value.length;
    if (n > limit) { await reader.cancel(); throw new AudioError("too-large"); }
    parts.push(r.value);
  }
  const out = new Uint8Array(n);
  let p = 0;
  for (const c of parts) { out.set(c, p); p += c.length; }
  return out;
}

const field = (b, o, n) => { let e = o; while (e < o + n && b[e] !== 0) e++; return dec.decode(b.subarray(o, e)); };

// untar(bytes) -> Map path -> Uint8Array (files only); a link, a device or an odd name is refused
export function untar(t) {
  const files = new Map();
  for (let o = 0; o + 512 <= t.length;) {
    const hdr = t.subarray(o, o + 512);
    if (hdr.every((x) => x === 0)) break;
    const type = String.fromCharCode(hdr[156] || 48);
    const size = parseInt(field(hdr, 124, 12).trim() || "0", 8);
    if (!Number.isSafeInteger(size) || size < 0) throw new AudioError("bad-tarball", "size");
    let name = field(hdr, 0, 100);
    const prefix = field(hdr, 345, 155);
    if (prefix && field(hdr, 257, 6).startsWith("ustar")) name = prefix + "/" + name;
    name = name.replace(/^\.\//, "").replace(/\/$/, "");
    o += 512;
    if (name !== "" && name !== ".") {
      if (!["0", "5"].includes(type) || !ENTRY.test(name)) throw new AudioError("bad-tarball", name);
      if (type === "0") {
        if (files.has(name)) throw new AudioError("bad-tarball", name);
        if (o + size > t.length) throw new AudioError("bad-tarball", "short");
        files.set(name, t.subarray(o, o + size));
      }
    }
    o += Math.ceil(size / 512) * 512;
  }
  return files;
}

// readAudioPackage(blob, { kernel }) -> { tarball: Blob, sha256, release, kernels: [{ key, krel, config }], fits }
// fits: the package has drivers for that kernel (5.4, 6.18, 7.2, 7.3); without them it is still usable, but its
// drivers do not load (the page asks before it takes such a package).
export async function readAudioPackage(blob, options = {}) {
  let zip;
  try { zip = await openZip(blob); } catch (e) { throw new AudioError(e instanceof ZipError ? "not-a-zip" : "not-a-zip", e.message); }
  const names = [...zip.entries.keys()];
  const tars = names.filter((n) => n.split("/").pop() === TARBALL && n.split("/").length <= 2);
  if (tars.length !== 1) throw new AudioError("not-audio");
  const top = tars[0].slice(0, -TARBALL.length);
  if (!zip.entries.has(top + "SHA256SUMS")) throw new AudioError("no-sums");
  const sums = {};
  for (const l of dec.decode(await zip.read(top + "SHA256SUMS", 65536)).split("\n")) {
    const p = l.trim().split(/\s+/);
    if (p.length === 2 && /^[0-9a-fA-F]{64}$/.test(p[0])) sums[p[1].replace(/^\*/, "")] = p[0].toLowerCase();
  }
  if (!sums[TARBALL]) throw new AudioError("no-sums");
  let tgz;
  try { tgz = await zip.read(tars[0], MAX_TARBALL); } catch (e) { throw new AudioError(e.code === "too-large" ? "too-large" : "not-a-zip", e.message); }
  const sha256 = hex(tgz);
  if (sha256 !== sums[TARBALL]) throw new AudioError("damaged");
  const files = untar(await gunzip(tgz, MAX_UNPACKED));
  const text = (n) => (files.has(n) ? dec.decode(files.get(n)) : "");
  if (text("name").trim() !== AUDIO_NAME) throw new AudioError("not-audio");
  const release = text("release").trim();
  if (!/^[A-Za-z0-9._-]{1,40}$/.test(release)) throw new AudioError("bad-tarball", "release");
  for (const n of NEEDED) if (!files.has(n)) throw new AudioError("bad-tarball", n);
  if (!files.has("manifest")) throw new AudioError("bad-tarball", "manifest");
  const want = new Map();
  for (const l of text("manifest").split("\n")) {
    if (!l) continue;
    const m = /^([0-9a-f]{64}) {2}\.\/([A-Za-z0-9._+/-]+)$/.exec(l);
    if (!m) throw new AudioError("bad-tarball", "manifest");
    want.set(m[2], m[1]);
  }
  const have = [...files.keys()].filter((n) => n !== "manifest").sort();
  if (have.join("\n") !== [...want.keys()].sort().join("\n")) throw new AudioError("bad-tarball", "manifest");
  for (const [n, h] of want) if (hex(files.get(n)) !== h) throw new AudioError("bad-tarball", n);
  const kernels = [];
  for (const [n, body] of files) {
    const p = n.split("/");
    if (p.length === 3 && p[0] === "modules" && p[2] === "KERNEL") {
      const kv = {};
      for (const l of dec.decode(body).split("\n")) { const eq = l.indexOf("="); if (eq > 0) kv[l.slice(0, eq)] = l.slice(eq + 1).trim(); }
      kernels.push({ key: kv.KEY || "", krel: p[1], config: kv.CONFIG || "" });
    }
  }
  kernels.sort((a, b) => a.krel.localeCompare(b.krel));
  const fits = !options.kernel || kernels.some((k) => k.key === options.kernel);
  return { tarball: new Blob([tgz]), sha256, release, kernels, fits };
}
