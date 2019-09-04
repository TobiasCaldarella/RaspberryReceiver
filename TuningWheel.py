'''
Created on 09.08.2019

@author: tobias
'''
import RPi.GPIO as GPIO
import Configuration
import Coordinator
from enum import Enum
import threading

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
        self.buttonModeActive = False
        self.buttonModeTimer = None
        self.buttonModeCounter = 0
    
        GPIO.add_event_detect(self.gpio_right_sensor, GPIO.FALLING, self.do_right_sensor, bouncetime=40)
        GPIO.add_event_detect(self.gpio_left_sensor, GPIO.FALLING, self.do_left_sensor, bouncetime=40)
        GPIO.add_event_detect(self.gpio_button, GPIO.FALLING, self.do_button, bouncetime=300)
        
    def do_right_sensor(self, ch):
        self.logger.debug("right sensor triggered")
        if self.firstDown is Side.LEFT and GPIO.input(self.gpio_left_sensor) is GPIO.LOW:
            # left was already down, now trigger
            self.logger.debug("wheel counterclockwise")
            if self.enabled:
                if self.buttonModeActive:
                    if self.buttonModeCounter > 0:
                        self.buttonModeCounter-=1
                else:
                    self.coordinator.channelDown()
        elif GPIO.input(self.gpio_left_sensor) is GPIO.HIGH:
            self.firstDown = Side.RIGHT
    
    def do_left_sensor(self, ch):
        self.logger.debug("left sensor triggered")
        if self.firstDown is Side.RIGHT and GPIO.input(self.gpio_right_sensor) is GPIO.LOW:
            # left was already down, now trigger
            self.logger.debug("wheel clockwise")
            if self.enabled:
                if self.buttonModeActive:
                    self.buttonModeCounter+=1
                else:
                    self.coordinator.channelUp()
        elif GPIO.input(self.gpio_right_sensor) is GPIO.HIGH:
            self.firstDown = Side.LEFT
            
    def do_button(self, ch):
        self.logger.debug("button triggered")
        if self.enabled is False:
            return
        if self.buttonModeActive is True:
            self.buttonModeActive = False
            self.buttonModeTimer.cancel()
            # do something with collected ticks
            self.coordinator.setChannel(self.buttonModeCounter)
            self.buttonModeCounter = 0
        else:
            self.buttonModeCounter = 0
            self.buttonModeActive = True
            self.buttonModeTimer = threading.Timer(10.0, self.do_button_timeout)
            self.buttonModeTimer.start()
            
    def do_button_timeout(self):
        self.buttonModeActive = False
    
    def enable(self):
        self.logger.debug("Wheel enabled")
        self.enabled = True
        
    def disable(self):
        self.logger.debug("Wheel disabled")
        self.enabled = False