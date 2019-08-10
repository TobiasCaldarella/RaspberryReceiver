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
        self.gpio_button = config.wheel_button
        GPIO.setup(self.gpio_right_sensor, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.gpio_left_sensor, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.gpio_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.logger = config.logger
        coordinator.wheel = self
        self.coordinator = coordinator
        self.firstDown = Side.NONE
        self.enabled = False
    
        GPIO.add_event_detect(self.gpio_right_sensor, GPIO.FALLING, self.do_right_sensor, bouncetime=40)
        GPIO.add_event_detect(self.gpio_left_sensor, GPIO.FALLING, self.do_left_sensor, bouncetime=40)
        GPIO.add_event_detect(self.gpio_button, GPIO.FALLING, self.do_button, bouncetime=300)
        
    def do_right_sensor(self, ch):
        self.logger.debug("right sensor triggered")
        if self.firstDown is Side.LEFT:
            # left was already down, now trigger
            self.firstDown = Side.NONE
            self.logger.debug("wheel counterclockwise")
            if self.enabled:
                self.coordinator.channelDown()
        else:
            self.firstDown = Side.RIGHT
    
    def do_left_sensor(self, ch):
        self.logger.debug("left sensor triggered")
        if self.firstDown is Side.RIGHT:
            # left was already down, now trigger
            self.firstDown = Side.NONE
            self.logger.debug("wheel clockwise")
            if self.enabled:
                self.coordinator.channelUp()
        else:
            self.firstDown = Side.LEFT
            
    def do_button(self, ch):
        self.logger.debug("button triggered")
    
    def enable(self):
        self.logger.debug("Wheel enabled")
        self.enabled = True
        
    def disable(self):
        self.logger.debug("Wheel disabled")
        self.enabled = False