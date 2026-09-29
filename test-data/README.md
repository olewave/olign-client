# Test data

Real read English speech for trying the API and for `tests/test_v1_live.py`.
Every clip comes from **LibriSpeech** (dev-clean), which is licensed under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
— see [`LICENSE-LibriSpeech.txt`](LICENSE-LibriSpeech.txt).

> LibriSpeech (c) 2014 Vassil Panayotov. V. Panayotov, G. Chen, D. Povey and
> S. Khudanpur, "Librispeech: an ASR corpus based on public domain audio books",
> ICASSP 2015. The recordings are LibriVox readings of public-domain books.

| file | length | words | reader (LibriVox) | book, chapter | LibriSpeech utterances |
|---|---|---|---|---|---|
| `ls_short.flac` + `.txt` | 10.8 s | 29 | JudyGibson | *Don Quixote*, Vol. 2, ch. 60 | `3576-138058-0000` |
| `ls_medium.ogg` + `.txt` | 56.1 s | 137 | President Lethe | *Beyond Good and Evil*, "What is Noble?" | `422-122949-0000` … `-0003` |
| `ls_long.ogg` + `.txt` | 3 min 24 s | 554 | nprigoda | *Book of Household Management*, ch. 10 | `1919-142785-0000` … `-0022` |

Changes from the original: consecutive utterances of one chapter joined into one
file (medium, long), encoded as Opus 32 kbit/s mono (the format we recommend for
long recordings: ~14 MB an hour), and transcripts lower-cased and joined.
`ls_short.flac` is the original file, unchanged. `cases.json` lists what the live
test expects from each.
