# 2022_PVT_celltype_paper
original codes related Shima et al.

## RPP.py
### requirement
- RaspberryPi 3/4
- TTL controled LED/laser
- a camera conencted to RaspberryPi
### dependency
- cv2
- skvideo.io
- numpy
- gpiozero
- picamera
### usage
/path/to/the/directory/of/the/code/RPP.py [-options] [animal ID] 
See help (-h) for details.


## quantification_pipeline.py
### usage
1. From Fiji, File->New->script, then open the script file.
2. After changing the path to a directory with original tif files, click the "Run" button. 
3. On the composite image, select areas with one of selection tools, then click "Go forward"
4. On the image of ROI of DAPI signal, adjust threshold and apply it. Click "Go forward"
5. Check ROIs of each cell. Add/remove ROIs.Click "Go forward".
6. Click "Go forward" to measure signals.

We found Mask function of Fiji worked differently in MacOS and Windows.
You may have to add/remove inversion steps depending on the OS (see comments on the script).
