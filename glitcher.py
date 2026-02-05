import os
import shutil
from pathlib import Path

from PyQt5.QtWidgets import *

from modules.JPEG import glitchJpeg
from modules.BMP import convertFileToBMP, glitchBMP
from modules.GIF import glitchGif, glitchGifWithJPEG


class GlitcherWindow(QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("Glitcher v1.1")
		self.setMinimumSize(500, 400)

		self.selectedPath = None # initial path of uploaded file

		root = QWidget()
		layout = QVBoxLayout(root)

		# help button
		topLayout = QHBoxLayout()
		topLayout.addStretch()
		self.helpButton = QPushButton("Help")
		self.helpButton.clicked.connect(self.showHelp)
		self.helpButton.setMaximumWidth(80)
		topLayout.addWidget(self.helpButton)
		layout.addLayout(topLayout)

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
		layout.addWidget(self.uploadLabel)
		layout.addWidget(self.uploadButton)
		layout.addWidget(self.typeLabel)
		layout.addWidget(self.typeSelect)
		layout.addWidget(self.amountLabel)
		layout.addWidget(self.amountInput)
		layout.addWidget(self.runButton)
		layout.addWidget(self.progressLabel)
		layout.addWidget(self.progressBar)
		layout.addWidget(self.outputConsole)

		self.setCentralWidget(root)


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
		
		# sets the selected file path
		self.selectedPath = path
		self.uploadLabel.setText(Path(path).name)
		self.log(f"Selected: {path}")


	def runGlitch(self):
		if not self.selectedPath:
			QMessageBox.warning(self, "No file", "Please select an image first.")
			return

		self.log("Starting glitch process...")
		downloadsDir = Path.home() / "Downloads"
		downloadsDir.mkdir(exist_ok=True)

		srcPath = Path(self.selectedPath)
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
					skipped = glitchGifWithJPEG(str(srcPath), str(outputPath), percent=amount, progressCallback=self.updateProgress)
					self.log(f"Frames skipped: {skipped}")
				self.log(f"Saved: {outputPath}")
				os.startfile(str(outputPath))

			elif ext in [".bmp", ".png"]:
				self.log("Processing BMP/PNG...")
				outputPath = self.getUniquePath(downloadsDir, "glitched", ".bmp")
				self.log("Converting to BMP format...")
				convertFileToBMP(str(srcPath), str(outputPath))
				self.log(f"Applying BMP glitch with {amount}% intensity...")
				glitchBMP(str(outputPath), str(outputPath), amount)
				self.log(f"Saved: {outputPath}")
				self.updateProgress(1, 1)
				os.startfile(str(outputPath))

			elif ext in [".jpg", ".jpeg"]:
				self.log("Processing JPEG...")
				outputPath = self.getUniquePath(downloadsDir, "glitched", ".jpg")
				self.log(f"Applying JPEG glitch with {amount} iterations...")
				glitchJpeg(str(srcPath), str(outputPath), percent=amount)
				self.log(f"Saved: {outputPath}")
				self.updateProgress(1, 1)
				os.startfile(str(outputPath))

			elif ext == ".mp4":
				self.log("Processing MP4...")
				from modules.MP4 import glitchMp4
				outputPath = self.getUniquePath(downloadsDir, "glitched", ".mp4")
				self.log("Extracting frames from video...")
				skipped, audio_status, glitch_type_str = glitchMp4(
					str(srcPath),
					str(outputPath),
					percent=amount,
					progressCallback=self.updateProgress,
					glitchType=choice,
				)
				if skipped:
					self.log(f"Frames skipped: {skipped}")
				self.log(glitch_type_str)
				self.log(audio_status)
				self.log(f"Saved: {outputPath}")
				os.startfile(str(outputPath))

			else:
				QMessageBox.warning(self, "Unsupported", f"Unsupported file type: {ext}")
				return

			self.log("Done.")
			# clears temp folders
			self.log("Cleaning up temporary files...")
			try:
				shutil.rmtree("data/temp_frames")
				self.log("Temp frames cleared.")
			except Exception:
				pass
			self.log("Ready for next glitch!")
		except Exception as exc:
			QMessageBox.critical(self, "Error", str(exc))


if __name__ == "__main__":
	app = QApplication([])
	window = GlitcherWindow()
	window.show()
	app.exec()
