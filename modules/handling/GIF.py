from PIL import Image, ImageSequence
from modules.glitch_types.JPEG import glitchJpeg
from modules.glitch_types.BMP import convertFileToBMP, glitchBMP, glitchFrame
from modules.glitch_types.GIF import glitchGif as _glitchGifBinary
from io import BytesIO
import random
import subprocess
import imageio_ffmpeg

def repairGifWithFFmpeg(inputPath, outputPath):
    # Architecture:
    # 1. Read disposal methods, delays, loop from the glitched source (PIL can usually
    #    parse the GCE metadata even from corrupt files)
    # 2. Decode raw frames through FFmpeg – its lenient LZW decoder renders corruption
    #    as real pixel artifacts (scanline tears, block smears etc.)
    # 3. Composite the decoded frames onto a persistent canvas applying the original
    #    disposal methods – this bakes ghosting / recursive overlay effects into pixels
    # 4. Save the composited pixel buffers into a clean GIF container
    import tempfile, os
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # ── 1. read metadata from glitched source
    try:
        src = Image.open(str(inputPath))
        canvas_size = src.size
        frame_count = src.n_frames
        delays, disposals = [], []
        for i in range(frame_count):
            src.seek(i)
            delays.append(src.info.get("duration", 100))
            disposals.append(src.info.get("disposal", 2))
        loop = src.info.get("loop", 0)
    except Exception:
        subprocess.run(
            [ffmpeg, "-y", "-i", str(inputPath), "-vsync", "0", "-loop", "0", str(outputPath)],
            capture_output=True)
        return

    # ── 2. decode raw frames through FFmpeg
    with tempfile.TemporaryDirectory() as tmpdir:
        frame_pattern = os.path.join(tmpdir, "frame%04d.png")
        subprocess.run(
            [ffmpeg, "-y", "-i", str(inputPath), "-vsync", "0", frame_pattern],
            capture_output=True)
        frame_files = sorted(f for f in os.listdir(tmpdir) if f.endswith(".png"))
        if not frame_files:
            subprocess.run(
                [ffmpeg, "-y", "-i", str(inputPath), "-vsync", "0", "-loop", "0", str(outputPath)],
                capture_output=True)
            return

        raw_frames = [Image.open(os.path.join(tmpdir, f)).convert("RGBA") for f in frame_files]

    # pad/trim metadata to match actual decoded frame count
    n = len(raw_frames)
    while len(delays) < n:     delays.append(100)
    while len(disposals) < n:  disposals.append(2)
    delays    = delays[:n]
    disposals = disposals[:n]

    # ── 3. composite frames maintaining a canvas with original disposal methods
    # disposal=0/1 → leave canvas as-is (next frame draws on top → ghosting)
    # disposal=2   → clear canvas to transparent before next frame
    # disposal=3   → restore canvas to state before current frame was drawn
    canvas      = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    pre_draw    = canvas.copy()   # canvas state before current frame (for disposal=3)
    composited  = []

    for i, raw in enumerate(raw_frames):
        disposal = disposals[i]

        # snapshot canvas before drawing (needed if next frame wants disposal=3)
        pre_draw = canvas.copy()

        # resize raw frame to canvas size if FFmpeg output dimensions differ
        if raw.size != canvas_size:
            raw = raw.resize(canvas_size, Image.NEAREST)

        # draw this frame onto the canvas
        canvas.paste(raw, (0, 0), raw)

        # save composited result as RGB for GIF encoding
        composited.append(canvas.convert("RGB"))

        # apply disposal to prepare canvas for next frame
        if disposal == 2:
            canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
        elif disposal == 3:
            canvas = pre_draw
        # disposal 0/1: leave canvas as current composite (ghosting effect preserved)

    # ── 4. save composited frames into a clean GIF container
    # each frame is now a full composite so disposal=2 is correct going forward
    composited[0].save(
        str(outputPath),
        save_all=True,
        append_images=composited[1:],
        loop=loop,
        duration=delays,
        disposal=2,
        optimize=False,
    )

def glitchGifBinary(inputGif, outputGif, percent=10, seed=None, progressCallback=None):
    # raw binary GIF glitch – operates directly on the file stream
    # (LZW data, color tables, disposal/delay bytes)
    _glitchGifBinary(str(inputGif), str(outputGif), percent=percent, seed=seed)
    if progressCallback is not None:
        progressCallback(1, 1)

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

    return skippedFrames, total
