#!/usr/bin/env python
'''module for real time place preference test'''

import os
import sys
import time
import datetime
import copy
import threading
import queue
import argparse
import subprocess
import cv2
import skvideo.io
import numpy as np
from gpiozero import LED
from picamera import PiCamera
from picamera.array import PiRGBArray

#global variables for cv2.setMouseCallback
cordinates = np.zeros((3, 4), dtype=np.int)
mode = 0
draw = False

def define_area(event, x, y, flag, parm):
    '''mouse callback function: store box cordinates.
       mode 0: to draw a box for a whole field
       mode 1: to draw 1st box
       mode 2: to draw 2nd box       mode 3: area setting done
    '''
    global mode, img, draw
    global cordinates
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 0, 0)]
    messages = ['Draw 1st box(green)',
                'Draw 2nd box(red)',
                'press "s" to start the session']
    # left button click
    if event == cv2.EVENT_LBUTTONDOWN and mode < 3: 
        draw = True
        cv2.imshow('area setting', img)
        cordinates[mode][0] = x
        cordinates[mode][1] = y
        print('box {}, start {},{}'.format(mode, x, y))
    # left button hold-move
    elif event == cv2.EVENT_MOUSEMOVE and draw and mode < 3:
        tempimg = copy.copy(img)
        tempx = cordinates[mode][0]
        tempy = cordinates[mode][1]
        cv2.rectangle(tempimg, (tempx, tempy) , (x, y), colors[mode], 2)
        cv2.imshow('area setting', tempimg)
    # left button release
    elif event == cv2.EVENT_LBUTTONUP and mode < 3:
        print('box {}, end {},{}'.format(mode, x, y))
        cordinates[mode][2], cordinates[mode][3] = x, y
        rectstx, rectsty = cordinates[mode][0], cordinates[mode][1]
        cv2.rectangle(img, (rectstx, rectsty), (x, y), colors[mode], 2)
        outline_text(img, messages[mode], (20, 60 + 20 * mode)
                     , cv2.FONT_HERSHEY_SIMPLEX, 0.5, colors[mode + 1], 1)
        mode += 1
        draw = False
        cv2.imshow('area setting', img)

def adjust_box(box, box0):
    '''adjust cordinates in box by those of box0'''
    box[0] = max(0, box[0] - box0[0])
    box[1] = min(box[1] - box0[0], box0[1] - box0[0])
    box[2] = max(0, box[2] - box0[2])
    box[3] = min(box[3] - box0[2], box0[3] - box0[2])
    return box

def in_box(x, y, box):
    ''' return True if (x,y) in box'''
    xmin, xmax, ymin, ymax = box
    return bool(x >= xmin and x <= xmax and y >= ymin and y <= ymax)

def outline_text(im, text, location, font, size, color, thikness):
    '''place text with white outline'''
    cv2.putText(im, text, location, font, size, (255, 255, 255), thikness*2, lineType=cv2.LINE_AA)
    cv2.putText(im, text, location, font, size, color, thikness, lineType=cv2.LINE_AA)


def compress(q,image):
    ''' compress the image and put it to the queue'''
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50] 
    result, encimg = cv2.imencode('.jpg', image, encode_param)
    q.put(encimg)
    q.task_done()

class RPP(object):
    '''Conditioned place preference test'''
    def __init__(self, animalID, sessionlength=10, noalternate=False, **keywords):
        '''initializing RPP object'''
        self.animalID = animalID
        self.dir = keywords.get('dir', './')
        self.camera = PiCamera()
        self.camera.resolution = keywords.get('resolution', (704, 350))
        self.camera.brightness = 70
        self.camera.contrast = 100
        self.camera.framerate = keywords.get('framerate', 10)
        self.pulselength = keywords.get('pulselength', 10)
        self.frequency = keywords.get('frequency', 20)
        self.threshold = keywords.get('threshold', 30)
        self.adaptation = keywords.get('adaptation', 20)
        self.pre_session = keywords.get('pre_session', 10)
        self.breaktime = keywords.get('breaktime', 0)
        if keywords.get('right_first', True):
            self.firstbox = 'right'
        else:
            self.firstbox = 'left'
        self.pin = keywords.get('pin', 14)
        self.savevideo = keywords.get('savevideo', False)
        self.sessionlength = sessionlength
        self.noalternate = noalternate
        self.framelist = []
        self.locationlist = []
        self.ontime = min(0.001 * self.pulselength, 0.5 / self.frequency)
        self.offtime = 1/self.frequency - self.ontime
        self.dirpath = os.path.join(self.dir, '-'.join([self.animalID, datetime.datetime.now().strftime('%Y%m%d%H%M')]))
        self.logpath = os.path.join(self.dirpath, 'log.txt')
        if not os.path.exists(self.dirpath):
            os.mkdir(self.dirpath)
        self.imagedirpath = os.path.join(self.dirpath, 'images')
        if not os.path.exists(self.imagedirpath):
            os.mkdir(self.imagedirpath)
        self.log = open(self.logpath, 'w')
        self.laser_switch_settings = [0, 1, 0, 2]
        # 0: laser off, 1: laser on in box1, 2: laser on in box2
        self.period = 0
        first_session_start = self.pre_session * 60
        break_start = first_session_start + self.sessionlength * 60
        second_session_start = break_start +  self.breaktime * 60
        second_session_end = second_session_start + self.sessionlength * 60
        if self.noalternate:
            self.times = [first_session_start, break_start]
        else:
            self.times = [first_session_start, break_start, second_session_start, second_session_end]
        self.trigger = LED(self.pin)
        self.trigger.off()

    def initial_log(self):
        '''record info before start a recording sesion'''
        self.record_log('animal ID: {}\n'.format(self.animalID))
        self.record_log('session date: {}\n'.format(datetime.date.today()))
        self.record_log('adaptation time: {} min\n'.format(self.adaptation))
        self.record_log('pre_session: {} min\n'.format(self.pre_session))
        self.record_log('session length: {} min\n'.format(self.sessionlength))
        if self.noalternate:
            self.record_log('activated side: {}\n'.format(self.firstbox))
        else:
            self.record_log('activated alternatively. first side:{}\n'.format(self.firstbox))
            self.record_log('break between session: {} min\n'.format(self.breaktime))
        self.record_log('video resolution: {} x {}\n'.format(*self.camera.resolution))
        self.record_log('video frame rate: {} fps\n'.format(self.camera.framerate))
        self.record_log('stimulation pulse length: {} ms'.format(self.ontime * 1000))
        if self.ontime < 0.001 * self.pulselength:
            self.record_log('(adjusted by stimulaiton frequency)\n')
        else:
            self.record_log('\n')
        self.record_log('stimulation frequency: {} Hz\n'.format(self.frequency))

    def record_log(self, text):
        '''write text in log and stdout'''
        self.log.write(text)
        sys.stdout.write(text)

    def set_camera(self):
        ''' setting camera condition before session'''
        cap = PiRGBArray(self.camera, size=self.camera.resolution)
        cv2.namedWindow('camera setting')
        for frame in self.camera.capture_continuous(cap, format='bgr', use_video_port=True):
            image = frame.array
            key = cv2.waitKey(1)&0xFF
            if key == ord('o'):
                break
            elif key == ord('c'):
                self.camera.contrast = max(0, self.camera.contrast - 1)
            elif key == ord('C'):
                self.camera.contrast = min(100, self.camera.contrast + 1)
            elif key == ord('b'):
                self.camera.brightness = max(0, self.camera.brightness - 1)
            elif key == ord('B'):
                self.camera.brightness = min(100, self.camera.brightness + 1)
            elif key == ord('t'):
                self.threshold = max(0, self.threshold -1)
            elif key == ord('T'):
                self.threshold = min(255, self.threshold + 1)
            try:
                x, y = self.get_center(image)
            except:
                pass
            outline_text(image, 'Set camera condition. "c"/"C" for contrast, "b"/"B" for brightness'
                        , (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            outline_text(image, '"t"/"T" for binarization threshold, "o" for OK'
                        , (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
            outline_text(image, 'TURN LASER ON NOW', (10, 90), cv2.FONT_HERSHEY_SIMPLEX
                         , 0.5, (0, 0, 0), 1)
            cv2.imshow('camera setting', image)
            cap.truncate(0)
        self.originalimg = copy.copy(image)
        cv2.destroyAllWindows()

    def sort_cordinate(self, box):
        ''' sort [x1, y1, x2, y2] cordinates to  [minx, maxx, miny, maxy]'''
        x1, y1, x2, y2 = box
        sorted_cordinates = sorted([x1, x2]) + sorted([y1, y2])
        # adjust cordinates between 0 and camera.resolution
        sorted_cordinates = [x if x>= 0 else 0 for x in sorted_cordinates]
        for i in [0, 1]:
            sorted_cordinates[i] = min(sorted_cordinates[i], self.camera.resolution[0])
        for i in [2, 3]:
            sorted_cordinates[i] = min(sorted_cordinates[i], self.camera.resolution[1])
        return sorted_cordinates

    def set_area(self):
        ''''set areas for RPP'''
        global cordinates
        global img, mode
        img = copy.copy(self.originalimg)
        cv2.imshow('area setting', img)
        outline_text(img, 'press "r" for reset', (20, 20), cv2.FONT_HERSHEY_SIMPLEX
                     , 0.5, (0, 0, 0), 1)
        outline_text(img, 'draw a box for the entire field(blue)', (20, 40)
                    , cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
        cv2.namedWindow('area setting')
        cv2.setMouseCallback('area setting', define_area)
        while True:
            cv2.imshow('area setting', img)
            k = cv2.waitKey(0) & 0xFF
            if k == ord('s') and mode >= 3:
                outline_text(img, 'selected area has been saved', (30, 400)
                     , cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
                cv2.imshow('area setting', img)
                time.sleep(1)
                break
            elif k == ord('r'):
                img = copy.copy(self.originalimg)
                outline_text(img, 'draw a box for the entire field(blue)', (20, 40)
                             , cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
                cv2.imshow('area setting', img)
                mode = 0
        [box_0, box_1, box_2] = cordinates
        boximagepath = os.path.join(self.imagedirpath, 'boximage.jpg')
        cv2.imwrite(boximagepath, img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        time.sleep(1)
        cv2.destroyAllWindows()
        self.record_log('box0: ({}, {}) x ({}, {})\n'.format(*box_0))
        self.record_log('box1: ({}, {}) x ({}, {})\n'.format(*box_1))
        self.record_log('box2: ({}, {}) x ({}, {})\n'.format(*box_2))
        self.box0 = self.sort_cordinate(box_0)
        box1 = self.sort_cordinate(box_1)
        box2 = self.sort_cordinate(box_2)
        self.box1 = adjust_box(box1, self.box0)
        self.box2 = adjust_box(box2, self.box0)
        if self.firstbox == 'right': #default
            if self.box1[1] > self.box2[1]: # if box1 is located right
                self.boxorder = [self.box1, self.box2]
            else:
                self.boxorder = [self.box2, self.box1]
        else: # starts with left side
            if self.box1[1] < self.box2[1]: # if box1 is located left
                self.boxorder = [self.box1, self.box2]
            else: # if box1 is located right
                self.boxorder = [self.box2, self.box1]
        self.record_log('adjusted box1 cordinates :({0}, {2}) x ({1}, {3})\n'.format(*self.box1))
        self.record_log('adjusted box2 cordinates :({0}, {2}) x ({1}, {3})\n'.format(*self.box2))

    def habituation(self):
        s = time.time()
        adaptation_time = self.adaptation * 60
        cap = PiRGBArray(self.camera, size=self.camera.resolution)
        for frame in self.camera.capture_continuous(cap, format='bgr', use_video_port=True):
            image = frame.array
            key = cv2.waitKey(1)&0xFF
            if key == ord('q'):
                break
            current_remain = adaptation_time- (time.time()-s)
            if current_remain <= 0:
                break
            elif current_remain > 60:
                remaining = "{} min".format(int(current_remain/60))
            else:
                remaining = "{} sec".format(int(current_remain))
            outline_text(image,'adaptation_time: {} left. "q" for quiting adaptation'.format(remaining)
                         , (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (20, 20, 20), 2)
            cv2.imshow('live', image)
            cap.truncate(0)
        cv2.destroyAllWindows()

    def get_center(self, image):
        '''find the laregest controur from an image and retrun the cordinate of its moment center'''
        grayimage = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        retVal, binary_image = cv2.threshold(grayimage, self.threshold, 255, cv2.THRESH_BINARY_INV)
        contours, hierarchy = cv2.findContours(binary_image, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
        target = max(contours, key =cv2.contourArea)
        M = cv2.moments(target)
        x = int(M['m10'] / M['m00'])
        y = int(M['m01'] / M['m00'])
        cv2.circle(image, (x,y), 5, (255,255,255), -1)
        return (x, y)

    def switch_laser(self, image):
        '''turn on/off laser by finding the center of target in the image'''
        try:
            x, y = self.get_center(image)
            in_box1 = in_box(x, y, self.box1)
            if self.laser_switch_settings[self.period]: # if in a session
                if in_box(x, y, self.boxorder[self.laser_switch_settings[self.period] - 1]):
                    # if the target in the box
                    outline_text(image, 'ON', (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0 , 0, 255), 2)
                    if self.trigger.value == 0: # if laser was off
                        self.trigger.on()
                        self.trigger.blink(on_time=self.ontime, off_time=self.offtime)
                else: # if the target is not in the box
                    outline_text(image, 'OFF', (30, 50), cv2.FONT_HERSHEY_SIMPLEX,1, (20, 20, 20), 2)
                    self.trigger.off()
            else:  # if not in a session
                self.trigger.off()
                if self.period == 0:
                    outline_text(image,'presession', (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (20, 20, 20), 2)
                else:
                    outline_text(image,'break', (30 ,50), cv2.FONT_HERSHEY_SIMPLEX, 1, (20, 20, 20), 2)
        except: #if either finding contrast or center fails
            outline_text(image,'cannot detect', (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (20, 20, 20), 2)
            self.trigger.off()
            x, y = 0, 0
            in_box1 = np.nan # record as NAN if location unidentifiable
        return x, y, in_box1

    def tracking(self):
        '''track animal and turn on/off laser'''
        Q = queue.Queue()
        cap = PiRGBArray(self.camera, size=self.camera.resolution)
        self.record_log('session start:{}\n'.format(datetime.datetime.now()))
        sessionst = time.time()
        for frame in self.camera.capture_continuous(cap, format='bgr', use_video_port=True):
            image = frame.array
            T = threading.Thread(target=compress, args=(Q, image,))
            T.start() 
            key = cv2.waitKey(1)&0xFF
            if key == ord('q'):
                break
            current_time = time.time() - sessionst
            if current_time >= self.times[self.period]:
                self.period += 1
            if self.period == len(self.times):
                break
            # trim image accroding to box cordinates
            image = image[self.box0[2]:self.box0[3], self.box0[0]:self.box0[1]]
            x, y, in_box1 = self.switch_laser(image)
            self.locationlist.append((self.period, x, y, in_box1, self.trigger.value, current_time))
            # save info:  period, x cordinate, y cordinate, in_box1, if trigger was on, time
            T.join()
            cv2.imshow('live', image)
            self.framelist.append(Q.get())
            cap.truncate(0)
        cv2.destroyAllWindows()
        sys.stdout.write('image collection done\n')
        self.record_log('session end:{}\n'.format(datetime.datetime.now()))
        self.camera.close()
        self.trigger.off()

    def save_data(self):
        '''save image and location data'''
        sys.stdout.write('start saving file\n')
        if self.savevideo:
            videopath = os.path.join(self.dirpath, 'video.mp4')
            v = skvideo.io.FFmpegWriter(videopath)
            for i in range(len(self.framelist)):
                image = cv2.imdecode(self.framelist[i], 1)
                v.writeFrame(image)
                if i%10 == 0:
                    sys.stdout.write('\rprogress: {:3.2f} %'.format(100 * i / len(self.framelist)))
            sys.stdout.write('\rprogress: 100.00 %\n')
            v.close()
        else:
            for i in range(len(self.framelist)):
                jpgpath = os.path.join(self.imagedirpath, str(i) + '.jpg')
                outf = open(jpgpath, 'wb')
                outf.write(self.framelist[i])
                outf.close()
                if i % 10 == 0:
                    sys.stdout.write('\rprogress: {:3.2f} %'.format(100 * i / len(self.framelist)))
            sys.stdout.write('\rprogress: 100.00 %\n')
            sys.stdout.write("compressing image directory\n")
            archivepath = os.path.join(self.dirpath, "images.tar.gz")
            command1 = ["tar", "-czf", archivepath, self.imagedirpath]
            command2 = ["rm", "-r", self.imagedirpath]
            subprocess.call(command1)
            subprocess.call(command2)
        locationfilepath = os.path.join(self.dirpath, 'location.txt')
        outf = open(locationfilepath, 'w')
        outf.write('\t'.join(['period', 'x', 'y', 'in_box1', 'stimulation', 'time'])+'\n')
        for info in self.locationlist:
            outf.write('\t'.join([str(x) for x in info])+'\n')
        outf.close()
        self.log.close()
        sys.stdout.write('saving done\n')

if __name__ == '__main__':  
    parser = argparse.ArgumentParser()
    parser.add_argument('animalID', type=str, help='animal ID')
    parser.add_argument('-d', '--dir', type=str, default='./', help='data directory')
    parser.add_argument('-s', '--session', type=int, default=10
                        , help='length of each session in minutes(default:10)')
    parser.add_argument('-n', '--noalternate', action='store_true'
                        , help='not switching stimulation room in the second half (default: alternating)')
    parser.add_argument('-a', '--adaptation', type=int, default=20
                        , help="time for adaptation (default: 20)")
    parser.add_argument('-b', '--pre_session', type=int, default=10
                        , help='minutes before session start(default=10)')
    parser.add_argument('-B', '--breaktime',  type=int, default=0
                        , help='break length in min between session 1 and 2(default:0)')
    parser.add_argument('-x', '--xresolution', type=int, default=704
                        , help='video resolution, x axis(default:704)')
    parser.add_argument('-y', '--yresolution', type=int, default=400
                        , help='video resolution, y axis(default:350)')
    parser.add_argument('-f', '--framerate', type=int, default=10
                        , help='video framerate(fps, default:10)')
    parser.add_argument('-z', '--hz', type=int, default=20
                        , help='stimulation frequency(Hz,default:20)')
    parser.add_argument('-p', '--pulselength', type=int, default=10
                        , help='length of pulse(ms, default:10)')
    parser.add_argument('-l', '--left', action='store_false'
                        , help='stimulation starts on left side(default: right)')
    parser.add_argument('-i', '--pin', type=int, default=14
                        , help='GPIO PIN# for the trigger (default:14)')
    parser.add_argument('-t', '--threshold', type=int, default=30
                        , help='threshold for binarizing images(default:30)')
    parser.add_argument('--savevideo', action='store_true'
                        , help='save a video file, not image files(take time)')
    args = parser.parse_args()
    R = RPP(args.animalID, args.session, args.noalternate, dir=args.dir
            , resolution=(args.xresolution, args.yresolution)
            , framerate=args.framerate, frequency=args.hz, breaktime=args.breaktime, adaptation=args.adaptation
            , pre_session=args.pre_session, pulselength=args.pulselength
            , threshold=args.threshold, right_first=args.left, pin=args.pin, savevideo=args.savevideo)
    R.initial_log()
    sys.stderr.write('start recording {}\n'.format(args.animalID))
    sys.stderr.write('select box areas\n')
    R.set_camera()
    R.set_area()
    R.habituation()
    R.tracking()
    R.save_data()
    while True:
        keyinp = input("ready to end (y/Y)? Is laser turned down/off?")
        if keyinp in ("y", "Y"):
            break
    R.trigger.close() # TL will be released


