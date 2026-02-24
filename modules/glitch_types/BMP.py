from PIL import Image
import random
import numpy as np


def convertFileToBMP(inputPath, outputPath="data/output.bmp"):
    img = Image.open(str(inputPath)).convert("RGB")
    img.save(str(outputPath), format="BMP")
    return outputPath



def glitchBMP(inputPath, outputPath, amount):
    # load and glitch using the same logic as glitchFrame
    img = Image.open(str(inputPath)).convert("RGB")
    glitched = glitchFrame(img, percent=amount)
    glitched.save(str(outputPath))
    return outputPath


def glitchFrame(frame, percent=50, maxShift=50):
    arr = np.array(frame)
    height, width, _ = arr.shape

    # scanline shift  
    for y in range(height):
        if random.random() < (percent / 100):
            shift = random.randint(-maxShift, maxShift)
            arr[y] = np.roll(arr[y], shift, axis=0)

    # random pixel corruption
    totalPixels = height * width
    numPixels = int(totalPixels * (percent / 100))

    for _ in range(numPixels):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        arr[y, x] = [random.randint(0, 255) for _ in range(3)]

    return Image.fromarray(arr)

