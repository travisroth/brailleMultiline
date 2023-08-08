# coding: utf-8
# objectMonitor.py 
# part of brailleBufferMultiline
# addon for NVDA 
# Travis Roth, travis@travisroth.com

import braille
import config
from logHandler import log
import types
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
import controlTypes
import api
import textInfos
from NVDAObjects import NVDAObject
import copy 

class ObjectMonitor():
	def __init__(self, obj: NVDAObject, bufferNum: int) -> None:
		# @param obj: NVDAObject to track such as navigator object
		# @param bufferNum: buffer or line to display this object
		# @type bufferNum: int
		self._bufferNum = bufferNum
		self._obj = obj 
		# copy of the bufferSegments object tsthat generated holding Braille regions
		self._buffer = None 
		self.loadBuffer()
		#self.saveBuffer() 
		log.info("objectMonitor set on " +str(self._bufferNum) + " role "+str(self._obj.role))

	def loadBuffer(self):
		#braille.handler._doNewObject(self.getRegions())
		#let's try just copying the buffer
		fb = braille.handler.mainBuffer.focusBufferNumber 
		braille.handler.mainBuffer.bufferSegments[self._bufferNum].regions = braille.handler.mainBuffer.bufferSegments[fb].regions  

	def getRegions(self):
		monitor = self._obj 
		#if hasattr(self._obj, "treeInterceptor"):
			#story = self._obj.treeInterceptor.makeTextInfo(textInfos.POSITION_CARET)
			#story.collapse()
			#story.expand(textInfos.UNIT_STORY)
			#monitor = story 
		for region in braille.getFocusRegions(monitor, review=False):
			region.targetSegment = self._bufferNum
			yield region 

	def saveBuffer(self):
		try:
			#self._buffer = copy.deepcopy(braille.handler.mainBuffer.bufferSegments[self._bufferNum]) 
			self._buffer = braille.handler.mainBuffer.bufferSegments[self._bufferNum] 
		except:
			pass 
