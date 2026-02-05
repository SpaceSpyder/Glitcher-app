from PIL import Image, ImageSequence
from modules.BMP import glitchFrame   # BMP glitching
from io import BytesIO
import random

def convertGIFtoBMPFrames(gifPath):
    gif = Image.open(str(gifPath))
    frames = []
    durations = []
    loop = gif.info.get("loop", 0)
    disposal = gif.info.get("disposal", 2)
    for frame in ImageSequence.Iterator(gif):
        frames.append(frame.convert("RGB"))
        durations.append(frame.info.get("duration", gif.info.get("duration", 100)))
    return frames, durations, loop, disposal

def glitchGif(inputGif, outputGif, percent=50, progressCallback=None):
    # BMP-style glitching of GIF frames
    frames, durations, loop, disposal = convertGIFtoBMPFrames(str(inputGif))
    glitchedFrames = []
    total = len(frames)
    for idx, frame in enumerate(frames, start=1):
        glitchedFrames.append(glitchFrame(frame, percent=percent))
        if progressCallback is not None:
            progressCallback(idx, total)

    glitchedFrames[0].save(
        str(outputGif),
        save_all=True,
        append_images=glitchedFrames[1:],
        loop=loop,
        duration=durations,
        disposal=disposal)

def glitchGifWithJPEG(inputGif, outputGif, percent=50, maxChunkLength=50, seed=None, tempFolder="data/temp_frames", progressCallback=None):
    # glitches a GIF using JPEG-style corruption
    # if a frame becomes unreadable after glitching, the original frame is used instead
    # uses iteration-based small chunks for reliable results on small frames
    frames, durations, loop, disposal = convertGIFtoBMPFrames(str(inputGif))
    glitchedFrames = []
    skippedFrames = 0

    total = len(frames)
    for idx, frame in enumerate(frames, start=1):
        try:
            # save frame to in-memory JPEG
            mem_file = BytesIO()
            frame.save(mem_file, format="JPEG", quality=95)
            mem_file.seek(0)

            # convert to bytearray
            jpgBytes = bytearray(mem_file.read())
            
            headerEnd = jpgBytes.find(b"\xFF\xDA") + 2
            length = len(jpgBytes) - headerEnd
            
            # dynamically set max chunk length based on frame size
            dynamicMaxChunk = max(1, min(maxChunkLength, length // 20))
            
            # use percent as number of iterations
            iterations = max(1, percent)

            # apply snorpey-style iteration-based glitch
            if seed is not None:
                random.seed(seed + idx)  # different seed per frame for variety

            # apply corruption as multiple small chunks
            for _ in range(iterations):
                pos = random.randint(headerEnd, len(jpgBytes) - 2)
                chunkLen = random.randint(1, dynamicMaxChunk)
                chunkLen = min(chunkLen, len(jpgBytes) - pos)
                for j in range(chunkLen):
                    if pos + j < len(jpgBytes):
                        jpgBytes[pos + j] = random.randint(0, 255)

            # load glitched JPEG back into PIL and verify it can decode
            glitchedImage = Image.open(BytesIO(jpgBytes))
            glitchedImage.verify()  # verify it's valid
            # reopen since verify() closes the image
            glitchedImage = Image.open(BytesIO(jpgBytes))
            glitchedFrames.append(glitchedImage.convert("RGB"))

        except (OSError, Exception):
            # if frame is corrupted or unreadable, use original
            skippedFrames += 1
            glitchedFrames.append(frame)

        if progressCallback is not None:
            progressCallback(idx, total)

    print(f"{skippedFrames}/{len(frames)} frames skipped")

    # reassemble GIF
    glitchedFrames[0].save(
        str(outputGif),
        save_all=True,
        append_images=glitchedFrames[1:],
        loop=loop,
        duration=durations,
        disposal=disposal)

    return skippedFrames
