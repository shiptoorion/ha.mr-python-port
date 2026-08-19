// Fuzz-векторы: случайные ссылки -> payload оригинального compress() из ha.mr.
import { compress } from "./js/compress.js";
import { outputAlphabetASCII } from "./js/alphabets.js";
import { writeFileSync } from "fs";

// Детерминированный PRNG, чтобы векторы были воспроизводимы
let seed = 0xC0FFEE;
function rnd() {
  seed = (seed * 1103515245 + 12345) & 0x7fffffff;
  return seed / 0x7fffffff;
}
const pick = (arr) => arr[Math.floor(rnd() * arr.length)];
const maybe = (p) => rnd() < p;

const hosts = [
  "example.com", "reddit.com", "old.reddit.com", "en.wikipedia.org",
  "github.com", "docs.microsoft.com", "bbc.co.uk", "news.ycombinator.com",
  "cydia.saurik.com", "sub.domain.example.org", "unknown-site.xyz",
  "localhost", "8.8.8.8", "my-server", "EXAMPLE.net", "x.co",
  "youtube.com", "www.youtube.com", "t.co", "notreddit.com",
];
const schemes = ["http://", "https://", "", "", "http://", "https://"];
const www = ["", "", "", "www."];
const ports = ["", "", "", ":8080", ":3000", ":81", ":65535", ":443", ":80"];
const segChars = [
  "abcdefghijklmnopqrstuvwxyz",
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
  "0123456789",
  "abcXYZ019-_",
  "!$&'()*+,;=:@",
  "abc%20def",
  "~user",
  "%E2%9C%93",
  "file.txt",
  "v1.2.3",
];
const queries = [
  "", "", "?a=1", "?q=hello+world", "?x=1&y=2", "?flag", "?k=",
  "?q=%D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82", "?a=1&a=2", "?=%20",
];
const hashes = ["", "", "", "#section", "#top", "#a%20b"];
const suffixes = ["", "", "", "/index.html", "/index.php"];

function randomPath() {
  const n = Math.floor(rnd() * 4);
  let p = "";
  for (let i = 0; i < n; i++) p += "/" + pick(segChars);
  return p;
}

const vectors = [];
for (let i = 0; i < 2000; i++) {
  let input = pick(schemes) + pick(www) + pick(hosts).replace(/^www\./, "");
  if (maybe(0.5)) input = pick(schemes) + pick(hosts); // host может уже иметь www
  if (maybe(0.3)) input += pick(ports);
  input += randomPath();
  input += pick(suffixes);
  input += pick(queries);
  input += pick(hashes);
  const entry = { input };
  try {
    entry.ascii = compress(input, outputAlphabetASCII);
  } catch (e) {
    entry.error = String(e && e.message ? e.message : e);
  }
  vectors.push(entry);
}

writeFileSync("fuzz_vectors.json", JSON.stringify(vectors), "utf-8");
const ok = vectors.filter((v) => !v.error).length;
console.log(`fuzz vectors: ${vectors.length}, ok: ${ok}, errors: ${vectors.length - ok}`);
