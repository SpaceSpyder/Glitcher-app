import os
import shutil
import subprocess
from pathlib import Path
import imageio.v2 as imageio
import math
import imageio_ffmpeg
from modules.JPEG import glitchJpeg
from modules.BMP import glitchFrame


def _prepare_folder(folder):
	if folder.exists():
		shutil.rmtree(folder)
	folder.mkdir(parents=True, exist_ok=True)


def glitchMp4(
	inputPath,
	outputPath,
	percent=10,
	seed=None,
	maxChunkLength=50,
	progressCallback=None,
	tempFolder="data/temp_frames",
	glitchType="JPEG",):

	tempFolder = Path(tempFolder)
	extractedFolder = tempFolder / "extracted"
	glitchedFolder = tempFolder / "glitched"

	_prepare_folder(extractedFolder)
	_prepare_folder(glitchedFolder)

	reader = imageio.get_reader(str(inputPath), format="ffmpeg")
	try:
		meta = reader.get_meta_data()
		fps = meta.get("fps") or 24
		nframes = meta.get("nframes")
		duration = meta.get("duration")
		total_frames = None
		if isinstance(nframes, (int, float)) and nframes > 0 and math.isfinite(nframes):
			total_frames = int(nframes)
		elif isinstance(duration, (int, float)) and duration > 0 and math.isfinite(duration):
			total_frames = int(round(duration * fps))
		if not total_frames:
			total_frames = 1

		combined_total = total_frames * 3
		if progressCallback is not None:
			progressCallback(0, combined_total)

		index = 0
		for index, frame in enumerate(reader, start=1):
			framePath = extractedFolder / f"frame_{index:06d}.jpg"
			imageio.imwrite(framePath, frame)
			if progressCallback is not None:
				progressCallback(min(index, total_frames), combined_total)

		# if the estimate was off, fix totals for later stages
		total_frames = max(index, 1)
		combined_total = total_frames * 3
		if progressCallback is not None:
			progressCallback(min(total_frames, total_frames), combined_total)
	finally:
		reader.close()

	framePaths = sorted(extractedFolder.glob("frame_*.jpg"))
	if not framePaths:
		raise ValueError("No frames extracted from MP4.")

	for index, framePath in enumerate(framePaths, start=1):
		outputFrame = glitchedFolder / framePath.name
		if glitchType == "BMP":
			from PIL import Image
			frame = Image.open(framePath).convert("RGB")
			glitched = glitchFrame(frame, percent=percent)
			glitched.save(outputFrame)
		else:
			frameSeed = None if seed is None else seed + index
			glitchJpeg(
				str(framePath),
				str(outputFrame),
				percent=percent,
				seed=frameSeed,
				maxChunkLength=maxChunkLength,
			)
		if progressCallback is not None:
			progressCallback(total_frames + index, combined_total)

	outputPath = str(outputPath)
	os.makedirs(os.path.dirname(outputPath) or ".", exist_ok=True)
	video_only_path = os.path.splitext(outputPath)[0] + "_noaudio.mp4"
	writer = imageio.get_writer(video_only_path, fps=fps, codec="libx264")
	skipped_frames = 0
	try:
		for index, framePath in enumerate(sorted(glitchedFolder.glob("frame_*.jpg")), start=1):
			try:
				writer.append_data(imageio.imread(framePath))
			except Exception:
				# if a glitched frame is unreadable fall back to original
				skipped_frames += 1
				originalFrame = extractedFolder / framePath.name
				writer.append_data(imageio.imread(originalFrame))
			if progressCallback is not None:
				progressCallback((total_frames * 2) + index, combined_total)
	finally:
		writer.close()

	# preserves audio using ffmpeg
	ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
	muxed = False
	audio_status = "Audio: none"
	mux_cmd = [
		ffmpeg_exe,
		"-y",
		"-i",
		str(video_only_path),
		"-i",
		str(inputPath),
		"-c:v",
		"copy",
		"-c:a",
		"aac",
		"-b:a",
		"192k",
		"-map",
		"0:v:0",
		"-map",
		"1:a:0",
		"-shortest",
		str(outputPath),]
	try:
		mux_result = subprocess.run(mux_cmd, capture_output=True, check=False, text=True)
		if mux_result.returncode == 0:
			muxed = True
			audio_status = "Audio: kept"
			try:
				os.remove(video_only_path)
			except OSError:
				pass
		else:
			audio_status = "Audio: failed"
			# fall back to video-only
			try:
				if os.path.exists(outputPath):
					os.remove(outputPath)
				shutil.move(video_only_path, outputPath)
			except Exception:
				pass
	except Exception as e:
		audio_status = f"Audio: error"
		# fall back to video-only
		try:
			if os.path.exists(outputPath):
				os.remove(outputPath)
			shutil.move(video_only_path, outputPath)
		except Exception:
			pass

	if skipped_frames:
		print(f"{skipped_frames}/{total_frames} frames skipped (corrupted after glitch)")

	glitch_type_str = f"Glitch type: {glitchType}"
	return skipped_frames, total_frames, audio_status, glitch_type_str

