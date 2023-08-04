
import globalPluginHandler
import addonHandler
import config 
from scriptHandler import script 
import braille
from . import brailleBufferMultiline

import wx
import gui
from logging import log

#addonHandler.initTranslation() 

#settings
curBD = braille.handler.display.name + str(braille.handler.displaySize)
config.conf.spec["brailleMultiline"] = {
	"autoCheckUpdate": "boolean(default=True)",
	"numberOfLines_%s" % curBD: "integer(min=1, default=1, max=5)",
	"focusLine%s" % curBD: "integer(min=-1, default=-1, max=5)",
	"reverseScrollBtns": "boolean(default=False)",
	"backup_tetherTo": 'string(default="focus")',
	"backup_autoTether": "boolean(default=True)",
}
bmSettings = config.conf["brailleMultiline"]
numberOfLines = bmSettings["numberOfLines_%s" % curBD]

class OptionsPanel(gui.SettingsPanel):
	
	title = _("Braille Multiline Settings")

	def makeSettings(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		#self.OptionCheckBox = sHelper.addItem(
			#wx.CheckBox(self, label=_("A simple checkbox"))
		#)
		#self.OptionCheckBox.SetValue(numberOfLines)
		# Translators: label of an edit box
		numberOfLinesLabel = _("Number of Braille lines:")
		self.numberOfLinesEdit = sHelper.addLabeledControl(numberOfLinesLabel, wx.TextCtrl)
		self.numberOfLinesEdit.Value = str(bmSettings["numberOfLines_%s" % curBD])
		# Translators: label for an edit box
		focusLabel = _("Focus displayed on line:")
		self.focusEdit = sHelper.addLabeledControl(focusLabel, wx.TextCtrl)
		self.focusEdit.Value = str(bmSettings["focusLine%s" % curBD])

	def onSave(self):
		global numberOfLines
		#sample = self.optionCheckBox.IsChecked()
		numberOfLines = self.numberOfLinesEdit.Value 
		#rudimentary error checking for user input should tighten up
		if self.numberOfLinesEdit.Value is not None and int(self.numberOfLinesEdit.Value) < 6:
			bmSettings["numberOfLines_%s" % curBD] = int(numberOfLines)
		if self.focusEdit.Value is not None and int(self.focusEdit.Value) <6:
			bmSettings["focusLine%s" % curBD] = int(self.focusEdit.Value)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = "BrailleMultiline"

	def __init__(self):
		super().__init__()
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(OptionsPanel)
		self.newBrailleBuffer(bmSettings["numberOfLines_%s" % curBD])
		braille.handler.mainBuffer.focusBufferNumber = bmSettings["focusLine%s" % curBD]

	def terminate(self):
		super(GlobalPlugin, self).terminate()
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(OptionsPanel)
		# undo monkey patches
		braille.handler.mainBuffer = brailleBufferMultiline.oldMainBuffer
		braille.handler.buffer = braille.handler.mainBuffer
		braille.BrailleHandler._doNewObject = brailleBufferMultiline._original_doNewObject 

	def newBrailleBuffer(self, numLines):
		# @param numLines: number of lines or buffers want either integer, or list of buffer lengths must equal full displaySize
		# this does not save old buffer as it may be used to swithc on the fly
		braille.handler.mainBuffer = brailleBufferMultiline.BrailleBufferContainer(braille.handler, numLines) 
		braille.handler.buffer = braille.handler.mainBuffer

	@script(
	 #description="Display Braille Multiline settings dialog"
	)
	def script_showBMSettingsDlg(self, gesture):
		#runScriptModalDialog(dialog, callback=None)
		# looks for attribute showModal not implemented
		gui.runScriptModalDialog(OptionsPanel, callback=None)
	
	@script(gesture="kb:NVDA+=",
		# Translators: Input help mode message for open Braille Multilinesettings command.
		description=_("Opens the Braille Multiline  add-on's settings"),
		#category=SCRCAT_CONFIG
	)
	@gui.blockAction.when(gui.blockAction.Context.MODAL_DIALOG_OPEN)
	def script_activateBrailleMultilineSettingsDialog(self, gesture):
		wx.CallAfter(
			# Maintain compatibility with pre-2023.2 versions of gui
			getattr(gui.mainFrame, "popupSettingsDialog" if hasattr(gui.mainFrame, "popupSettingsDialog") else "_popupSettingsDialog"),
			gui.settingsDialogs.NVDASettingsDialog,
			OptionsPanel
		)

	#scrolling the non focus buffer lines requires calling scroll on the buffer as have not monkey patched braille.handler scroll
	@script(
		# Translators: Input help mode message for a braille command.
		description=_("Scrolls the braille display back"),
		#category=SCRCAT_BRAILLE,
		bypassInputHelp=True
	)
	def script_braille_scrollBackLineZero(self, gesture):
		braille.handler.buffer.scrollBack(0)

	@script(
		# Translators: Input help mode message for a braille command.
		description=_("Scrolls the braille display forward"),
		#category=SCRCAT_BRAILLE,
		bypassInputHelp=True
	)
	def script_braille_scrollForwardLineZero(self, gesture):
		braille.handler.buffer.scrollForward(0)

	@script(
		# Translators: Input help mode message for a braille command.
		description=_("Scrolls the braille display back"),
		#category=SCRCAT_BRAILLE,
		bypassInputHelp=True
	)
	def script_braille_scrollBackLineOne(self, gesture):
		braille.handler.buffer.scrollBack(1)

	@script(
		# Translators: Input help mode message for a braille command.
		description=_("Scrolls the braille display forward"),
		#category=SCRCAT_BRAILLE,
		bypassInputHelp=True
	)
	def script_braille_scrollForwardLineOne(self, gesture):
		braille.handler.buffer.scrollForward(1)

	@script(
		# Translators: Input help mode message for a braille command.
		description=_("Scrolls the braille display back"),
		#category=SCRCAT_BRAILLE,
		bypassInputHelp=True
	)
	def script_braille_scrollBackLineTwo(self, gesture):
		braille.handler.buffer.scrollBack(2)

	@script(
		# Translators: Input help mode message for a braille command.
		description=_("Scrolls the braille display forward"),
		#category=SCRCAT_BRAILLE,
		bypassInputHelp=True
	)
	def script_braille_scrollForwardLineTwo(self, gesture):
		braille.handler.buffer.scrollForward(2)

	@script(
		# Translators: Input help mode message for a braille command.
		description=_("Scrolls the braille display back"),
		#category=SCRCAT_BRAILLE,
		bypassInputHelp=True
	)
	def script_braille_scrollBackLineThree(self, gesture):
		braille.handler.buffer.scrollBack(3)

	@script(
		# Translators: Input help mode message for a braille command.
		description=_("Scrolls the braille display forward"),
		#category=SCRCAT_BRAILLE,
		bypassInputHelp=True
	)
	def script_braille_scrollForwardLineThree(self, gesture):
		braille.handler.buffer.scrollForward(3)



	@script(gesture="kb:NVDA+Shift+T")
	def script_oldBrailleBuffer(self, gesture):
		braille.handler.mainBuffer = brailleBufferMultiline.oldMainBuffer
		braille.handler.buffer = braille.handler.mainBuffer

	@script(gesture="kb:NVDA+shift+y")
	def script_newBrailleBuffer(self, gesture):
		# monkey patches
		#brailleBufferMultiline.oldMainBuffer = braille.handler.mainBuffer
		braille.handler.mainBuffer = brailleBufferMultiline.BrailleBufferContainer(braille.handler, 1) 
		braille.handler.buffer = braille.handler.mainBuffer
