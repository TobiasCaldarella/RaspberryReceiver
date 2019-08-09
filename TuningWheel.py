'''
Created on 09.08.2019

@author: tobias
'''
import RPi.GPIO as GPIO
import Configuration
import Coordinator
from enum import Enum

class Side(Enum):
    NONE = 0
    LEFT = 1
    RIGHT = 2

class TuningWheel(object):
    '''
    classdocs
    '''
    

    def __init__(self, config: Configuration, coordinator: Coordinator):
        '''
        Constructor
        '''
        self.gpio_right_sensor = config.gpio_mag_right
        self.gpio_left_sensor = config.gpio_mag_left
        GPIO.setup(self.gpio_right_sensor, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.gpio_left_sensor, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.logger = config.logger
        coordinator.wheel = self
        self.coordinator = coordinator
        self.lastLevel = None
        self.enabled = False
    
        GPIO.add_event_detect(self.gpio_right_sensor, GPIO.BOTH, self.do_right_sensor)
        GPIO.add_event_detect(self.gpio_left_sensor, GPIO.BOTH, self.do_left_sensor)
        
    def do_right_sensor(self, ch):
        newState = GPIO.input(self.gpio_right_sensor)
        self.logger.debug("right sensor changed => %s" % newState)
        if not self.enabled:
            return
        if newState == self.lastLevel:
            self.logger.debug("wheel clockwise")
            self.coordinator.channelUp()
        else:
            self.lastLevel = newState
    
    def do_left_sensor(self, ch):
        newState = GPIO.input(self.gpio_left_sensor)
        self.logger.debug("left sensor changed => %s" % newState)
        if not self.enabled:
            return
        if newState == self.lastLevel:
            self.logger.debug("wheel counter-clockwise")
            self.coordinator.channelDown()
        else:
            self.lastLevel = newState
    
    def enable(self):
        self.logger.debug("Wheel enabled")
        self.enabled = True
        
    def disable(self):
        self.logger.debug("Wheel disabled")
        self.enabled = False