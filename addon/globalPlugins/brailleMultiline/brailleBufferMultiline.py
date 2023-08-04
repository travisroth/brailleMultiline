
import ui
import braille
import types
from collections.abc import Iterable
import typing
from typing import (
	TYPE_CHECKING,
	Any,
	Dict,
	Generator,
	Iterable,
	List,
	Optional,
	Set,
	Tuple,
	Union,
	Type,
)
import config
from config.configFlags import (
	ShowMessages,
	TetherTo,
	ReportTableHeaders,
)
from logHandler import log
import controlTypes
import api
import textInfos
import baseObject 
import math

#once not monkey patching BrailleHandler look to remove 
from utils.security import objectBelowLockScreenAndWindowsIsLocked
from braille import TextInfoRegion

if TYPE_CHECKING:
	from NVDAObjects import NVDAObject

CONTEXTPRES_SCROLL = "scroll"
CONTEXTPRES_CHANGEDCONTEXT = "changedContext"



class BrailleBufferSegment(braille.BrailleBuffer):
	"""
	overrides methods in BrailleBuffer class that use handler.displaySize to calclate what is visible as a segment is smaller than full display size
	"""

	def __init__(self, handler, segmentSize):
		"""@param segmentSize: size of a segment of a multiline display
		@type segmentSize: int
		"""
		super().__init__(handler)
		self.segmentSize = segmentSize

	def append(self, regions):
		self.regions.append(regions) 


	def _get_windowEndPos(self):
		endPos = self.windowStartPos + self.segmentSize
		cellsLen = len(self.brailleCells)
		if endPos >= cellsLen:
			return cellsLen
		if not config.conf["braille"]["wordWrap"]:
			return endPos
		try:
			# Try not to split words across windows.
			# To do this, break after the furthest possible space.
			return min(braille.rindex(self.brailleCells, 0, self.windowStartPos, endPos) + 1,
				endPos)
		except ValueError:
			pass
		return endPos

	def _set_windowEndPos(self, endPos):
		"""Sets the end position for the braille window and recalculates the window start position based on several variables.
		1. Braille display size.
		2. Whether one of the regions should be shown hard left on the braille display;
			i.e. because of The configuration setting for focus context representation
			or whether the braille region that corresponds with the focus represents a multi line edit box.
		3. Whether word wrap is enabled."""
		startPos = endPos - self.segmentSize
		# Loop through the currently displayed regions in reverse order
		# If focusToHardLeft is set for one of the regions, the display shouldn't scroll further back than the start of that region
		for region, regionStart, regionEnd in reversed(list(self.regionsWithPositions)):
			if regionStart<endPos:
				if region.focusToHardLeft:
					# Only scroll to the start of this region.
					restrictPos = regionStart
					break
				elif config.conf["braille"]["focusContextPresentation"]!=CONTEXTPRES_CHANGEDCONTEXT:
					# We aren't currently dealing with context change presentation
					# thus, we only need to consider the last region
					# since it doesn't have focusToHardLeftSet, the window start position isn't restricted
					restrictPos = 0
					break
		else:
			restrictPos = 0
		if startPos <= restrictPos:
			self.windowStartPos = restrictPos
			return
		if not config.conf["braille"]["wordWrap"]:
			self.windowStartPos = startPos
			return
		try:
			# Try not to split words across windows.
			# To do this, break after the furthest possible block of spaces.
			# Find the start of the first block of spaces.
			# Search from 1 cell before in case startPos is just after a space.
			startPos = self.brailleCells.index(0, startPos - 1, endPos)
			# Skip past spaces.
			for startPos in range(startPos, endPos):
				if self.brailleCells[startPos] != 0:
					break
		except ValueError:
			pass
		self.windowStartPos = startPos


	def focus(self, region):
		"""Bring the specified region into focus.
		The region is placed at the start of the display.
		However, if the region has not set L{Region.focusToHardLeft} and there is extra space at the end of the display, the display is scrolled left so that as much as possible is displayed.
		@param region: The region to focus.
		@type region: L{Region}
		"""
		pos = self.regionPosToBufferPos(region, 0)
		self.windowStartPos = pos
		if region.focusToHardLeft or config.conf["braille"]["focusContextPresentation"]==CONTEXTPRES_SCROLL:
			return
		end = self.windowEndPos
		if end - pos < self.segmentSize:
			# We can fit more on the display while still keeping pos visible.
			# Force windowStartPos to be recalculated based on windowEndPos.
			self.windowEndPos = end

	def _get_windowBrailleCells(self):
		cells = self.brailleCells[self.windowStartPos:self.windowEndPos]
		# cells might not be the full length of the display.
		# Therefore, pad it with spaces to fill the display.
		#this is handled in BrailleHandler.update() but it does not know about our multi buffers
		#so need add spaces here or buffers will not start where wanted on second, third, etc., lines
		#potential bug this could break rawText?
		cells = cells + [0] * (self.segmentSize- len(cells))
		return cells

	def update(self):
		super().update()
		log.debug("BrailleBufferSegment.update %s" % self.rawText)

	def updateDisplay(self):
		#if self is self.handler.buffer:
		# when the braille buffer (BrailleBufferSegment) is active self.handler.buffer is BrailleBufferContainer so this will fail 
		#why does braille.py need this extra check? 
		#todo: add check if in BrailleBufferContainer if this is crashy
		self.handler.update()
		log.debug("BrailleBufferSegment.updateDisplay is called %s" % self.rawText)




class FakeRegionsList(object):
	def __init__(self, multibuffer, regions ):
		"""
		@param multibuffer: the BraillemultilineBuffer isntance
		@param regions: the BrailleMultilineBuffer.BrailleSegmentBuffer.regions list that focus objects are written to by braille.mainBuffer.append by default. monkey hack
		"""
		self.multibuffer = multibuffer
		self._regions = regions 

	def __getitem__(self, item):
		return self._regions[item] if self._regions  else None

	def __len__(self):
		return len(self._regions) if self._regions  else 0

	def append(self, region):
		"""
		@param region: the region or regions to append to a buffer. Will handle checking attribute targetSegment to send to corresponding buffer
		@type region: list of Braille.Region
		"""
		if region is None: return 
		if isinstance(region, Iterable):
			for r in region:
				self.multibuffer.bufferSegments[getattr(r, "targetSegment", -1)].append(r)
		else:
			self.multibuffer.bufferSegments[getattr(region, "targetSegment", -1)].append(region)



#class  BrailleBufferContainer(braille.BrailleBuffer): #inherits updateDisplay but otherwise everything is overridden or not used unnecessary overhead?
class  BrailleBufferContainer(baseObject.AutoPropertyObject):
	"""
	Contains BrailleBufferSegment children. Returns combined visible cells to NVDA as one object as NVDA prints only entire displaySize chars to a display. 
	Manages scrolling for each child BrailleBufferSegment.
	To direct to an individual buffer for default braille.BrailleBuffer methods pass named optional parameter l{segment} as last argument. 
	When appending regions use attribute l{targetSegment} in the region object.
	"""

	def __init__(self, handler, segments):
		"""
		@param segments: number of segments and optionally size if they're in a list for a display. Unknown if BrailleHandler will have this automatically at some point.
		@type segments: int or list
		"""
		#super().__init__(handler)
		self.handler = handler
		self.segments = segments 
		# @param bufferSegments: children BrailleBufferSegment that make up the display
		# @type bufferSegments: list
		# @precondition: the list of segment sizes must equal total displaySize
		self.bufferSegments = []
		self.displaySize = self.handler.displaySize
		if type(self.segments) == int:
			# equal length segments divided by displaySize
			segmentSize = int(self.displaySize / self.segments) #force integer  
			for i in range(0, segments):
				self.bufferSegments.append(BrailleBufferSegment(handler, segmentSize))
				self.numOfSegments = segments
		elif type(self.segments)==list: 
			for i in self.segments:
				self.bufferSegments.append(BrailleBufferSegment(handler, i))
			self.numOfSegments = len(segments)
		self._focusBufferNumber = self.focusBufferNumberDefault = -1 # where she should default NVDA focus braille be sent too #warning not fuly implemented
		#hack: BrailleHandler likes to write to BrailleBuffer.regions[] directly which is not very OOO in message() and _doNewObject()
		# make a pointer to our new append method so don't have monkey patch BrailleHandler._doNewObject, handlePendingCaretUpdate
		self.regions = FakeRegionsList(self, self.bufferSegments[self.focusBufferNumber].regions)
		self.rawText = ""
		self.brailleCells = []
		self.cursorPos = None
		log.debug("BrailleBufferContainer initialized")



	def append(self, region):
		"""
		@param region: the region or regions to append to a buffer. Will handle checking attribute targetSegment to send to corresponding buffer
		@type region: list of Braille.Region
		"""
		if region is None: return 
		if isinstance(region, Iterable):
			for r in region:
				s = getattr(r, "targetSegment", -1)
				s = sef.focusBufferNumber  if s >= len(self.bufferSegments) else s #safety check if multiline output gets connected ot one buffer
				self.bufferSegments[s].append(r)
		else:
				s = getattr(r, "targetSegment", -1)
				s = -1 if s >= len(self.bufferSegments) else s #safety check if multiline output gets connected ot one buffer
				self.bufferSegments[s].append(r)

	def _get_focusBufferNumber(self):
		return self._focusBufferNumber 

	def _set_focusBufferNumber(self, bufferNum):
		if (bufferNum >=0 and bufferNum < self.numOfSegments) or bufferNum==-1:
			self._focusBufferNumber = bufferNum
		else:
			raise LookupError("No such position to set focus buffer")

	def update(self):
		self.rawText = ""
		self.brailleCells = []
		self.cursorPos = None
		start = 0
		for b in self.bufferSegments:
			b.update()
			# it appears sometimes rawText and brailleCells are accessed at the buffer level direclty instead of through getters
			self.rawText+= b.rawText
			self.brailleCells.extend(b.brailleCells)
			#if b.cursorPos is not None:
				#self.cursorPos = start + b.cursorPos
			#start += len(b.brailleCells)
		#return the cursor from the focus buffer as default BrailleHandler only knows one cursor 
		if self.bufferSegments[self.focusBufferNumber].cursorPos is not None:
			self.cursorPos = self.getWindowLeadingCells(self.focusBufferNumber) + self.bufferSegments[self.focusBufferNumber].cursorPos 



	def updateDisplay(self):
		log.debug("BrailleBufferContainer.updateDisplay ")
		if self is self.handler.buffer:
			self.handler.update()

	def _get_windowRawText(self):
		#since Braille display is treated as one buffer may be best to match _get_windowBrailleCells
		text = ""
		for b in self.bufferSegments:
			text += b._get_windowRawText()
		return text

	def _get_windowBrailleCells(self):
		#since Braille display is treated as one buffer should return all segments' cells
		cells = []
		for buf in self.bufferSegments:
			cells.extend(buf._get_windowBrailleCells())
		return cells

	def _get_visibleRegions(self):
		for buf in self.bufferSegments:
			yield buf._get_visibleRegions()

	def saveWindow(self):
		"""Save the current window so that it can be restored after the buffer is updated.
		The window start position is saved as a position relative to a region.
		This allows it to be restored even after other regions are added, removed or updated.
		It can be restored with L{restoreWindow}.
		@postcondition: The window is saved and can be restored with L{restoreWindow}.
		"""
		#self._savedWindow = self.bufferPosToRegionPos(self.windowStartPos)
		for s in self.bufferSegments:
			try: #if bufferSegmetn is empty saveWindow barfs but this may be a valid condition if only focus segment has been used so far or buffer was cleared
				s.saveWindow()
			except:
				pass

	def restoreWindow(self):
		"""Restore the window saved by L{saveWindow}.
		@precondition: L{saveWindow} has been called.
		@postcondition: If the saved position is valid, the window is restored.
			Otherwise, the nearest position is restored.
		"""
		for s in self.bufferSegments:
			try:
				s.restoreWindow()
			except: 
				pass

	def getBufferSegment(self, braillePos):
		"""
		Calculates the buffer segment braillePos is in for multibuffer. If only one buffer will return 0
		@param braillePos: Braille cursor position urousually vided by routeTo
		@param braillePos type: int
		"""
		inSegment = 0
		inSegmentSize = 0
		#our bufferSegments are 0 based physical routing keys also 0 based
		if type(self.segments) == int:
			inSegmentSize = (self.displaySize/self.segments )
			inSegment = math.floor( braillePos/ inSegmentSize)
			return inSegment
		elif type(self.segments) == list:
			counter = 0
			for i in self.segments:
				counter = counter + i
				if braillePos < counter:
					return inSegment 
				inSegment = inSegment+1

	def getWindowLeadingCells(self, segment):
		"""
		Returns number of cells before a buffer starts. Segments are 0 based, -1 is last buffer usually focus
		@param segment: the 0 based segment 
		@param type segment: int
		"""
		cells = 0
		segment = len(self.bufferSegments)-1 if segment == -1 else segment 
		if type(self.segments) == int:
			size = int((self.displaySize/self.segments ))
			cells = size*segment
		elif type(self.segments) == list:
			if (segment > 0) and (segment < len(self.segments)):
				for i in range(0, segment):
					cells += self.segments[i]
		return cells 
		

	def routeTo(self, braillePos):
		if braillePos == 79:
			self.debugBuffer()
			return 
		#if display and NVDA think it is one buffer positions after the first buffer wont' match up 
		#if window mode such as on Orbit slate is supported in firmware what will it send routing wise? 
		inSegment = self.getBufferSegment(braillePos)
		segmentSize = int((self.displaySize/self.segments)) if type(self.segments) == int else self.segments[inSegment]
		#text = "routing " + str(braillePos) + " inSegment " + str(inSegment) + "final routing " + str(int(braillePos%segmentSize))
		#ui.message(text)
		self.bufferSegments[inSegment].routeTo( (int(braillePos%segmentSize)) )

	def clear(self, segment=-1):
		if segment is None: 
			for b in self.bufferSegments: b.clear()
		else:
			segment = self.focusBufferNumber if segment == -1 else segment
			self.bufferSegments[segment].clear() 
		#brailleBuffer.clear() just initializes regions to a new list which breaks our 
		self.regions = FakeRegionsList(self, self.bufferSegments[self.focusBufferNumber].regions)

# these are BrailleBuffer methods but base class doesn't know to look at multiple buffers so needs redirecting to be plug and play
	#adding ability to access individual buffers but NVDA is focus driven so liekly mostly will work with focus buffer
	# last buffer in bufferSegments has the last text written and is being used as default focus buffer

	def scrollForward(self, segment=-1):
		# redirect scroll command to a specific segment optional defaults to last buffer should be compatible with old API this way
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment].scrollForward()

	def scrollBack(self, segment=-1):
		# redirect scroll command to a specific segment optional defaults to last buffer should be compatible with old API this way
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment].scrollBack()

	
	def focus(self, region, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		#workaround: _doNewObject calls this without knowing what buffer is targeted. Check for a targetSegment in region and override
		try:
			if hasattr(region, "targetSegment"): 
				return self.bufferSegments[getattr(region, "targetSegment")].focus(region)
			else:
				return self.bufferSegments[segment].focus(region)
		except:
			pass 
		return 


	def _get_windowEndPos(self, segment =-1):
		#seems dont' need to adjust for leading cells at this level
		#return self.getWindowLeadingCells(segment) + self.bufferSegments[segment]._get_windowEndPos()
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment]._get_windowEndPos()
	
	def _set_windowEndPos(self, endPos, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		self.bufferSegments[segment]._set_windowEndPos(endPos)

	def scrollTo(self, region, pos, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		#workaround _doNewObject calls scrollToCursorOrSelection which calls this scrollTo and they are buffer unaware. also see focus()
		try: 
			if hasattr(region, "targetSegment"): 
				return self.bufferSegments[getattr(region, "targetSegment")].scrollTo(region, pos)
			else: 
				return self.bufferSegments[segment].scrollTo(region, pos)
		except:  
			pass 

	def _get_regionsWithPositions(self, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment]._get_regionsWithPositions()

	def _get_rawToBraillePos(self, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment]._get_rawToBraillePos()

	#brailleToRawPos: List[int] #we dont' have a liblouis translation at the multi buffer level

	def _get_brailleToRawPos(self, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment]._get_brailleToRawPos()

	def bufferPosToRegionPos(self, bufferPos, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment].bufferPosToRegionPos(bufferPos)

	def regionPosToBufferPos(self, region, pos, allowNearest=False, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment].regionPosToBufferPos(region, pos, allowNearest)

	def bufferPositionsToRawText(self, startPos, endPos, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment].bufferPositionsToRawText(startPos, endPos)

	def bufferPosToWindowPos(self, bufferPos, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment].bufferPosToWindowPos(bufferPos)


	def _nextWindow(self, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[ssegment]._nextWindow()

	def _previousWindow(self, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment]._previousWindow()


	def _get_cursorWindowPos(self, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		if self.bufferSegments[segment]._get_cursorWindowPos() is not None:
			return self.getWindowLeadingCells(segment) + self.bufferSegments[segment]._get_cursorWindowPos()
		return self.bufferSegments[segment]._get_cursorWindowPos()

	def getTextInfoForWindowPos(self, windowPos, segment=-1):
		segment = segment if segment >=0 and segment < self.numOfSegments else self.focusBufferNumber 
		return self.bufferSegments[segment].getTextInfoForWindowPos(windowPos - self.getWindowLeadingCells(segment))

	def debugBuffer(self):
		text = ""
		text += "bufferSegments count: " + str(len(self.bufferSegments)) + "\n"
		text += "getWindowLeadingCells(1): " + str(self.getWindowLeadingCells(1)) + "\n" 
		text += "getWindowLeadingCells(focusBufferNumber): " + str(self.getWindowLeadingCells(self.focusBufferNumber)) + "\n"
		#text += "BrailleBufferContainer self.bufferSegments[-1].brailleCursorPos: " + str(self.bufferSegments[-1].brailleCursorPos) + "\n" 
		text += "BrailleBufferContainer self.bufferSegments[-1].cursorPos: " + str(self.bufferSegments[-1].cursorPos) + "\n" 
		text += "BrailleBufferContainer self.cursorPos: " + str(self.cursorPos) + "\n"
		text += "mainBuffer last region brailleCursorPos: " + str(braille.handler.mainBuffer.regions[-1].brailleCursorPos) + "\n"
		#text += "bufferPosToWindowPos: " + str(self.bufferPosToWindowPos(self.cursorPos)) + "\n"
		text += "bufferSegments[-1] windowStartPos: " + str(self.bufferSegments[-1].windowStartPos ) + "\n"
		text += "bufferSegments[-1] windowEndPos: " + str(self.bufferSegments[-1].windowEndPos ) + "\n"
		text += "braille.handler._cursorPos: " + str(braille.handler._cursorPos) + "\n"
		#text += "BrailleBufferContainer windowStartPos: " + str(self.windowStartPos ) + "\n"
		text += "BrailleBufferContainer windowEndPos: " + str(self.windowEndPos ) + "\n"
		text += "BrailleBufferContainer.cursorWindowPos: " + str(self.cursorWindowPos) + "\n"
		text += "region cursorPos: " + str(braille.handler.mainBuffer.regions[-1].cursorPos) + "\n"
		text += "Region: \n" + braille.handler.mainBuffer.regions[-1].rawText
		ui.browseableMessage(text, "BrailleBufferContainer log")



# BrailleHandler._doNewObject
def _doNewObjectMultiBuffer(self, regionIterator):
	#BrailleHandler._doNewObject does not know that the list of regions can now cover mutliple buffers and therefore objects with ancestors 
	# to keep focusToHardLeft working sort the regions into buffer specific lists first
	buffers = self.mainBuffer.numOfSegments
	#log.debug("doNewObjectMultiBuffer has numOfSegments " + str(buffers))
	if buffers > 1:
		#sort
		regions = list(regionIterator) 
		log.debug("doNewObject regions received "+ str(len(regions)) )
		for x in range(buffers): #look for targetSegment 0-buffers not most efficient but not that many objects 
			targeted = [] 
			for r in regions:
				if hasattr(r, "targetSegment") : 
					if r.targetSegment == x:  targeted.append(r) 
				#end inner for
			log.debug("not default buffer "+ str(x) +" doNewObject with non targeted segments " + str(len(targeted)))
			if len(targeted) > 0: _original_doNewObject(self, targeted) 
		# default regions made by NVDA don't have targetSegment do them last
		targeted = []
		for r in regions:
			if not hasattr(r, "targetSegment"):
				targeted.append(r) 
			#end for
		log.debug("final doNewObject with non targeted segments " + str(len(targeted)))
		if len(targeted) > 0: 
			braille.handler.mainBuffer.clear(x) #todo: original _doNewObject calls clear which clears focus buffer every time probably need rewrite it
			_original_doNewObject(self, targeted)

	else:
		#do original
		#log.debug("DoNewObjectMulti calling default")
		_original_doNewObject(self, regionIterator) 


#braille.BrailleHandler copied here for reference so far
def _doNewObjectOriginal(self, regions):
	self.mainBuffer.clear()
	focusToHardLeftSet = False
	for region in regions:
		if (
			self.getTether() == TetherTo.FOCUS.value
			and config.conf["braille"]["focusContextPresentation"] == CONTEXTPRES_CHANGEDCONTEXT
		):
			# Check focusToHardLeft for every region.
			# If noone of the regions has focusToHardLeft set to True, set it for the first focus region.
			if region.focusToHardLeft:
				focusToHardLeftSet = True
			elif not focusToHardLeftSet and getattr(region, "_focusAncestorIndex", None) is None:
				# Going to display a new object with the same ancestry as the previously displayed object.
				# So, set focusToHardLeft on this region
				# For example, this applies when you are in a list and start navigating through it
				region.focusToHardLeft = True
				focusToHardLeftSet = True
		self.mainBuffer.regions.append(region)
	self.mainBuffer.update()
	# Last region should receive focus.
	self.mainBuffer.focus(region)
	self.scrollToCursorOrSelection(region)
	if self.buffer is self.mainBuffer:
		self.update()
	elif self.buffer is self.messageBuffer and keyboardHandler.keyCounter>self._keyCountForLastMessage:
		self._dismissMessage()

def monkey_handleCaretMove(
	self,
	obj: "NVDAObject",
	shouldAutoTether: bool = True
) -> None:
	if not self.enabled:
		return
	if objectBelowLockScreenAndWindowsIsLocked(obj):
		return
	prevTether = self._tether
	if shouldAutoTether:
		self.setTether(TetherTo.FOCUS.value, auto=True)
	if self._tether != TetherTo.FOCUS.value:
		return
	region = self.mainBuffer.regions[-1] if self.mainBuffer.regions else None
	if region and region.obj==obj:
		region.pendingCaretUpdate=True
	elif prevTether == TetherTo.REVIEW.value:
		# The caret moved in a different object than the review position.
		self._doNewObject(getFocusRegions(obj, review=False))
	log.debug("caret moved in region %s" % region.rawText)

def monkey_handlePendingCaretUpdate(self):
	"""Checks to see if the final text region needs its caret updated and if so calls _doCursorMove for the region."""
	region=self.mainBuffer.regions[-1] if self.mainBuffer.regions else None
	if isinstance(region,TextInfoRegion) and region.pendingCaretUpdate:
		try:
			self._doCursorMove(region)
		finally:
			region.pendingCaretUpdate=False
	log.debug("caret pending update in region %s" % region.rawText)

def monkey_doCursorMove(self, region):
	self.mainBuffer.saveWindow()
	region.update()
	self.mainBuffer.update()
	self.mainBuffer.restoreWindow()
	self.scrollToCursorOrSelection(region)
	if self.buffer is self.mainBuffer:
		self.update()
	elif self.buffer is self.messageBuffer and keyboardHandler.keyCounter>self._keyCountForLastMessage:
		self._dismissMessage()
	log.debug("do_cursor_move in region %s" % region.rawText)


# monkey patches
#braille.BrailleHandler.handleCaretMove = monkey_handleCaretMove
#braille.BrailleHandler.handlePendingCaretUpdate = monkey_handlePendingCaretUpdate
#braille.BrailleHandler._doCursorMove = monkey_doCursorMove
_original_doNewObject = braille.BrailleHandler._doNewObject
braille.BrailleHandler._doNewObject = _doNewObjectMultiBuffer
oldMainBuffer = braille.handler.mainBuffer
#initialize here because _doNewObject is being monkey patched and that is causing errors before globalPlugin loads needeed if global plugin crashing
#braille.handler.mainBuffer = BrailleBufferContainer(braille.handler, 1) 


#move this to globalPlugin so can make buffers on the fly
#braille.handler.mainBuffer = BrailleBufferContainer(braille.handler, 1) 
#braille.handler.mainBuffer = BrailleBufferContainer(braille.handler, [10,70]) 
#braille.handler.buffer = braille.handler.mainBuffer
