Python port of ha.mr offline link shortener by p2r3.
This is the port of the v1.1 release https://github.com/p2r3/ha.mr/releases/tag/v1.1 and I hope the author will keep the compatibility.
Done entirely by Kimi K3 Max. Works fully offline. Lets you shorten or unshorten a link with a single line of code.

## Usage:
All you need are hamr.py and hamr_data.py
The rest of the files are just tests.

```python
from hamr import compress, decompress, shorten, unshorten

short_link = shorten("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
# -> http://ha.mr#:c27B@&#wF4e.[7vN417$
unshorten(short_link) # -> https://www.youtube.com/watch?v=dQw4w9WgXcQ

# Also has these:
payload = compress("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
# -> :c27B@&#wF4e.[7vN417$
decompress(payload) # -> https://www.youtube.com/watch?v=dQw4w9WgXcQ
```
