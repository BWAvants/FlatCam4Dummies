from tkinter import *
from PIL import Image, ImageTk
from os.path import realpath
import numpy as np
from pypylon import pylon as py
from threading import Thread, Event
# from multiprocessing import Process, Event as mpEvent

pwd = realpath(__file__)
pwd = pwd[:pwd.rindex('\\') + 1]

resample = Image.BILINEAR
# resample = Image.BICUBIC
# resample = Image.LANCZOS


class Window(Frame):

    def __init__(self, master=None):
        Frame.__init__(self, master)
        self.master = master
        self.camera = None
        self.IFC = None
        self.camImg = None
        self.imgWig = None
        self.capturing = False
        self.captureWorker = None
        self.showWorker = None
        self.newFrame = Event()
        self.oldW = self.winfo_width
        self.oldH = self.winfo_height
        self.iw = self.oldW
        self.ih = self.oldH
        self.file = None
        self.edit = None
        self.resizePending = False
        self.init_window()


    def init_window(self):
        self.master.title('FlatCam4Dummies')

        self.pack(fill=BOTH, expand=1)
        self.configure(background='black')

        master_menu = Menu(self.master)
        self.master.config(menu=master_menu)

        self.file = Menu(master_menu)
        self.file.add_command(label='Quit', command=self.client_exit)
        master_menu.add_cascade(label='File', menu=self.file)

        self.edit = Menu(master_menu)
        self.edit.add_command(label='Stream Camera', command=self.stream_camera)
        master_menu.add_cascade(label='Image', menu=self.edit)

        self.camera = py.InstantCamera(py.TlFactory.GetInstance().CreateFirstDevice())
        self.IFC = py.ImageFormatConverter()
        self.IFC.SetOutputPixelFormat(py.PixelType_Mono16)
        # self.camera.Open()
        # self.camera.PixelFormat.SetValue('Mono12')
        # self.camera.StartGrabbing(py.GrabStrategy_LatestImageOnly)
        # self.showImg()

    def stream_camera(self):
        # text = Label(self, text='Flat Cam 4 Dummies')
        # text.pack()
        if not self.capturing:
            self.camera.Open()
            self.camera.StartGrabbing(py.GrabStrategy_LatestImageOnly)
            self.captureWorker = Thread(target=self.capture_frames)
            self.showWorker = Thread(target=self.show_frames)
            self.capturing = True
            self.captureWorker.start()
            self.showWorker.start()
            self.edit.entryconfigure('Stream Camera', label='Stop Camera')
        else:
            self.capturing = False
            self.captureWorker.join(1)
            self.captureWorker = None
            self.camera.Close()
            self.edit.entryconfigure('Stop Camera', label='Stream Camera')

    def capture_frames(self):
        # self.camera.ExecuteSoftwareTrigger()
        lastTime = 0
        diffTimes = [0] * 10
        frameCounter = 0
        while self.capturing:
            grabResult = self.camera.RetrieveResult(5000, py.TimeoutHandling_ThrowException)
            if not self.capturing:
                continue
            # self.camera.ExecuteSoftwareTrigger()
            if grabResult.GrabSucceeded():
                thisTime = grabResult.TimeStamp
                if not self.newFrame.is_set():
                    imgt = np.copy(grabResult.Array)
                    grabResult.Release()
                    if lastTime > 0:
                        diffTimes[frameCounter] = thisTime - lastTime
                    lastTime = thisTime
                    frameCounter = (frameCounter + 1) % 10
                    if frameCounter == 9:
                        print(10000000000 / sum(diffTimes))
                    self.camImg = Image.fromarray((imgt[0::1, 0::1] / 16).astype('uint8'))
                    self.newFrame.set()
                else:
                    grabResult.Release()
                    diffTimes[frameCounter] = thisTime - lastTime
                    lastTime = thisTime
                    frameCounter = (frameCounter + 1) % 10
                    if frameCounter == 9:
                        print(10000000000 / sum(diffTimes))
        self.camera.StopGrabbing()

    def show_frames(self):
        while self.capturing:
            if self.newFrame.wait(0.01):
                ratio = self.camImg.width / self.camImg.height
                if self.imgWig is None:
                    mw, mh = (self.winfo_width(), self.winfo_height())
                    self.oldW = mw
                    self.oldH = mh
                    if mw >= mh * ratio:
                        self.ih = mh
                        self.iw = round(mh * ratio)
                    else:
                        self.iw = mw
                        self.ih = round(mw / ratio)
                    self.camImg = ImageTk.PhotoImage(self.camImg.resize((self.iw, self.ih), resample))
                    self.imgWig = Label(self, image=self.camImg)
                    self.imgWig.place(relx=0.5, rely=0.5, width=self.iw, height=self.ih, anchor=CENTER)
                else:
                    mw, mh = (self.winfo_width(), self.winfo_height())
                    if self.oldH != mh or self.oldW != mw:
                        if mw >= mh * ratio:
                            self.ih = mh
                            self.iw = round(mh * ratio)
                        else:
                            self.iw = mw
                            self.ih = round(mw / ratio)
                        self.imgWig.place(relx=0.5, rely=0.5, width=self.iw, height=self.ih, anchor=CENTER)
                        self.oldH = mh
                        self.oldW = mw
                    self.camImg = ImageTk.PhotoImage(self.camImg.resize((self.iw, self.ih), resample))
                    self.imgWig.configure(image=self.camImg)
                self.imgWig.image = self.camImg
                self.newFrame.clear()

    def schedule_resize(self, event):
        if self.resizePending:
            return
        self.resizePending = True
        self.master.after(50, self.resize)

    def resize(self):
        iw, ih = self.owlOrig.size
        mw, mh = (self.winfo_width(), self.winfo_height())
        if mw <= mh * self.owlOrig.ratio:
            resized = self.owlOrig.resize((mw, round((mw / iw) * ih)), resample)
        else:
            resized = self.owlOrig.resize((round((mh / ih) * iw), mh), resample)
        render = ImageTk.PhotoImage(resized)
        self.owl.configure(image=render)
        self.owl.image = render
        self.resizePending = False

    def client_exit(self):
        # Wrap-up code here
        self.master.destroy()


root = Tk()
root.geometry('640x480')

app = Window(root)

root.mainloop()

if app.camera is not None:
    app.camera.StopGrabbing()
    app.camera.Close()

