import os
import shutil
from pathlib import Path

# Prefer the WMF backend on Windows (more reliable than DirectShow for many codecs).
# Must be set before QtMultimedia is imported.
os.environ.setdefault("QT_MULTIMEDIA_PREFERRED_PLUGINS", "windowsmediafoundation")

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import QMovie
from PyQt5.QtGui import *

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
		self.setMinimumSize(700, 500)

		# selectedPath is used for previewing (can be original or latest output)
		self.selectedPath = None
		# originalPath is always the file the user uploaded
		self.originalPath = None

		root = QWidget()
		layout = QVBoxLayout(root)

		widgetLeft = QWidget()
		widgetLeft.setMinimumSize(350, 300)
		#widgetLeft.setMaximumSize(350, 600)
		widgetLeft.setMaximumWidth(350)

		widgetRight = QWidget()
		widgetRight.setMinimumSize(250,300)
		widgetRight.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)

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
		self.previewStack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		rightLayout.addWidget(self.previewStack)
	
		# Move the initialization of self.imageLabel before adding it to the layout
		self.imageLabel = QLabel(self.previewStack)
		# Let the layout control sizing; scaling is handled via setScaledContents / QMovie scaling.
		self.imageLabel.setScaledContents(True)  # Ensure content scales automatically
		self.imageLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		self.previewStack.addWidget(self.imageLabel)

		self.videoWidget = None
		self.mediaPlayer = None
		if _HAS_QT_MULTIMEDIA:
			self.videoWidget = QVideoWidget(self.previewStack)
			self.videoWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
			# Match QLabel.setScaledContents(True) behavior: stretch to fill.
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
		
		self.imagePreview = QMovie(self.selectedPath) if self.selectedPath is not None else QMovie("assets\placeHolder.png")
		self.imageLabel.setMovie(self.imagePreview)
		self.imagePreview.setScaledSize(self.imageLabel.size())  # Scale the GIF to fit the QLabel size
		self.imagePreview.start()

		# Show placeholder until the user uploads a file
		self.updateImageDisplay()



		# upload button
		self.uploadLabel = QLabel("No file selected")
		self.uploadButton = QPushButton("Upload file")
		self.uploadButton.clicked.connect(self.pickFile)

		# glitch type button
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

		# adds all the buttons to the window
		# Create a horizontal layout to divide the window into left and right halves
		mainLayout = QHBoxLayout()
		mainLayout.addWidget(widgetLeft, 1)  # Left widget takes all the space
		mainLayout.addWidget(widgetRight, 1)  # Right widget expands with the window

		# Set the layout for widgetLeft
		leftLayout = QVBoxLayout(widgetLeft)

		# Move all existing widgets to the left layout
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

		# Add the main layout to the root layout
		layout.addLayout(mainLayout)

		self.setCentralWidget(root)

		# Keep existing pickFile logic working without creating a second layout
		self.fileDisplay = self.imageLabel
	
	def resizeEvent(self, event):
		# Keep GIF scaling in sync with the label size when the window/layout changes.
		try:
			if hasattr(self, "imagePreview") and self.imagePreview is not None:
				self.imagePreview.setScaledSize(self.imageLabel.size())
		except Exception:
			pass
		super().resizeEvent(event)


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
		help_file = Path("how to glitch.txt")
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
		if not path:
			return
		
		# store the original upload for future glitches
		self.originalPath = path
		# preview starts as the original upload
		self.selectedPath = path
		self.uploadLabel.setText(Path(path).name)

		# Update the image display
		self.updateImageDisplay()

		# Check if the file is an image and display it
		ext = Path(path).suffix.lower()
		if ext in [".png", ".jpg", ".jpeg", ".bmp"]:
			pixmap = QPixmap(path)
			if pixmap.isNull():
				self.showUnreadablePreview()
			else:
				self.fileDisplay.setPixmap(pixmap)
		elif ext == ".gif":
			# updateImageDisplay() already set up the QMovie
			pass
		elif ext == ".mp4":
			# updateImageDisplay() already started playback
			pass
		else:
			self.fileDisplay.setText(f"Uploaded: {Path(path).name}")  # update widgetRight display

		self.log(f"Selected: {path}")


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
				self.log(f"Saved: {outputPath}")
				

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
			self.log("Ready for next glitch!")
		except Exception as exc:
			QMessageBox.critical(self, "Error", str(exc))


	# Add a method to get the path of the uploaded image
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

		fallback_path = Path(__file__).resolve().parent / "assets" / "fileUnreadable.png"
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
		# If decoding fails (corrupted/unsupported), fall back to unreadable
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

	# Update the image display logic to handle both GIFs and static images
	def updateImageDisplay(self):
		if not self.selectedPath:
			self.stopVideoPreview()
			try:
				if hasattr(self, "imagePreview") and self.imagePreview is not None:
					self.imagePreview.stop()
			except Exception:
				pass
			self.previewStack.setCurrentWidget(self.imageLabel)
			placeholder_path = Path(__file__).resolve().parent / "assets" / "placeHolder.png"
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
			# Display GIF using QMovie
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
			self.imagePreview.start()
		elif file_extension in [".png", ".jpg", ".jpeg", ".bmp"]:
			self.stopVideoPreview()
			self.previewStack.setCurrentWidget(self.imageLabel)
			# Display static image using QPixmap
			pixmap = QPixmap(self.selectedPath)
			if pixmap.isNull():
				self.showUnreadablePreview()
				return
			self.imageLabel.setPixmap(pixmap)
		elif file_extension == ".mp4":
			# Autoplay video preview
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
