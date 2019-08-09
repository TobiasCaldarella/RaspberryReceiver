'''
Created on 08.08.2019

@author: tobias
'''
from GpioController import PowerState
from MpdClient import MpdClient
import threading

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
        
    def channelUp(self):
        pass
    
    def channelDown(self):
        pass
        