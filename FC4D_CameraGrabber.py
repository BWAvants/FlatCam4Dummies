import logging
import os
import signal
import sys
from pypylon import pylon as py
from pypylon import genicam
import numpy as np
# from multiprocessing import Process, Event
import socket
from select import select
from threading import Thread, Event
from queue import Queue, Full
from time import time

global stoppingGuard, running, pyCam


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
        self.opened = False

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
        self.grabber = None
        self.FPS = 0
        self.imageClients = []

    def open_cam(self):
        self.cam = py.InstantCamera(py.TlFactory.GetInstance().CreateFirstDevice())
        self.IFC = py.ImageFormatConverter()

        for key, val in self.allPixelFormatNames.items():
            try:
                self.IFC.SetOutputPixelFormat(val)
                self.pixelFormats.update({key: val})
            except genicam.RuntimeException:
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

        path_str = './Cam_' + self.SN + '__' + str(self.W) + 'x' + str(self.H) + '-' + self.f + '.npy'
        self.fname = os.path.abspath(path_str)
        print(self.fname)

        self.open_mm()

    def open_mm(self):
        if self.mm is not None:
            del self.mm
        if not os.path.exists(self.fname):
            with open(self.fname, 'w+b') as f:
                f.write(b'\n' * (round(self.W * self.H * self.bytespp)))
        f = open(self.fname, 'r+b')
        self.mm = np.memmap(f, dtype=self.dType, mode='w+', shape=(self.H, self.W))

    def release_cam(self):
        self.grabbing = False
        if self.cam is not None:
            try:
                self.cam.StopGrabbing()
            finally:
                try:
                    self.cam.Close()
                finally:
                    del self.mm
                    self.mm = None
                    logging.info('Camera Released')

    def add_image_client(self, image_client):
        if not image_client in self.imageClients:
            self.imageClients.append(image_client)

    def rem_image_client(self, image_client):
        if image_client in self.imageClients:
            self.imageClients.remove(image_client)


def grab_frames(pycam: PylonCam):
    pycam.grabbing = True
    last_time = 0
    diff_times = [0] * 10
    counter_time = 0
    pycam.cam.StartGrabbing(py.GrabStrategy_LatestImageOnly)
    while pycam.grabbing:
        grab_result = pycam.cam.RetrieveResult(5000, py.TimeoutHandling_ThrowException)
        if not pycam.grabbing:
            continue
        if grab_result.GrabSucceeded():
            pycam.mm[:] = grab_result.Array[:]
            this_time = grab_result.TimeStamp
            grab_result.Release()
            if last_time > 0:
                diff_times[counter_time] = this_time - last_time
                counter_time = (counter_time + 1) % 10
                if counter_time == 9:
                    pycam.FPS = 10000000000 / sum(diff_times)
            last_time = this_time

            for iClient in pycam.imageClients:
                sent = iClient.sendall(('cap:' + str(time()) + '\n').encode('utf-8'))
                if sent == 0:
                    iClient.close()
                    pycam.imageClients.remove(iClient)
    pycam.cam.StopGrabbing()


def manage_client(new_client, notification_event, message_queue):
    global running
    connected = True
    peername = str(new_client.getpeername())
    stream = ''
    logging.info('Client Manager Started')
    new_client.send('connected\n'.encode('utf-8'))
    while connected and running:
        r, w, e = select([new_client, ], [], [], 0.01)
        for c in r:
            try:
                data = c.recv(1024)
            except ConnectionResetError as e:
                logging.debug(e)
                connected = False
                try:
                    c.shutdown(socket.SHUT_RDWR)
                except OSError as e:
                    logging.debug(e)
                finally:
                    c.close()
                    logging.info('Client Disconnected: ' + peername)
                continue
            if len(data) == 0:
                connected = False
                try:
                    c.shutdown(socket.SHUT_RDWR)
                except OSError as e:
                    logging.debug(e)
                finally:
                    c.close()
                    logging.info('Client Disconnected: ' + peername)
            logging.debug('Data received: ' + data.decode('utf-8'))
            stream += data.decode('utf-8')
            while '\n' in stream and running:
                message, stream = stream.split('\n', 1)
                put_in_queue = False
                while not put_in_queue and running:
                    try:
                        message_queue.put([message, c], timeout=0.01)
                    except Full:
                        logging.debug(__name__ + ': Message Queue Full')
                    except Exception as e:
                        logging.error(e)
                    else:
                        put_in_queue = True
                notification_event.set()
    logging.info('Client Manager Closing: ' + peername)


def parse_message(message: str, client: socket.socket):
    global running, stoppingGuard, pyCam
    peername = str(client.getpeername())
    parts = message.split(':', 1)
    cmd = parts[0]
    if len(parts) > 1:
        argument = parts[1]
    else:
        argument = None
    if 'close' in cmd:
        running = False
        logging.info('Stop Command: ' + peername)
        client.send(b'Stop Command Received\n')
    elif 'release' in cmd:
        logging.info('Release Command: ' + peername)
        pyCam.release_cam()
        client.send(b'Release Command Received\n')
    elif 'open' in cmd:
        logging.info('Open Command: ' + peername)
        pyCam.open_cam()
        client.send(b'Open Command Received\n')
    elif 'activefile' in cmd:
        logging.info('Filename Request: ' + peername)
        if pyCam.fname is not None:
            client.send((pyCam.fname + ':' + str((pyCam.H, pyCam.W)) + ':' + pyCam.dType + '\n').encode('utf-8'))
    elif 'framedonotify' in cmd:
        pyCam.add_image_client(client)
        logging.info('Frame Client Added :' + peername)
        if pyCam.fname is not None:
            client.send((pyCam.fname + ':' + str((pyCam.H, pyCam.W)) + ':' + pyCam.dType + '\n').encode('utf-8'))
    elif 'farmenonotify' in cmd:
        pyCam.rem_image_client(client)
        logging.info('Frame Client Removed : ' + peername)
        client.send(b'Unsubscribed\n')
    elif 'stream' in cmd:
        if not pyCam.opened:
            pyCam.open_cam()
        if pyCam.grabber is None:
            pyCam.grabber = Thread(target=grab_frames, args=(pyCam, ))
            pyCam.grabber.start()
    elif 'stop' in cmd:
        if pyCam.grabbing:
            pyCam.grabbing = False
            while pyCam.grabber.is_alive():
                pyCam.grabber.join(0.01)
            pyCam.grabber = None


if __name__ == '__main__':

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--log_level', help='Specify log verbosity')

    args = parser.parse_args()
    if args.log_level:
        if 'critical' in args.log_level:
            logging.basicConfig(level=logging.CRITICAL)
        elif 'error' in args.log_level:
            logging.basicConfig(level=logging.ERROR)
        elif 'warning' in args.log_level:
            logging.basicConfig(level=logging.WARNING)
        elif 'info' in args.log_level:
            logging.basicConfig(level=logging.INFO)
        elif 'debug' in args.log_level:
            logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    logging.debug('Starting up CameraGrabber')

    stoppingGuard = StopGuard()

    pyCam = PylonCam()

    serveSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serveSock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serveSock.bind(('127.0.0.1', 0xFC4D))
    serveSock.listen(128)

    running = True
    clients = []
    notification_event = Event()
    message_queue = Queue()

    while running and not stoppingGuard.stop:
        r, w, e = select([serveSock, ], [], [], 0)
        for request in r:
            client, addr = serveSock.accept()
            logging.info('Client connected @' + str(addr))
            new_client = Thread(target=manage_client, args=(client, notification_event, message_queue))
            new_client.start()
            clients.append(new_client)
        if notification_event.wait(0.01):
            while not message_queue.empty() and running and not stoppingGuard.stop:
                message, client = message_queue.get()
                parse_message(message, client)
            notification_event.clear()

    logging.warning('Shutting Down')
    running = False
    pyCam.release_cam()
    serveSock.close()
    for c in clients:
        while c.is_alive():
            c.join(0.01)
    sys.exit()


# PixelType_BGR10V1packed ~ 35651612
# PixelType_BGR10V2packed ~ 35651613
# PixelType_BGR10packed ~ 36700185
# PixelType_BGR12packed ~ 36700187
# PixelType_BGR8packed ~ 35127317
# PixelType_BGRA8packed ~ 35651607
# PixelType_BayerBG10 ~ 17825807
# PixelType_BayerBG10p ~ 17432658
# PixelType_BayerBG12 ~ 17825811
# PixelType_BayerBG12Packed ~ 17563693
# PixelType_BayerBG12p ~ 17563731
# PixelType_BayerBG16 ~ 17825841
# PixelType_BayerBG8 ~ 17301515
# PixelType_BayerGB10 ~ 17825806
# PixelType_BayerGB10p ~ 17432660
# PixelType_BayerGB12 ~ 17825810
# PixelType_BayerGB12Packed ~ 17563692
# PixelType_BayerGB12p ~ 17563733
# PixelType_BayerGB16 ~ 17825840
# PixelType_BayerGB8 ~ 17301514
# PixelType_BayerGR10 ~ 17825804
# PixelType_BayerGR10p ~ 17432662
# PixelType_BayerGR12 ~ 17825808
# PixelType_BayerGR12Packed ~ 17563690
# PixelType_BayerGR12p ~ 17563735
# PixelType_BayerGR16 ~ 17825838
# PixelType_BayerGR8 ~ 17301512
# PixelType_BayerRG10 ~ 17825805
# PixelType_BayerRG10p ~ 17432664
# PixelType_BayerRG12 ~ 17825809
# PixelType_BayerRG12Packed ~ 17563691
# PixelType_BayerRG12p ~ 17563737
# PixelType_BayerRG16 ~ 17825839
# PixelType_BayerRG8 ~ 17301513
# PixelType_Double ~ -2127560448
# PixelType_Mono10 ~ 17825795
# PixelType_Mono10p ~ 17432646
# PixelType_Mono10packed ~ 17563652
# PixelType_Mono12 ~ 17825797
# PixelType_Mono12p ~ 17563719
# PixelType_Mono12packed ~ 17563654
# PixelType_Mono16 ~ 17825799
# PixelType_Mono1packed ~ -2130640884
# PixelType_Mono2packed ~ -2130575347
# PixelType_Mono4packed ~ -2130444274
# PixelType_Mono8 ~ 17301505
# PixelType_Mono8signed ~ 17301506
# PixelType_RGB10packed ~ 36700184
# PixelType_RGB10planar ~ 36700194
# PixelType_RGB12V1packed ~ 35913780
# PixelType_RGB12packed ~ 36700186
# PixelType_RGB12planar ~ 36700195
# PixelType_RGB16packed ~ 36700211
# PixelType_RGB16planar ~ 36700196
# PixelType_RGB8packed ~ 35127316
# PixelType_RGB8planar ~ 35127329
# PixelType_RGBA8packed ~ 35651606
# PixelType_Undefined ~ -1
# PixelType_YUV411packed ~ 34340894
# PixelType_YUV422_YUYV_Packed ~ 34603058
# PixelType_YUV422packed ~ 34603039
# PixelType_YUV444packed ~ 35127328
#
# {'PixelType_BGR8packed': 35127317,
#  'PixelType_BGRA8packed': 35651607,
#  'PixelType_Mono16': 17825799,
#  'PixelType_Mono8': 17301505,
#  'PixelType_RGB16packed': 36700211,
#  'PixelType_RGB16planar': 36700196,
#  'PixelType_RGB8packed': 35127316,
#  'PixelType_RGB8planar': 35127329}
