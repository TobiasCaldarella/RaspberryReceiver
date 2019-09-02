'''
Created on 17.08.2019

@author: tobias
'''
import os
from inotify_simple import INotify, flags
import threading
import subprocess

class Bluetooth(object):
    '''
    classdocs
    '''


    def __init__(self, config, coordinator):
        self.logger = config.logger
        self.coordinator = coordinator
        self.inotify = INotify()
        mask = flags.CREATE | flags.DELETE | flags.MODIFY | flags.DELETE_SELF | flags.OPEN
        self.wd = self.inotify.add_watch('/sys/class/bluetooth/hci0', mask)
        self.device_connected = False
        self.playbackProcess = None
        self.run = True
        coordinator.bluetooth = self
    
    def initialize(self):
        self.disable()
    
    def startPlayback(self):
        if self.playbackProcess is None:
            try:
                self.playbackProcess = subprocess.Popen(["/usr/bin/bluealsa-aplay", "--profile-a2dp", "00:00:00:00:00:00"])
            except:
                self.logger.error("Could not start bluealsa-aplay")
        else:
            self.logger.error("bluealsa-aplay already/still running?")
            
    def stopPlayback(self):
        if self.playbackProcess is None:
            self.logger.info("No playback process running.")
        else:
            self.logger.info("Killing bluealsa-aplay")
            self.playbackProcess.terminate()
    
    def enable(self):
        self.logger.info("Enabling bluetooth")
        os.system("/usr/sbin/rfkill unblock bluetooth")
        self.run = True
        if self.workerThread is not None and self.workerThread.isAlive():
            self.logger.error("Bluetooth monitor thread still/already running!")
        else:
            self.workerThread = threading.Thread(target=self._waitForEvent)
            self.workerThread.start()
    
    def disable(self):
        self.logger.info("Disabling bluetooth")
        self.stopPlayback()
        os.system("/usr/sbin/rfkill block bluetooth")
        self.run = False
        if self.workerThread is not None:
            self.workerThread.join(2)
            if self.workerThread.isAlive():
                self.logger.error("Could not stop bluetooth monitor thread!")
        
    def _waitForEvent(self):
        self.logger.info("Bluetooth monitor thread started")
        prevNumEntries = -1
        while(self.run):
            #self.logger.debug("Waiting for bluetooth event or 5s timeout...")
            for event in self.inotify.read(1000):
                pass
                #self.logger.debug("got bluetooth event: '%s'" % event)
                
            numEntries = len(os.listdir('/sys/class/bluetooth/'))
            if prevNumEntries != numEntries:
                self.logger.debug("'%i' entries in /sys/class/bluetooth/, was %i before" % (numEntries, prevNumEntries))
                prevNumEntries = numEntries
                
            if numEntries > 1:
                #self.logger.debug("Bluetooth device connected")
                if self.device_connected == False:
                    self.logger.info("New bluetooth device connected")
                    self.device_connected = True
                    self.coordinator.bluetoothPlaying(True)
                    self.startPlayback()
            else:
                #self.logger.debug("No bluetooth device connected")
                if self.device_connected == True:
                    self.logger.info("Bluetooth device no longer connected")
                    self.stopPlayback()
                    self.coordinator.bluetoothPlaying(False)
                    self.device_connected = False        
            #self.logger.debug("...waiting again for bluetooth event or 5s timeout...")
        self.logger.info("Bluetooth monitor thread stopped")
            