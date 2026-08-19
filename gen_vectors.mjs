// Generates ground-truth test vectors using the ORIGINAL ha.mr code.
import { compress, decompress } from "./js/compress.js";
import { outputAlphabetASCII, outputAlphabetQR, outputAlphabetEmoji } from "./js/alphabets.js";
import { writeFileSync } from "fs";

const inputs = [
  // --- basics ---
  "example.com",
  "https://example.com",
  "http://example.com/",
  "www.example.com",
  "https://www.example.com/",
  "EXAMPLE.COM",
  "https://EXAMPLE.COM/Path/To/Page",
  // --- known SLDs / TLDs ---
  "reddit.com/r/all",
  "https://old.reddit.com/r/programming/comments/abc123",
  "en.wikipedia.org/wiki/Python_(programming_language)",
  "github.com/p2r3/ha.mr",
  "https://github.com/p2r3/ha.mr/releases",
  "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "stackoverflow.com/questions/1732348/regex-match-open-tags",
  "https://news.ycombinator.com/item?id=12345678",
  "docs.microsoft.com/en-us/dotnet/",
  "cydia.saurik.com/package/com.example",
  "bbc.co.uk/news/world-europe-12345678",
  // --- TLD edge cases ---
  "example.wtf/page",
  "example.ceo",
  "example.invalidtld/path",
  "localhost",
  "http://localhost:8080/test",
  // --- ports ---
  "example.com:8080/path",
  "https://example.com:443/secure",
  "http://example.com:80/default-port",
  "example.com:65535/max",
  // --- index suffixes ---
  "example.com/index.html",
  "example.com/blog/index.html",
  "example.com/index.php",
  "https://www.example.com/a/b/index.php?x=1",
  // --- paths ---
  "example.com/a",
  "example.com/a/b/c/d/e/f",
  "example.com/UPPERCASE",
  "example.com/MixedCase123",
  "example.com/12345678",
  "example.com/some-file_name",
  "example.com//double//slash",
  "example.com/trailing/",
  "example.com/a/../b/./c",
  // --- queries ---
  "example.com/?a=1",
  "example.com/?a=1&b=2",
  "example.com/search?q=hello+world",
  "example.com/?q=hello%20world",
  "example.com/?flag",
  "example.com/?=emptykey",
  "example.com/?a=&b=",
  "example.com/path?x=1&y=2&z=3",
  "example.com/?a=1&a=2&a=3",
  // --- hash ---
  "example.com/page#section",
  "example.com/#top",
  "example.com/path?x=1#frag",
  "example.com#",
  // --- percent-encoding ---
  "example.com/a%20b",
  "example.com/%E2%9C%93",
  "example.com/100%25-sure",
  "example.com/%2F%3F%23",
  "example.com/~user",
  "example.com/file~name~v2",
  // --- unicode ---
  "example.com/привет/мир",
  "example.com/✓✓✓",
  "example.com/?q=привет",
  "example.com/#фрагмент",
  // --- userinfo / ipv4 ---
  "https://user:pass@example.com/secure",
  "http://1.1.1.1/dns",
  "https://8.8.8.8/",
  // --- full URLs with protocol in input ---
  "https://example.com/already",
  "http://example.com/plain?x=1#y",
  "ftp://ftp.example.com/pub/file.zip",
  // --- subdomains & SLD matching quirks ---
  "notreddit.com",
  "reddit.com.evil.com/x",
  "www.wikipedia.org",
  "a.b.c.example.com/deep/path?query=1#hash",
  // --- misc ---
  "example.com/?",
  "example.com/!$&'()*+,;=:@",
  "example.com/very-long-segment-with-lots-of-words-and-dashes-between-them",
  "https://ha.mr/#recursive",
  "x.co",
  "t.co/abcXYZ123",
];

const vectors = [];
for (const input of inputs) {
  const entry = { input };
  try {
    entry.ascii = compress(input, outputAlphabetASCII);
    entry.link = `http://ha.mr#${entry.ascii}`;
    entry.qr = compress(input, outputAlphabetQR);
    entry.emoji = compress(input, outputAlphabetEmoji);
    // sanity: the original must roundtrip
    entry.roundtrip = decompress(entry.ascii, outputAlphabetASCII);
  } catch (e) {
    entry.error = String(e && e.message ? e.message : e);
  }
  vectors.push(entry);
}

writeFileSync("test_vectors.json", JSON.stringify(vectors, null, 2), "utf-8");
const ok = vectors.filter(v => !v.error).length;
console.log(`vectors: ${vectors.length}, ok: ${ok}, errors: ${vectors.length - ok}`);
for (const v of vectors) {
  if (v.error) console.log(`ERROR  ${v.input}  ->  ${v.error}`);
}
