import os, shutil
import os.path
from ij import IJ, WindowManager
from ij.plugin.frame import RoiManager
from ij.measure import ResultsTable
from ij.plugin.filter import ParticleAnalyzer, BackgroundSubtracter, EDM
from ij.io import FileSaver

'''
jython script for signal quantification of 3 ch + DAPI image  
file name format:
[date]_[animalID]_[ch0name]_[ch1name]_[ch2name]_[section#]_Processed_RAW_[ch#].tif
example:
20220101_B6J#1_DAPI_Gng8_Ecel1_Col12a1_01_Processed_RAW_ch01.tif
'''

OriginalDataDir = "/Path/to/directory/of/tif/files"
ProcessedDir = os.path.join(os.path.dirname(OriginalDataDir), "Processed")
TifDir = os.path.join(ProcessedDir, "tif")
MaskDir = os.path.join(ProcessedDir, "mask")
ROIDir = os.path.join(ProcessedDir, "ROI")
StatDir = os.path.join(ProcessedDir, "stat")
CompositeDir = os.path.join(ProcessedDir, "composite")

def closeWindowWitoutSave(title):
	IJ.selectWindow(title)
	imp = IJ.getImage()
	imp.changes = False
	imp.close()

def getWindowTitles():
	titles = []
	for i in WindowManager.getIDList():
		titles.append(WindowManager.getImage(i).getTitle())
	return titles

def s0(): #file copy
	for d in [OriginalDataDir, ProcessedDir, TifDir, MaskDir, ROIDir, StatDir, CompositeDir]:
		if not os.path.exists(d):
			os.mkdir(d)
	
	for r, d, files in os.walk(OriginalDataDir):
		for f in files:
			if f.endswith(".tif") and "Processed" in f and "ch0" in f:        	
				originalpath = os.path.join(r,f)
				SampleDirName = "_".join(f.split("_")[:-1]);
				SampleDirPath = os.path.join(TifDir, SampleDirName);
				if not os.path.exists(SampleDirPath):
					os.mkdir(SampleDirPath)
				copypath = os.path.join(SampleDirPath, f)
				shutil.copy(originalpath, copypath)

def s1(redo=False): #composite_selection
	compositeFlag = True
	if redo:
		s5(False)
		return
	for SampleDir in os.listdir(TifDir):
		Skip = False
		SampleDirPath = os.path.join(TifDir, SampleDir)
		if SampleDir.startswith("."):
			continue
		for f in ['_'.join(x.split("_")[:-1]) for x in os.listdir(MaskDir)]:
			if f in SampleDir:
				Skip = True
		if Skip:
			continue
		for f in os.listdir(SampleDirPath):
			if f.endswith("tif"):
				imagepath = os.path.join(SampleDirPath, f)
				IJ.open(imagepath)
		samplename = "_".join(f.split("_")[:-1])
		print "samplename: ", samplename
		break
	try:
		titles = getWindowTitles()
	except:
		print "All samples seem to be processed"
		return
	print titles
	if len(titles) < 4:
		print("This image set is not appropriate for this analysis: process is skipped")
		t=titles[0]
		print "title is ", t
		info = t.split("_")
		sampleinfo = "_".join(info[:-1])
		maskfilename = sampleinfo+'_Mask.tif'
		maskfilepath = os.path.join(MaskDir, maskfilename)
		IJ.selectWindow(t)
		imp = IJ.getImage()
		fs = FileSaver(imp) 
		fs.saveAsTiff(maskfilepath)
		for t in titles:
			closeWindowWitoutSave(t)
		return
	chTerms = ["ch00", "ch01", "ch02", "ch03"]
	chImageTitles = []
	for term in chTerms:
		for title in titles:
			if term in title:
				chImageTitles.append(title)
	
	mergeoption = " ".join(
		["c1="+chImageTitles[2], 
		"c2=" + chImageTitles[1], 
		"c3=" + chImageTitles[3],
		"c4=" + chImageTitles[0], 
		"create",
		"keep", 
		"ignore"])
	for f in os.listdir(CompositeDir):
		if samplename in f:
			compositeFlag = False
			compositepath = os.path.join(CompositeDir, f)
	if compositeFlag:
		IJ.run("Merge Channels...", mergeoption)
	else:
		IJ.open(compositepath)
		
def s2(redo=False, rerun = False): #masking
	print "s2 called as", redo
	titles = getWindowTitles()
	if redo:
		s5()
		s1()
		return
	for t in titles:
		if t.startswith("Composite"):
			if not rerun: 
				IJ.selectWindow(t)
				imp = IJ.getImage()
				IJ.run("Create Mask")
				#IJ.run("Invert") # inversion may be required in Windows
				imp = IJ.getImage()
		elif t.startswith("Mask"):
			if rerun:
				IJ.selectWindow(t)
				imp = IJ.getImage()

	for t in titles:
		if "ch00" in t:
			IJ.selectWindow(t)
			IJ.run("Duplicate...", "title=ch00_COPY")
			IJ.run("Duplicate...", "title=ch00_COPY2")
			IJ.selectWindow("ch00_COPY2")
	
	IJ.run("Subtract Background...", "rolling=40 disable") 
	IJ.run("Gaussian Blur...", "sigma=3")
	IJ.run("Add Image...", "image=Mask x=0 y=0 opacity=100 zero")
	imp = IJ.getImage()		
	IJ.run("Threshold...");

def s3(redo=False):
	print "s3 was called as " , redo
	titles = getWindowTitles()
	if redo:
		 for t in titles:
		 	if t.startswith("COPY"):
		 		closeWindowWitoutSave(t)
		 		s2(redo=False, rerun = True)
		 		return
	IJ.run("Invert");
	IJ.run("Convert to Mask");
	IJ.run("Watershed")
	imp = IJ.getImage()
	IJ.run("Flatten")
	IJ.run("8-bit")
	#IJ.run("Invert") # inversion may be required in Windows
	imp = IJ.getImage()
	rm = RoiManager().getInstance()
	rm.reset()
	rt = ResultsTable()
	PA = ParticleAnalyzer(8, 0, rt, 500, 2500, 0.1, 1.0)
	PA.setRoiManager(rm)
	PA.analyze(imp)
	IJ.selectWindow("ch00_COPY")
	IJ.run("From ROI Manager")
	IJ.selectWindow("Composite")
	roiArray = rm.getRoisAsArray()
	rm2.select(len(roiArray)-1)
	rm.runCommand("Set Color", "red", 0)
	rm.rename(len(roiArray)-1, "region_outline")

def s4(redo=False): 
	print "s4 was called as " , redo
	channels = ["ch01", "ch02", "ch03"]
	titles = getWindowTitles()
	if redo:
		for t in titles:
			if "COPY" in t and "ch00" not in t:
				closeWindowWitoutSave(t)
		return				
	rm = RoiManager().getInstance()
	channelnames = []
	for t in titles:
		if "ch03" in t:
			info = t.split("_")
			for i in range(len(info)):
				if info[i].startswith("DAPI"):
					channelnames.extend(info[i+1:i+4])
					break
			break
	sampleinfo = "_".join(info[:-1])
	IJ.run("Set Measurements...", "area mean min redirect=None decimal=3")
	savedfiles = []

	for t in titles:
		for c in channels:
			if c not in t:
				continue
			IJ.selectWindow(t)
			newtitle = "COPY_" + t
			IJ.run("Duplicate...", "title="+newtitle)
			IJ.selectWindow(newtitle)
			IJ.run("Select All")
			IJ.run("Subtract Background...", "rolling=0.5 disable")
			IJ.run("From ROI Manager")
		   	rm.runCommand('Measure')
		   	IJ.selectWindow("Results")
		   	statfilename = sampleinfo + "_" + c + ".csv" 
		   	savefilepath= os.path.join(StatDir, statfilename)
		   	IJ.saveAs("Results", savefilepath)
		   	savedfiles.append(savefilepath)
		   	IJ.run("Close") 
	
	results = []
	for f in savedfiles:
		for ch, chname in zip(channels, channelnames):
			if ch in f:
				column = []
				inf = open(f)
				inf.readline()# ignore header
				column.append("-".join([ch, chname]))
				for l in inf:
					column.append(l.split(",")[2])# add mean
				inf.close()
				results.append(column)
	
	summaryfilename = sampleinfo+"-summary.txt"
	summaryfilepath = os.path.join(StatDir, summaryfilename)
	outf = open(summaryfilepath,"w")
	for d1,d2,d3 in zip(results[0], results[1], results[2]):
		outf.write("\t".join([d1,d2,d3])+"\n")
	outf.close()

def s5(saveMask=True):
	titles = []
	for i in WindowManager.getIDList():
		titles.append(WindowManager.getImage(i).getTitle())
	channelnames = []
	for t in titles:
		if "ch03" in t:
			info = t.split("_")
			for i in range(len(info)):
				if info[i].startswith("DAPI"):
					channelnames.extend(info[i+1:i+4])
					break
	sampleinfo = "_".join(info[1:-1])

	maskfilename = sampleinfo+'_Mask.tif'
	maskfilepath = os.path.join(MaskDir, maskfilename)
	ROIimagefilename = sampleinfo+"_ROI.tif"
	ROIimagefilepath = os.path.join(ROIDir, ROIimagefilename)
	compositefilename = "Composite_" +sampleinfo+ ".tif"
	compositepath = os.path.join(CompositeDir, compositefilename)
	for t in titles:
		IJ.selectWindow(t)
		imp = IJ.getImage()
		if t.startswith("Mask") and saveMask:
			fs = FileSaver(imp) 
			fs.saveAsTiff(maskfilepath)
		elif t.startswith("ch00_COPY"):
			fs = FileSaver(imp)
			fs.saveAsTiff(ROIimagefilepath)
		elif t.startswith("Composite"):
			fs = FileSaver(imp)
			fs.saveAsTiff(compositepath)
		imp.changes = False
		imp.close()
	
	ROIfilename = sampleinfo + "_ROI.zip"
	ROIfilepath = os.path.join(ROIDir, ROIfilename)
	rm = RoiManager().getInstance()
	rm.runCommand("Save", ROIfilepath)
	rm.reset()

def goforward():
	status = checkStatus()
	print "go forward status ", status
	action = [s1, s2, s3, s4, s5]
	action[status]()

def goback():
	status = checkStatus()
	print "goback status ", status
	action = [s1, s2, s2, s4, s4]
	action[status](redo=True)

def checkStatus():
	try:
		titles = getWindowTitles()
	except:
		return 0
	print "# of opened widonw:",len(titles)
	if len(titles) == 0:
		return 0
	elif len(titles) == 5:
		return 1
	elif len(titles) == 8:
		return 2
	elif len(titles) == 9:
		return 3
	elif len(titles) == 12:
		return 4
		
from ij.gui    import NonBlockingGenericDialog
from java.awt.event   import ActionListener
from java.awt  import GridLayout,Button
class ButtonClic(ActionListener):

    def actionPerformed(self, event): # self (or this in Java) to state that the method will be associated to the class instances

        source = event.getSource()
        if source.label == "Go Forward":
        	print "go"
        	goforward()
        elif source.label == "Go Back":
        	print "back"
        	goback()
        elif source.label == "Reset":
        	s5(False)
s0()
gui = NonBlockingGenericDialog("Controler")
clicRecorder = ButtonClic()  
labels = ["Go Forward", "Go Back", "Reset"]
for l in labels:
	b=Button(l)
	b.addActionListener(clicRecorder)
	gui.add(b)
gui.setLayout(GridLayout(3,3))
gui.showDialog()