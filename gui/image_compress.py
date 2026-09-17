"""
gui/image_compress.py

The actual re-encoding step behind Operations -> Compress Images
(Lossy) -- needs Qt's own image codecs (QImage), which is why it lives
here rather than in core/ (see core/cover_generator.py vs
gui/cover_render.py for the same "no Qt in core/" split already used
for covers).

JPEG only, deliberately. PNG's own real size win needs palette
quantization, which Qt has no built-in equivalent of (QImage's
Format_Indexed8 conversion is a plain nearest-color reducer, not a
proper quantizer) -- doing that half-heartedly would risk visible
banding for a weak result. JPEG re-encoding at a lower quality is a
well-understood, predictable trade-off Qt already does well.
"""

from __future__ import annotations

from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtGui import QImage


def recompress_jpeg(data: bytes, quality: int) -> bytes | None:
    """Decodes `data` as an image and re-encodes it as JPEG at `quality`
    (0-100, Qt's own scale -- higher is better quality and larger).
    Returns None if the source bytes couldn't be decoded as an image at
    all, so the caller can leave that file untouched rather than risk
    writing a corrupt or empty result over it."""
    image = QImage()
    if not image.loadFromData(data):
        return None
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    ok = image.save(buffer, "JPG", quality)
    buffer.close()
    if not ok or buffer.data().isEmpty():
        return None
    return bytes(buffer.data())
