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
        mask = flags.CREATE | flags.DELETE | flags.MODIFY | flags.DELETE_SELF
        self.wd = self.inotify.add_watch('/sys/class/bluetooth/hci0', mask)
        self.device_connected = False
        self.playbackProcess = None
    
    def initialize(self):
        self.disable()
        self.workerThread = threading.Thread(target=self._waitForEvent)
        self.workerThread.start()
        pass
    
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
        os.system("rfkill unblock bluetooth")
    
    def disable(self):
        self.logger.info("Disabling bluetooth")
        self.stopPlayback()
        os.system("rfkill block bluetooth")
        
    def _waitForEvent(self):
        self.logger.debug("Waiting for bluetooth event...")
        for event in self.inotify.read():
            self.logger.debug("got bluetooth event: '%s'" % event)
            numEntries = os.listdir('/sys/class/bluetooth/hci0/')
            self.logger.debug("'%i' entries in /sys/class/bluetooth/hci0/" % numEntries)
            if numEntries > 1:
                self.logger.debug("Bluetooth device connected")
                if self.device_connected == False:
                    self.logger.info("New bluetooth device connected")
                    self.coordinator.bluetoothPlaying(True)
                    self.startPlayback()
            else:
                self.logger.debug("No bluetooth device connected")
                if self.device_connected == True:
                    self.logger.info("Bluetooth device no longer connected")
                    self.stopPlayback()
                    self.coordinator.bluetoothPlaying(False)
                
            self.logger.debug("...waiting again for bluetooth event...")
        