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

class VolumeKnobRotaryEncoder(object):
    '''
    classdocs
    '''
    def __init__(self, config: Configuration, coordinator: Coordinator):
        '''
        Constructor
        '''
        self.gpio_right_sensor = config.gpio_vol_right
        self.gpio_left_sensor = config.gpio_vol_left
        GPIO.setup(self.gpio_right_sensor, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.gpio_left_sensor, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.logger = config.logger
        coordinator.volumeKnob = self
        self.coordinator = coordinator
        self.firstDown = Side.NONE
        self.enabled = False
    
        GPIO.add_event_detect(self.gpio_right_sensor, GPIO.FALLING, self.do_right_sensor)
        GPIO.add_event_detect(self.gpio_left_sensor, GPIO.FALLING, self.do_left_sensor)
        
    def do_right_sensor(self, ch):
        self.logger.debug("volumeknob: right sensor triggered")
        if self.firstDown is Side.LEFT and GPIO.input(self.gpio_left_sensor) is GPIO.LOW:
            # left was already down, now trigger
            self.logger.debug("volumeknob counterclockwise")
            if self.enabled:
                self.coordinator.volumeDown()
        elif GPIO.input(self.gpio_left_sensor) is GPIO.HIGH:
            self.firstDown = Side.RIGHT
    
    def do_left_sensor(self, ch):
        self.logger.debug("volumeknob: left sensor triggered")
        if self.firstDown is Side.RIGHT and GPIO.input(self.gpio_right_sensor) is GPIO.LOW:
            # left was already down, now trigger
            self.logger.debug("volumeknob clockwise")
            if self.enabled:
                self.coordinator.volumeUp()
        elif GPIO.input(self.gpio_right_sensor) is GPIO.HIGH:
            self.firstDown = Side.LEFT
        
    def enable(self):
        self.enabled = True
        self.logger.debug("Volumeknob enabled")
        
    def disable(self):
        self.logger.debug("Volumeknob disabled")
        self.enabled = False