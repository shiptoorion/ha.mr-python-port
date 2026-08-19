// Эталонные векторы для decompress(): прогоняем все payload'ы из
// test/fuzz/edge-векторов через оригинальный decompress() из ha.mr.
import { decompress } from "./js/compress.js";
import { outputAlphabetASCII, outputAlphabetQR, outputAlphabetEmoji } from "./js/alphabets.js";
import { readFileSync, writeFileSync } from "fs";

const alphabets = {
  ascii: outputAlphabetASCII,
  qr: outputAlphabetQR,
  emoji: outputAlphabetEmoji,
};

const rows = [];
for (const file of ["test_vectors.json", "fuzz_vectors.json", "edge_vectors.json"]) {
  const vectors = JSON.parse(readFileSync(file, "utf-8"));
  for (const v of vectors) {
    for (const kind of ["ascii", "qr", "emoji"]) {
      if (!(kind in v)) continue;
      const row = { payload: v[kind], alphabet: kind };
      try {
        row.expected = decompress(v[kind], alphabets[kind]);
      } catch (e) {
        row.error = String(e && e.message ? e.message : e);
      }
      rows.push(row);
    }
  }
}

// Мусорные payload'ы: оригинал обязан упасть
for (const garbage of ["^", "hello world", "", " ", "%20", "abc^def", "0 0"]) {
  const row = { payload: garbage, alphabet: "ascii" };
  try {
    row.expected = decompress(garbage, outputAlphabetASCII);
  } catch (e) {
    row.error = String(e && e.message ? e.message : e);
  }
  rows.push(row);
}

writeFileSync("decompress_vectors.json", JSON.stringify(rows), "utf-8");
const ok = rows.filter((r) => !r.error).length;
console.log(`decompress vectors: ${rows.length}, ok: ${ok}, errors: ${rows.length - ok}`);
// все ли "мусорные" действительно падают?
for (const r of rows.slice(-7)) console.log(JSON.stringify(r));
