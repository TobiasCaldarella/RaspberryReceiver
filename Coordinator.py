'''
Created on 08.08.2019

@author: tobias
'''
from GpioController import PowerState
from MpdClient import MpdClient
import threading
from enum import Enum

class _RadioState(Enum):
    STOPPED = 0
    PLAYING = 1

class Coordinator(object):
    '''
    classdocs
    '''
    def __init__(self, logger):
        '''
        Constructor
        '''
        self.mqttClient = None
        self.gpioController = None
        self.mpdClient = None
        self.logger = logger
        self.powerLock = threading.Lock()
        self.numChannels = 0
        self.currentChannel = 0
        self.radioState = _RadioState.STOPPED
        
    def connectWifi(self):
        pass
        
    def connectMqtt(self):
        if self.mqttClient is None:
            return
        self.gpioController.setStereoBlink(active=True, pause_s=1)
        self.mqttClient.connect()
        self.mqttClient.waitForSubscription()
        self.gpioController.setStereolight(PowerState.OFF)

    def powerOff(self):
        with self.powerLock:
            self.logger.info("Powering down...")
            self.gpioController.setPowerAndSpeaker(PowerState.OFF)
            self.gpioController.setStereolight(PowerState.OFF)
            self.gpioController.setBacklight(PowerState.OFF)
            self.gpioController.setNeedlelight(PowerState.OFF)
            self.gpioController.setStereoBlink(active=True, pause_s=10)
            self.mqttClient.publish_power_state(PowerState.OFF)
    
    def powerOn(self):
        with self.powerAndSpeakerLock:
            self.logger.info("Powering up...")
            self.gpioController.setPowerAndSpeaker(PowerState.ON)
            self.gpioController.setStereolight(PowerState.ON)
            self.gpioController.setBacklight(PowerState.ON)
            self.gpioController.setNeedlelight(PowerState.ON)
            self.mqttClient.publish_power_state(PowerState.ON)
            
    def initialize(self):
        # todo: move needle to the absolute left...
        # todo: download radio playlist    
        if self.mpdClient.loadPlaylist():
            self.numChannels = self.mpdClient.getNumTracksInRadioPlaylist()
        
    def channelUp(self):
        # todo: move needle
        if self.currentChannel < self.numChannels:
            self.currentChannel+=1
            self.mpdClient.playTitle(self.currentChannel)
    
    def channelDown(self):
        # todo: move needle
        if self.currentChannel > 0:
            self.currentChannel-=1
            self.mpdClient.playTitle(self.currentChannel)
    
    def radioStop(self):
        self.radioState = _RadioState.STOPPED
        self.mpdClient.stop()
        
    def radioPlay(self):
        self.radioState = _RadioState.PLAYING
        self.mpdClient.playTitle(self.currentChannel)
        