import logging
import os
import signal
import sys
from pypylon import pylon as py
import numpy as np
# from multiprocessing import Process, Event
import socket
from select import select


class StopGuard:
    stop = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.int_rcvd)
        signal.signal(signal.SIGTERM, self.term_rcvd)

    def int_rcvd(self, signum, frame):
        logging.warning('Interrupt signal received')
        self.stop = True

    def term_rcvd(self, signum, frame):
        logging.warning('Terminate signal received')
        self.stop = True


stoppingGuard = StopGuard()


class PylonCam:

    def __init__(self):
        self.allPixelFormatNames = dict()
        self.allPixelFormatVals = dict()

        for attr in dir(py):
            if 'PixelType_' in attr:
                val = getattr(py, attr)
                self.allPixelFormatNames.update({attr: val})
                self.allPixelFormatVals.update({val: attr})
        self.pixelFormats = dict()

        self.cam = None
        self.IFC = None

        self.dType = None
        self.bytespp = None
        self.info = None
        self.SN = None
        self.W = None
        self.H = None
        self.f = None
        self.F = None
        self.fname = None
        self.mm = None
        self.grabbing = False

    def open_cam(self):
        self.cam = py.InstantCamera(py.TlFactory.GetInstance().CreateFirstDevice())
        self.IFC = py.ImageFormatConverter()

        for key, val in self.allPixelFormatNames.items():
            try:
                self.IFC.SetOutputPixelFormat(val)
                self.pixelFormats.update({key: val})
            finally:
                pass
        if 'PixelType_Mono16' in self.pixelFormats.keys():
            self.IFC.SetOutputPixelFormat(self.pixelFormats['PixelType_Mono16'])
            self.dType = 'uint16'
            self.bytespp = 2
        elif 'PixelType_Mono12' in self.pixelFormats.keys():
            self.IFC.SetOutputPixelFormat(self.pixelFormats['PixelType_Mono12p'])
            self.dType = 'uint16'
            self.bytespp = 2
        elif 'PixelType_Mono8' in self.pixelFormats.keys():
            self.IFC.SetOutputPixelFormat(self.pixelFormats['PixelType_Mono8'])
            self.dType = 'uint8'
            self.bytespp = 1

        self.info = self.cam.GetDeviceInfo()
        self.SN = self.info.GetSerialNumber()

        self.cam.Open()
        self.W = self.cam.Width()
        self.H = self.cam.Height()
        self.f = self.cam.PixelFormat.GetValue()
        self.cam.Close()

        self.fname = './Cam_' + self.SN + '__' + str(self.W) + 'x' + str(self.H) + '-' + self.f + '.npy'

        self.open_mm()

    def open_mm(self):
        del self.mm
        if not os.path.exists(self.fname):
            with open(self.fname, 'r+b') as f:
                f.write(b'\n' * (round(self.W * self.H * self.bytespp)))
        f = open(self.fname, 'r+b')
        self.mm = np.memmap(f, dtype=self.dType, mode='w', shape=(self.W, self.H))

    def release_cam(self):
        try:
            self.cam.StopGrabbing()
        finally:
            pass
        try:
            self.cam.Close()
        finally:
            pass


if os.path.exists('./FC4D.af_inet'):
    try:
        os.unlink('./FC4D.af_inet')
    except OSError as e:
        if os.path.exists('./FC4D.af_inet'):
            logging.error(e)
            raise e
serveSock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
serveSock.bind('./FC4D.af_inet')
serveSock.listen(10)

running = True
clients = []

while running and not stoppingGuard.stop:
    r, w, e = select([serveSock, ], [], [], 0)
    for request in r:
        client, addr = serveSock.accept()
        clients.append(client)
        logging.warning('Client connected @' + str(addr))
    r, w, e = select([clients, ], [], [], 0)

serveSock.shutdown(socket.SHUT_RDWR)
serveSock.close()
os.unlink('./FC4D.af_inet')
sys.exit()

'''
PixelType_BGR10V1packed ~ 35651612
PixelType_BGR10V2packed ~ 35651613
PixelType_BGR10packed ~ 36700185
PixelType_BGR12packed ~ 36700187
PixelType_BGR8packed ~ 35127317
PixelType_BGRA8packed ~ 35651607
PixelType_BayerBG10 ~ 17825807
PixelType_BayerBG10p ~ 17432658
PixelType_BayerBG12 ~ 17825811
PixelType_BayerBG12Packed ~ 17563693
PixelType_BayerBG12p ~ 17563731
PixelType_BayerBG16 ~ 17825841
PixelType_BayerBG8 ~ 17301515
PixelType_BayerGB10 ~ 17825806
PixelType_BayerGB10p ~ 17432660
PixelType_BayerGB12 ~ 17825810
PixelType_BayerGB12Packed ~ 17563692
PixelType_BayerGB12p ~ 17563733
PixelType_BayerGB16 ~ 17825840
PixelType_BayerGB8 ~ 17301514
PixelType_BayerGR10 ~ 17825804
PixelType_BayerGR10p ~ 17432662
PixelType_BayerGR12 ~ 17825808
PixelType_BayerGR12Packed ~ 17563690
PixelType_BayerGR12p ~ 17563735
PixelType_BayerGR16 ~ 17825838
PixelType_BayerGR8 ~ 17301512
PixelType_BayerRG10 ~ 17825805
PixelType_BayerRG10p ~ 17432664
PixelType_BayerRG12 ~ 17825809
PixelType_BayerRG12Packed ~ 17563691
PixelType_BayerRG12p ~ 17563737
PixelType_BayerRG16 ~ 17825839
PixelType_BayerRG8 ~ 17301513
PixelType_Double ~ -2127560448
PixelType_Mono10 ~ 17825795
PixelType_Mono10p ~ 17432646
PixelType_Mono10packed ~ 17563652
PixelType_Mono12 ~ 17825797
PixelType_Mono12p ~ 17563719
PixelType_Mono12packed ~ 17563654
PixelType_Mono16 ~ 17825799
PixelType_Mono1packed ~ -2130640884
PixelType_Mono2packed ~ -2130575347
PixelType_Mono4packed ~ -2130444274
PixelType_Mono8 ~ 17301505
PixelType_Mono8signed ~ 17301506
PixelType_RGB10packed ~ 36700184
PixelType_RGB10planar ~ 36700194
PixelType_RGB12V1packed ~ 35913780
PixelType_RGB12packed ~ 36700186
PixelType_RGB12planar ~ 36700195
PixelType_RGB16packed ~ 36700211
PixelType_RGB16planar ~ 36700196
PixelType_RGB8packed ~ 35127316
PixelType_RGB8planar ~ 35127329
PixelType_RGBA8packed ~ 35651606
PixelType_Undefined ~ -1
PixelType_YUV411packed ~ 34340894
PixelType_YUV422_YUYV_Packed ~ 34603058
PixelType_YUV422packed ~ 34603039
PixelType_YUV444packed ~ 35127328
'''
'''
{'PixelType_BGR8packed': 35127317,
 'PixelType_BGRA8packed': 35651607,
 'PixelType_Mono16': 17825799,
 'PixelType_Mono8': 17301505,
 'PixelType_RGB16packed': 36700211,
 'PixelType_RGB16planar': 36700196,
 'PixelType_RGB8packed': 35127316,
 'PixelType_RGB8planar': 35127329}
'''