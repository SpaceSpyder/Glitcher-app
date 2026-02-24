import random

def findJpegHeaderEnd(filePath):
    with open(filePath, "rb") as f:
        data = f.read()

    sosIndex = data.find(b'\xFF\xDA')
    if sosIndex == -1:
        raise ValueError("Could not find SOS marker in JPEG")
    
    return sosIndex + 2  # start after SOS marker


def glitchJpeg(inputPath, outputPath, percent=5, seed=None, maxChunkLength=50):
    if seed is not None:
        random.seed(seed)

    headerEnd = findJpegHeaderEnd(inputPath)

    with open(inputPath, "rb") as f:
        jpgBytes = bytearray(f.read())

    length = len(jpgBytes) - headerEnd
    
    # dynamically set max chunk length based on frame size
    # small frames get smaller chunks for better results
    dynamicMaxChunk = max(1, min(maxChunkLength, length // 20))
    
    # use percent as number of iterations instead of total bytes
    # each iteration is one small glitch chunk
    iterations = max(1, percent)

    # apply corruption as multiple small chunks spread throughout
    for _ in range(iterations):
        # pick a random start position after the header
        start = random.randint(headerEnd, len(jpgBytes) - 2)
        # pick a chunk length (1 to dynamicMaxChunk bytes)
        chunkLen = random.randint(1, dynamicMaxChunk)
        chunkLen = min(chunkLen, len(jpgBytes) - start)

        # corrupt each byte in the chunk
        for i in range(chunkLen):
            if start + i < len(jpgBytes):
                jpgBytes[start + i] = random.randint(0, 255)

    # save the glitched JPEG
    with open(outputPath, "wb") as f:
        f.write(jpgBytes)
