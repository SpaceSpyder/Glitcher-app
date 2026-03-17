import random

def findEditableRegions(data: bytearray):
    regions = []
    pos = 0
    length = len(data)

    pos += 6  # header

    if pos + 7 > length:
        return regions
    lsd_packed = data[pos + 4]
    has_gct    = (lsd_packed >> 7) & 1
    gct_size   = lsd_packed & 0x07
    pos += 7  # lsd

    if has_gct:
        gct_len = 3 * (1 << (gct_size + 1))
        regions.append((pos, pos + gct_len, "color"))
        pos += gct_len

    while pos < length:
        sentinel = data[pos]

        if sentinel == 0x3B:
            break

        elif sentinel == 0x2C:
            pos += 1
            if pos + 9 > length:
                break
            img_packed = data[pos + 8]
            has_lct    = (img_packed >> 7) & 1
            lct_size   = img_packed & 0x07
            pos += 9

            if has_lct:
                lct_len = 3 * (1 << (lct_size + 1))
                regions.append((pos, pos + lct_len, "color"))
                pos += lct_len

            regions.append((pos, pos + 1, "lzw_mcs"))
            pos += 1

            while pos < length:
                sub_len = data[pos]
                pos += 1
                if sub_len == 0:
                    break
                regions.append((pos, pos + sub_len, "lzw"))
                pos += sub_len

        elif sentinel == 0x21:
            pos += 1
            if pos >= length:
                break
            label = data[pos]
            pos += 1

            if label == 0xF9:
                if pos + 6 > length:
                    break
                block_size = data[pos]
                pos += 1
                if block_size == 4:
                    regions.append((pos,     pos + 1, "disposal"))
                    regions.append((pos + 1, pos + 3, "delay"))
                    pos += 4
                    pos += 1
                else:
                    pos += block_size
                    pos += 1
            else:
                while pos < length:
                    sub_len = data[pos]
                    pos += 1
                    if sub_len == 0:
                        break
                    pos += sub_len
        else:
            pos += 1

    return regions


_TAG_WEIGHT_MULTIPLIER = {
    "lzw_mcs":  500,
    "color":    20,
    "lzw":      5,
    "disposal": 1,
    "delay":    1,
}


def _set_gif_loop(data: bytearray, loop: int = 0) -> None: # makes sure the gif loops
    if loop < 0 or loop > 0xFFFF:
        return
    pat = b"\x21\xFF\x0BNETSCAPE2.0\x03\x01"
    i = data.find(pat)
    if i != -1 and i + len(pat) + 2 <= len(data):
        data[i + len(pat): i + len(pat) + 2] = loop.to_bytes(2, "little")
        return
    if len(data) < 13:
        return
    packed = data[10]  # header(6) + packed field offset(4)
    gct_len = 3 * (1 << ((packed & 0x07) + 1)) if ((packed >> 7) & 1) else 0
    pos = 13 + gct_len  # header(6) + LSD(7) + GCT
    if 0 <= pos <= len(data):
        data[pos:pos] = pat + loop.to_bytes(2, "little") + b"\x00"


def glitchGif(inputPath, outputPath, percent=10, seed=None, allowed_tags=None):
    if seed is not None:
        random.seed(seed)

    with open(inputPath, "rb") as f:
        original = bytearray(f.read())

    regions = findEditableRegions(original)
    if not regions:
        raise ValueError("No editable regions found in GIF.")

    if allowed_tags is not None:
        allowed_set = set(allowed_tags)
        regions = [r for r in regions if r[2] in allowed_set]
        if not regions:
            with open(outputPath, "wb") as f:
                f.write(original)
            return

    editable_sorted = sorted(regions, key=lambda r: r[0])
    safe_snapshots = []
    cursor = 0
    for start, end, _tag in editable_sorted:
        if cursor < start:
            safe_snapshots.append((cursor, bytes(original[cursor:start])))
        cursor = end
    if cursor < len(original):
        safe_snapshots.append((cursor, bytes(original[cursor:])))

    data = bytearray(original)
    iterations = max(1, percent)

    weights = [
        max(1, (e - s)) * _TAG_WEIGHT_MULTIPLIER.get(t, 1)
        for s, e, t in regions
    ]

    for _ in range(iterations):
        start, end, tag = random.choices(regions, weights=weights)[0]

        if tag == "lzw_mcs":
            data[start] = random.randint(2, 8)
        elif tag == "color":
            entry_count = (end - start) // 3
            entry = random.randint(0, entry_count - 1)
            base = start + entry * 3
            for i in range(3):
                data[base + i] = random.randint(0, 255)
        else:
            max_chunk = (end - start) if tag == "lzw" else max(1, (end - start) // 2)
            pos = random.randint(start, end - 1)
            chunk_len = min(random.randint(1, max(1, max_chunk // 2)), end - pos)
            for i in range(chunk_len):
                data[pos + i] = random.randint(0, 255)

    # restore safe bytes
    for start, snap in safe_snapshots:
        data[start:start + len(snap)] = snap

    _set_gif_loop(data, 0)
    with open(outputPath, "wb") as f:
        f.write(data)
