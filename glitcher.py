import os
import shutil
from pathlib import Path
import sys
import subprocess

# auto-setup venv and installs packages
venv_path = Path(__file__).parent / ".venv"
if not venv_path.exists():
	subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)
	pip_path = venv_path / "Scripts" / "pip.exe"
	subprocess.run([str(pip_path), "install", "-r", str(venv_path.parent / "requirements.txt")], check=True)

os.environ.setdefault("QT_MULTIMEDIA_PREFERRED_PLUGINS", "windowsmediafoundation")

from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QMovie
from PyQt5.QtGui import QPixmap

try:
	from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
	from PyQt5.QtMultimediaWidgets import QVideoWidget
	_HAS_QT_MULTIMEDIA = True
except Exception:
	_HAS_QT_MULTIMEDIA = False

from modules.JPEG import glitchJpeg
from modules.BMP import convertFileToBMP, glitchBMP
from modules.GIF import glitchGif, glitchGifWithJPEG


class GlitcherWindow(QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("Glitcher v1.2")
		#self.setMinimumSize(700, 500)
		self.move(300, 300)
		self.setAcceptDrops(True)  # enable drag-drop anywhere on window

		# selectedPath is used for previewing (can be original or latest output)
		self.selectedPath = None
		# originalPath is always the file the user uploaded
		self.originalPath = None

		root = QWidget()
		layout = QVBoxLayout(root)

		widgetLeft = QWidget()
		widgetLeft.setMinimumSize(350, 300)
		widgetLeft.setMaximumWidth(350)

		widgetRight = QWidget()
		widgetRight.setMinimumSize(150,300)
		widgetRight.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)
		self.widgetRight = widgetRight  # store reference for later updates
		#self.widgetRight.setAcceptDrops(True)  # enable drag and drop

		rightLayout = QVBoxLayout(widgetRight)

		# help button
		topLayout = QHBoxLayout()
		topLayout.addStretch()
		self.helpButton = QPushButton("Help")
		self.helpButton.clicked.connect(self.showHelp)
		self.helpButton.setMaximumWidth(80)
		topLayout.addWidget(self.helpButton)
		rightLayout.addLayout(topLayout)

		self.previewStack = QStackedWidget(widgetRight)
		self.previewStack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
		#self.previewStack.setAcceptDrops(True)  # enables drag and drop on right side of window
		rightLayout.addWidget(self.previewStack)
	
		self.imageLabel = QLabel(self.previewStack)
		self.imageLabel.setScaledContents(True)  # content scales automatically
		self.imageLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		self.previewStack.addWidget(self.imageLabel)

		self.videoWidget = None
		self.mediaPlayer = None
		if _HAS_QT_MULTIMEDIA:
			self.videoWidget = QVideoWidget(self.previewStack)
			self.videoWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
			try:
				if hasattr(self.videoWidget, "setAspectRatioMode"):
					self.videoWidget.setAspectRatioMode(Qt.IgnoreAspectRatio)
			except Exception:
				pass
			self.previewStack.addWidget(self.videoWidget)

			self.mediaPlayer = QMediaPlayer(self)
			self.mediaPlayer.setVideoOutput(self.videoWidget)
			try:
				self.mediaPlayer.errorOccurred.connect(self._onVideoError)
			except Exception:
				try:
					self.mediaPlayer.error.connect(self._onVideoError)
				except Exception:
					pass
			try:
				self.mediaPlayer.mediaStatusChanged.connect(self._onVideoStatusChanged)
			except Exception:
				pass

		self.previewStack.setCurrentWidget(self.imageLabel)
		
		# Initialize preview (will show placeholder if no file selected)
		self.updateImageDisplay()



		# upload button
		self.uploadLabel = QLabel("No file selected")
		self.uploadButton = QPushButton("Upload file")
		self.uploadButton.clicked.connect(self.pickFile)

		# glitch type dropdown
		self.typeLabel = QLabel("Glitch type")
		self.typeSelect = QComboBox()
		self.typeSelect.addItems(["BMP", "JPEG"])
		self.typeSelect.setCurrentText("JPEG")

		# glitch type amount
		self.amountLabel = QLabel("Glitch amount (0-100)")
		self.amountInput = QSpinBox()
		self.amountInput.setRange(0, 100)
		self.amountInput.setValue(10)

		# glitch button
		self.runButton = QPushButton("Glitch")
		self.runButton.clicked.connect(self.runGlitch)

		# progress bar
		self.progressLabel = QLabel("Progress: 0/0")
		self.progressBar = QProgressBar()
		self.progressBar.setRange(0, 100)
		self.progressBar.setValue(0)

		# console output
		self.outputConsole = QTextEdit()
		self.outputConsole.setReadOnly(True)

		# divide the window into left and right halves
		mainLayout = QHBoxLayout()
		mainLayout.addWidget(widgetLeft, 1)  # left widget takes all the space
		mainLayout.addWidget(widgetRight, 1)  # right widget expands with the window

		# layout
		leftLayout = QVBoxLayout(widgetLeft)

		# add widgets to the left layout
		leftLayout.addWidget(self.uploadLabel)
		leftLayout.addWidget(self.uploadButton)
		leftLayout.addWidget(self.typeLabel)
		leftLayout.addWidget(self.typeSelect)
		leftLayout.addWidget(self.amountLabel)
		leftLayout.addWidget(self.amountInput)
		leftLayout.addWidget(self.runButton)
		leftLayout.addWidget(self.progressLabel)
		leftLayout.addWidget(self.progressBar)
		leftLayout.addWidget(self.outputConsole)

		# main layout
		layout.addLayout(mainLayout)
		self.setCentralWidget(root)

		self.fileDisplay = self.imageLabel # holds original file path
		#self.widgetRight.setAcceptDrops(True)  # enable drag and drop
	
	# image/video preview scaling
	def resizeEvent(self, event):
		try:
			if hasattr(self, "imagePreview") and self.imagePreview is not None and isinstance(self.imagePreview, QMovie):
				self.imagePreview.setScaledSize(self.imageLabel.size())
		except Exception:
			pass
		super().resizeEvent(event)


	# drag and drop support
	def dragEnterEvent(self, event):
		if event.mimeData().hasUrls():
			event.acceptProposedAction()

	def dropEvent(self, event):
		files = [url.toLocalFile() for url in event.mimeData().urls()]
		if files:
			self.loadFile(files[0])

	# load file from button or drag-drop
	def loadFile(self, path):
		if not path or not Path(path).exists():
			return
		
		ext = Path(path).suffix.lower()
		if ext not in [".png", ".jpg", ".jpeg", ".bmp", ".gif", ".mp4"]:
			QMessageBox.warning(self, "Unsupported", f"Unsupported file type: {ext}")
			return
		
		# store the original upload for future glitches
		self.originalPath = path
		# preview starts as the original upload
		self.selectedPath = path
		self.uploadLabel.setText(Path(path).name)

		# updates the image display
		self.updateImageDisplay()

		# get media dimensions and update widget size to maintain aspect ratio
		dimensions = self.getMediaDimensions(path)
		if dimensions:
			width, height = dimensions
			finalHeight = 400
			print(f"DEBUG: previewStack height: {finalHeight}, GIF height: {height}")
			scale = finalHeight / height
			#ratioS = width / height
			finalWidth = int(width * scale )
			print(f"DEBUG: Calculated widget width: {finalWidth}, Total window width would be: {150 + finalWidth}")
			self.previewStack.resize(finalWidth, finalHeight)
			self.resize(450 + finalWidth, 500)

		# Check if the file is an image and display it
		if ext in [".png", ".jpg", ".jpeg", ".bmp"]:
			pixmap = QPixmap(path)
			if pixmap.isNull():
				self.showUnreadablePreview()
			else:
				self.fileDisplay.setPixmap(pixmap)

		#self.log(f"Loaded: {path}")

	# get media dimensions for any supported file type
	def getMediaDimensions(self, path):
		if not path or not Path(path).exists():
			return None
		
		ext = Path(path).suffix.lower()
		
		try:
			if ext in ['.png', '.jpg', '.jpeg', '.bmp']:
				pixmap = QPixmap(path)
				if not pixmap.isNull():
					return (pixmap.width(), pixmap.height())
			
			elif ext == '.gif':
				movie = QMovie(path)
				if movie.isValid() and movie.jumpToFrame(0):
					frame_rect = movie.frameRect()
					dims = (frame_rect.width(), frame_rect.height())
					print(f"DEBUG: GIF dimensions: {dims}")
					return dims
				else:
					print(f"DEBUG: QMovie failed for GIF - isValid={movie.isValid()}")
					# Fallback: try PIL
					try:
						from PIL import Image
						img = Image.open(path)
						dims = img.size
						print(f"DEBUG: PIL fallback GIF dimensions: {dims}")
						return dims
					except Exception as e:
						print(f"DEBUG: PIL fallback failed: {e}")
			
			elif ext == '.mp4':
				# use moviepy to get actual video dimensions
				try:
					from moviepy.video.io.VideoFileClip import VideoFileClip
					clip = VideoFileClip(path)
					width, height = clip.size
					clip.close()
					return (width, height)
				except Exception:
					pass
				# fallback if moviepy fails
				return (1920, 1080)
		except Exception:
			pass
		
		return None


	# makes sure the output file doesn't overwrite an existing file 
	def getUniquePath(self, directory, baseName, extension):
		candidate = directory / f"{baseName}{extension}"
		index = 1

		# if output file name is unique
		if not candidate.exists(): 
			return candidate
		
		# output file name already exists
		while True:
			candidate = directory / f"{baseName}{index}{extension}"
			if not candidate.exists(): # increment number at the end till file name is unique
				return candidate
			index += 1 


	# logs messages to the window console
	def log(self, message):
		self.outputConsole.append(message)


	# updates progress bar 
	def updateProgress(self, current, total):
		self.progressLabel.setText(f"Progress: {current}/{total}")
		self.progressBar.setRange(0, total)
		self.progressBar.setValue(current)
		QApplication.processEvents()


	# help button function
	def showHelp(self):
		help_file = Path(__file__).resolve().parent / "assets/how to glitch.txt"
		if help_file.exists():
			os.startfile(str(help_file))
			self.log("Opening help file...")
		else:
			QMessageBox.warning(self, "Help", "ERROR help file not found (how to glitch.txt)")


	# upload button function
	def pickFile(self):
		defaultDir = str(Path.home() / "Downloads")
		path, _ = QFileDialog.getOpenFileName(
			self, "Select file",
			defaultDir, "Supported files (*.png *.jpg *.jpeg *.bmp *.gif *.mp4);;All files (*.*)") # file upload filters
		if path:
			self.loadFile(path)


	# update the file display after the process is done
	def runGlitch(self):
		if not self.originalPath and not self.selectedPath:
			QMessageBox.warning(self, "No file", "Please select an image first.")
			return

		self.log("Starting glitch process...")
		downloadsDir = Path.home() / "Downloads"
		downloadsDir.mkdir(exist_ok=True)

		srcPath = Path(self.originalPath or self.selectedPath)
		choice = self.typeSelect.currentText()
		amount = self.amountInput.value()
		ext = srcPath.suffix.lower()
		self.log(f"File type: {ext} | Glitch type: {choice} | Amount: {amount}")

		self.progressLabel.setText("Progress: 0/0")
		self.progressBar.setRange(0, 0)
		self.progressBar.setValue(0)

		try:
			if ext == ".gif":
				self.log("Processing GIF...")
				outputPath = self.getUniquePath(downloadsDir, "glitched", ".gif")
				if choice == "BMP":
					self.log("Applying BMP glitch to frames...")
					glitchGif(str(srcPath), str(outputPath), percent=amount, progressCallback=self.updateProgress)
				else:
					self.log("Applying JPEG glitch to frames...")
					# gets number of skipped frames and total frames for logging
					skipped, total_frames = glitchGifWithJPEG(
						str(srcPath),
						str(outputPath),
						percent=amount,
						progressCallback=self.updateProgress,)
					self.log(f"Frames skipped: {skipped} / {total_frames}")
				#self.log(f"Saved: {outputPath}")
				

			elif ext in [".bmp", ".png"]:
				self.log("Processing BMP/PNG...")
				outputPath = self.getUniquePath(downloadsDir, "glitched", ".bmp")
				self.log("Converting to BMP format...")
				convertFileToBMP(str(srcPath), str(outputPath))
				self.log(f"Applying BMP glitch with {amount}% intensity...")
				glitchBMP(str(outputPath), str(outputPath), amount)
				self.log(f"Saved: {outputPath}")
				self.updateProgress(1, 1)
				

			elif ext in [".jpg", ".jpeg"]:
				self.log("Processing JPEG...")
				outputPath = self.getUniquePath(downloadsDir, "glitched", ".jpg")
				self.log(f"Applying JPEG glitch with {amount} iterations...")
				glitchJpeg(str(srcPath), str(outputPath), percent=amount)
				self.log(f"Saved: {outputPath}")
				self.updateProgress(1, 1)
				

			elif ext == ".mp4":
				self.log("Processing MP4...")
				from modules.MP4 import glitchMp4
				outputPath = self.getUniquePath(downloadsDir, "glitched", ".mp4")
				self.log("Extracting frames from video...")
				skipped, total_frames, audio_status, glitch_type_str = glitchMp4(
					str(srcPath),
					str(outputPath),
					percent=amount,
					progressCallback=self.updateProgress,
					glitchType=choice,
				)
				if skipped:
					self.log(f"Frames skipped: {skipped} / {total_frames}")
				self.log(glitch_type_str)
				self.log(audio_status)
				self.log(f"Saved: {outputPath}")
				

			else:
				QMessageBox.warning(self, "Unsupported", f"Unsupported file type: {ext}")
				return

			self.log("Done.")

			# Preview the output, but keep the original upload for future glitches
			self.selectedPath = str(outputPath)
			self.updateImageDisplay()

			self.log("Cleaning up temporary files...")
			try:
				shutil.rmtree("data/temp_frames")
				self.log("Temp frames cleared.")
			except Exception:
				pass
			self.log("Ready")
		except Exception as exc:
			QMessageBox.critical(self, "Error", str(exc))


	def getUploadedFilePath(self):
		return self.originalPath

	def showUnreadablePreview(self):
		self.stopVideoPreview()
		try:
			self.previewStack.setCurrentWidget(self.imageLabel)
		except Exception:
			pass

		try:
			if hasattr(self, "imagePreview") and self.imagePreview is not None:
				self.imagePreview.stop()
		except Exception:
			pass

		fallback_path = Path(__file__).resolve().parent / "assets" / "icons" / "fileUnreadable.png"
		pixmap = QPixmap(str(fallback_path))
		if pixmap.isNull():
			self.imageLabel.setText("File unreadable")
			return
		self.imageLabel.setPixmap(pixmap)

	def _onMovieError(self, _err=None):
		self.showUnreadablePreview()

	def _onVideoError(self, *_args):
		self.showUnreadablePreview()

	def _onVideoStatusChanged(self, status):
		# If decoding fails (corrupted), fall back to unreadable image
		try:
			if status == QMediaPlayer.InvalidMedia:
				self.showUnreadablePreview()
				return
			if status == QMediaPlayer.EndOfMedia and self.mediaPlayer is not None:
				self.mediaPlayer.setPosition(0)
				self.mediaPlayer.play()
		except Exception:
			pass

	def _verifyVideoPlayback(self):
		if self.mediaPlayer is None:
			return
		try:
			err = self.mediaPlayer.error()
			if err != QMediaPlayer.NoError:
				self.showUnreadablePreview()
				return
		except Exception:
			pass

		try:
			status = self.mediaPlayer.mediaStatus()
			if status in (QMediaPlayer.InvalidMedia, QMediaPlayer.NoMedia):
				self.showUnreadablePreview()
				return
		except Exception:
			pass

	def stopVideoPreview(self):
		if self.mediaPlayer is None:
			return
		try:
			self.mediaPlayer.stop()
		except Exception:
			pass

	def startVideoPreview(self, path: str):
		if not _HAS_QT_MULTIMEDIA or self.mediaPlayer is None or self.videoWidget is None:
			self.showUnreadablePreview()
			return
		if not path or not Path(path).exists():
			self.showUnreadablePreview()
			return
		try:
			from PyQt5.QtCore import QUrl
			self.mediaPlayer.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
			self.previewStack.setCurrentWidget(self.videoWidget)
			self.mediaPlayer.play()
			QTimer.singleShot(250, self._verifyVideoPlayback)
		except Exception:
			self.showUnreadablePreview()

	# image display logic to handle both GIFs and static images
	def updateImageDisplay(self):
		if not self.selectedPath:
			self.stopVideoPreview()
			try:
				if hasattr(self, "imagePreview") and self.imagePreview is not None:
					self.imagePreview.stop()
			except Exception:
				pass
			self.previewStack.setCurrentWidget(self.imageLabel)
			placeholder_path = Path(__file__).resolve().parent / "assets" / "icons" / "placeHolder.png"
			pixmap = QPixmap(str(placeholder_path))
			if not pixmap.isNull():
				self.imageLabel.setPixmap(pixmap)
			else:
				self.imageLabel.clear()
			return

		file_extension = Path(self.selectedPath).suffix.lower()
		if file_extension == ".gif":
			self.stopVideoPreview()
			self.previewStack.setCurrentWidget(self.imageLabel)
			# display GIF using QMovie
			movie = QMovie(self.selectedPath)
			try:
				movie.error.connect(self._onMovieError)
			except Exception:
				pass
			if not movie.isValid() or not movie.jumpToFrame(0):
				self.showUnreadablePreview()
				return
			self.imagePreview = movie
			self.imageLabel.setMovie(self.imagePreview)
			self.imagePreview.setScaledSize(self.imageLabel.size())
			self.imagePreview.start()
		elif file_extension in [".png", ".jpg", ".jpeg", ".bmp"]:
			self.stopVideoPreview()
			self.previewStack.setCurrentWidget(self.imageLabel)
			# display static image using QPixmap
			pixmap = QPixmap(self.selectedPath)
			if pixmap.isNull():
				self.showUnreadablePreview()
				return
			self.imageLabel.setPixmap(pixmap)
		elif file_extension == ".mp4":
			# autoplay video preview
			self.startVideoPreview(self.selectedPath)
		else:
			self.stopVideoPreview()
			self.previewStack.setCurrentWidget(self.imageLabel)
			self.imageLabel.setText("Unsupported file format")

if __name__ == "__main__":
	app = QApplication([])
	window = GlitcherWindow()
	window.show()
	app.exec()
